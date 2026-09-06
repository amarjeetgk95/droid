"""
Tests for:
1. Rich AI Context Snapshot (no starved empty dicts)
2. Decoupled Desk Concurrency (Scalp Desk 1M/3M vs Intraday Desk 5M/15M)
3. Candle-Anchored Cooldown scaling with timeframe
4. Throttled signals metrics exposure in outcome_tracker and ScanDiagnostics
5. State-Aware F&O Degraded Lifecycle
"""
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo
import pytest

from app.services.calendar_service import MarketSessionPermission, calendar_service
from app.signals.fsm import signal_fsm, SignalInstance
from app.signals.scanner import SignalScanner, ScanDiagnostics
from app.signals.strategies.base import SignalCandidate, StrategyContext
from app.signals.strategies.breakout import BreakoutStrategy
from app.signals.scalp_confirmation import ScalpConfirmationEngine
from app.signals.outcome_tracker import outcome_tracker

IST = ZoneInfo("Asia/Kolkata")


def _mock_open_permission(exchange: str = "NSE"):
    return MarketSessionPermission(
        allowed=True,
        reason="REGULAR_HOURS",
        exchange=exchange,
        session="REGULAR",
        timestamp_ist=datetime.now(IST),
        market_open=None,
        market_close=None,
    )


@pytest.fixture(autouse=True)
def clean_fsm():
    signal_fsm._signals.clear()
    signal_fsm._audit_log.clear()
    yield
    signal_fsm._signals.clear()
    signal_fsm._audit_log.clear()


@pytest.mark.asyncio
async def test_ai_snapshot_rich_context_passing(monkeypatch):
    """Verify scanner passes non-empty fno, mtf, indicators, and vwap into fetch_ai_advisory."""
    monkeypatch.setattr(calendar_service, "can_trade_now", _mock_open_permission)

    scanner = SignalScanner()

    # Candidate with rich context_snapshot
    cand = SignalCandidate(
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("24800"),
        entry_min=Decimal("24805"),
        entry_max=Decimal("24815"),
        trigger=Decimal("24815"),
        stop_loss=Decimal("24803"),
        target_1=Decimal("24850"),
        target_2=Decimal("24890"),
        risk_points=Decimal("12"),
        risk_reward_t1=1.6,
        risk_reward_t2=3.2,
        confidence=85.0,
        context_snapshot={
            "fno": {"pcr": 1.35, "ce_oi": 100000, "pe_oi": 135000},
            "mtf": {"overall_bias": "BULLISH", "alignment_score": 85.0},
            "indicators": {"adx": 28.5, "atr": 22.0, "volume_ratio": 1.8},
            "vwap": 24780.0,
            "spot_price": 24800.0,
            "regime": "TREND_UP",
        }
    )

    captured_snapshot = {}

    from app.signals.confluence import confluence_engine, AIAdviceResult

    async def mock_fetch_ai_advisory(candidate, snapshot):
        nonlocal captured_snapshot
        captured_snapshot = snapshot
        return AIAdviceResult(
            status="AVAILABLE",
            direction="BULLISH",
            confidence=85.0,
            score=85.0,
            reasoning="Strong PCR and MTF alignment",
        )

    monkeypatch.setattr(confluence_engine, "fetch_ai_advisory", mock_fetch_ai_advisory)

    registered, rejected = await scanner._process_candidates([cand])
    assert len(registered) == 1
    assert captured_snapshot.get("fno", {}).get("pcr") == 1.35
    assert captured_snapshot.get("mtf", {}).get("overall_bias") == "BULLISH"
    assert captured_snapshot.get("indicators", {}).get("adx") == 28.5
    assert captured_snapshot.get("vwap") == 24780.0


@pytest.mark.asyncio
async def test_desk_concurrency_decoupled_scalp_and_intraday(monkeypatch):
    """Verify 1 Scalp and 1 Intraday on the SAME underlying can co-exist, but same-desk stacking is blocked."""
    monkeypatch.setattr(calendar_service, "can_trade_now", _mock_open_permission)

    scanner = SignalScanner()

    # Pre-register an active 1M Scalp trade on NIFTY
    scalp_sig = SignalInstance(
        signal_id="sig-scalp-nifty",
        underlying="NIFTY",
        strategy="VWAP_SCALP",
        direction="LONG_CALL",
        timeframe="1M",
        is_scalp=True,
        spot_price=Decimal("24800"),
        entry_min=Decimal("24800"),
        entry_max=Decimal("24805"),
        trigger=Decimal("24805"),
        stop_loss=Decimal("24795"),
        target_1=Decimal("24825"),
        target_2=Decimal("24840"),
        risk_points=Decimal("10"),
        risk_reward_t1=2.0,
        risk_reward_t2=3.5,
        confidence=82.0,
        fsm_state="CONFIRMED",
    )
    signal_fsm.register(scalp_sig)

    # Candidate A: An Intraday 5M candidate on NIFTY (different desk lane) -> SHOULD BE ALLOWED
    intraday_cand = SignalCandidate(
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        is_scalp=False,
        spot_price=Decimal("24800"),
        entry_min=Decimal("24805"),
        entry_max=Decimal("24815"),
        trigger=Decimal("24815"),
        stop_loss=Decimal("24803"),
        target_1=Decimal("24850"),
        target_2=Decimal("24890"),
        risk_points=Decimal("12"),
        risk_reward_t1=1.6,
        risk_reward_t2=3.2,
        confidence=85.0,
    )

    registered, rejected = await scanner._process_candidates([intraday_cand])
    assert len(registered) == 1
    assert registered[0].strategy == "BREAKOUT"

    # Candidate B: Another Scalp (1M or 3M) in same direction -> SHOULD BE BLOCKED
    second_scalp = SignalCandidate(
        underlying="NIFTY",
        strategy="MICRO_MOMENTUM",
        direction="LONG_CALL",
        timeframe="1M",
        is_scalp=True,
        spot_price=Decimal("24800"),
        entry_min=Decimal("24802"),
        entry_max=Decimal("24808"),
        trigger=Decimal("24808"),
        stop_loss=Decimal("24798"),
        target_1=Decimal("24830"),
        target_2=Decimal("24850"),
        risk_points=Decimal("10"),
        risk_reward_t1=2.2,
        risk_reward_t2=4.0,
        confidence=80.0,
    )

    registered_2, rejected_2 = await scanner._process_candidates([second_scalp])
    assert len(registered_2) == 0
    assert any("UNDERLYING_HAS_ACTIVE_TRADE_SCALP" in r for r in rejected_2)


def test_candle_anchored_cooldown_scaling():
    """Verify cooldown scales with candle timeframe: 1M=60s, 3M=180s, 5M=300s, 15M=900s."""
    engine = ScalpConfirmationEngine()
    now_ms = 1_000_000_000

    cand_1m = SignalCandidate(
        underlying="NIFTY",
        strategy="VWAP_SCALP",
        direction="LONG_CALL",
        timeframe="1M",
        spot_price=Decimal("24800"),
        entry_min=Decimal("24800"),
        entry_max=Decimal("24805"),
        trigger=Decimal("24805"),
        stop_loss=Decimal("24795"),
        target_1=Decimal("24825"),
        target_2=Decimal("24840"),
        risk_points=Decimal("10"),
        risk_reward_t1=2.0,
        risk_reward_t2=3.5,
    )
    
    # Record confirmed at now_ms
    engine.record_confirmed(cand_1m, candle_timestamp_ms=now_ms, now_ms=now_ms)

    # 45s later (1M requires 60s) -> should be rejected for cooldown
    res = engine.validate(cand_1m, current_spot=Decimal("24805"), regime="RANGE", candle_timestamp_ms=now_ms + 45_000, now_ms=now_ms + 45_000)
    assert res.passed is False
    assert res.reason_code == "REJECTED_COOLDOWN"

    # 65s later (1M requires 60s) -> passes cooldown
    res_pass = engine.validate(cand_1m, current_spot=Decimal("24805"), regime="RANGE", candle_timestamp_ms=now_ms + 65_000, now_ms=now_ms + 65_000)
    assert res_pass.passed is True

    # For 5M candidate (requires 300s)
    cand_5m = SignalCandidate(
        underlying="NIFTY",
        strategy="VWAP_SCALP",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("24800"),
        entry_min=Decimal("24800"),
        entry_max=Decimal("24805"),
        trigger=Decimal("24805"),
        stop_loss=Decimal("24795"),
        target_1=Decimal("24825"),
        target_2=Decimal("24840"),
        risk_points=Decimal("10"),
        risk_reward_t1=2.0,
        risk_reward_t2=3.5,
    )
    engine.record_confirmed(cand_5m, candle_timestamp_ms=now_ms, now_ms=now_ms)

    # 150s later -> 150 < 300 -> rejected for cooldown
    res_5m = engine.validate(cand_5m, current_spot=Decimal("24805"), regime="RANGE", candle_timestamp_ms=now_ms + 150_000, now_ms=now_ms + 150_000)
    assert res_5m.passed is False
    assert res_5m.reason_code == "REJECTED_COOLDOWN"

    # 305s later -> passes
    res_5m_pass = engine.validate(cand_5m, current_spot=Decimal("24805"), regime="RANGE", candle_timestamp_ms=now_ms + 305_000, now_ms=now_ms + 305_000)
    assert res_5m_pass.passed is True


@pytest.mark.asyncio
async def test_performance_metrics_and_diagnostics_throttled_total(monkeypatch):
    """Verify outcome_tracker exposes throttled_signals_total tracked by scan diagnostics."""
    from app.signals.scanner import signal_scanner
    signal_scanner._last_diagnostics.clear()

    diag = ScanDiagnostics(underlying="NIFTY", throttled_signals_count=3)
    signal_scanner._last_diagnostics["NIFTY:5M"] = diag

    metrics = outcome_tracker.get_performance_metrics()
    assert metrics.throttled_signals_total == 3


@pytest.mark.asyncio
async def test_fno_degraded_state_aware_lifecycle(monkeypatch):
    """Verify degraded F&O setups register as VALIDATED but fail-close on any ARMED or active transition."""
    monkeypatch.setattr(calendar_service, "can_trade_now", _mock_open_permission)

    scanner = SignalScanner()
    cand = SignalCandidate(
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("24800"),
        entry_min=Decimal("24805"),
        entry_max=Decimal("24815"),
        trigger=Decimal("24815"),
        stop_loss=Decimal("24803"),
        target_1=Decimal("24850"),
        target_2=Decimal("24890"),
        risk_points=Decimal("12"),
        risk_reward_t1=1.6,
        risk_reward_t2=3.2,
        confidence=85.0,
        fno_degraded=True,
    )

    registered, rejected = await scanner._process_candidates([cand])
    assert len(registered) == 1
    sig = registered[0]
    assert sig.fsm_state == "VALIDATED"
    assert sig.confluence_breakdown.get("fno_degraded") is True
    assert any("ARMED_BLOCKED_FNO_DEGRADED" in r for r in rejected)

    # Attempt transitions to ARMED, TRIGGERED, CONFIRMED
    ok, err = signal_fsm.transition(sig.signal_id, "ARMED")
    assert not ok
    assert err == "FNO_DATA_DEGRADED_CANNOT_ARM"

    ok, err = signal_fsm.transition(sig.signal_id, "TRIGGERED")
    assert not ok
    assert err == "FNO_DATA_DEGRADED_CANNOT_ARM"

    ok, err = signal_fsm.transition(sig.signal_id, "CONFIRMED")
    assert not ok
    assert err == "FNO_DATA_DEGRADED_CANNOT_ARM"

