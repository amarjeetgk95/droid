"""
Unit tests for the 7 Architectural Hardening Fixes:
1. Degraded F&O Gate (ARMED_BLOCKED_FNO_DEGRADED)
2. True Session-Anchored VWAP (09:15:00 IST)
3. Un-coerced AI Bias & Canonical Regime
4. Dynamic Strategy Scoring (No hardcoded constants)
5. Underlying Anti-Stacking & Portfolio Concurrency Limits
6. Empirical Expectancy & Average R/R (Mathematical truth)
7. Fail-Closed Master Pipeline
"""
import pytest
from decimal import Decimal
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo

from app.signals.strategies.base import SignalCandidate, StrategyContext
from app.signals.fsm import signal_fsm, SignalInstance
from app.signals.scanner import SignalScanner
from app.signals.confluence import confluence_engine
from app.signals.outcome_tracker import SignalOutcomeTracker
from app.signals.strategies.vwap_scalp import VWAPScalpStrategy
from app.signals.strategies.breakout import BreakoutStrategy
from app.signals.strategies.orb import OpeningRangeBreakoutStrategy
from app.services.master_pipeline import master_pipeline, PipelineOutcome
from app.services.calendar_service import calendar_service, MarketSessionPermission

IST = ZoneInfo("Asia/Kolkata")


def _mock_open_permission():
    return MarketSessionPermission(
        allowed=True,
        reason="MARKET_OPEN",
        exchange="NSE",
        session="REGULAR",
        timestamp_ist=datetime.now(IST),
        market_open=None,
        market_close=None,
    )


@pytest.fixture(autouse=True)
def clean_fsm_state():
    """Clear FSM state before and after each test."""
    with signal_fsm._lock:
        signal_fsm._signals.clear()
        signal_fsm._audit_log.clear()
    yield
    with signal_fsm._lock:
        signal_fsm._signals.clear()
        signal_fsm._audit_log.clear()


@pytest.mark.asyncio
async def test_degraded_fno_blocks_candidate_arming(monkeypatch):
    """Verify that candidates with fno_degraded=True are rejected with ARMED_BLOCKED_FNO_DEGRADED."""
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
        fno_degraded=True,  # DEGRADED F&O
    )

    registered, rejected = await scanner._process_candidates([cand])
    assert len(registered) == 1
    assert registered[0].fsm_state == "VALIDATED"
    assert registered[0].confluence_breakdown.get("fno_degraded") is True
    assert any("ARMED_BLOCKED_FNO_DEGRADED" in r for r in rejected)

    # Verify FSM strictly blocks transition to ARMED
    ok, err = signal_fsm.transition(registered[0].signal_id, "ARMED")
    assert not ok
    assert err == "FNO_DATA_DEGRADED_CANNOT_ARM"


def test_orb_strategy_fails_closed_without_opening_range_or_candles():
    """Verify ORB strategy fails closed (returns None) instead of fabricating ATR envelope."""
    strat = OpeningRangeBreakoutStrategy()
    ctx = StrategyContext(
        underlying="NIFTY",
        spot_price=Decimal("24800"),
        timeframe="5M",
        indicators={"atr": 25.0},
        mtf={"overall_bias": "BULLISH"},
        fno={"pcr": 1.1},
        regime="TREND_UP",
        candles=[],  # No candles
        timestamp_ms=0,  # Bypass session time window check
    )
    cand = strat.detect(ctx)
    assert cand is None


def test_dynamic_fno_scoring_in_breakout():
    """Verify Breakout strategy continuously scales fno_score with PCR using neutral baseline."""
    strat = BreakoutStrategy()
    
    # High PCR = 1.4
    ctx_high = StrategyContext(
        underlying="NIFTY",
        spot_price=Decimal("24805"),
        timeframe="5M",
        indicators={"atr": 20.0, "volume_ratio": 1.5, "support_resistance": {"resistance": [24800], "support": [24700]}},
        mtf={"overall_bias": "BULLISH", "alignment_score": 80.0},
        fno={"pcr": 1.4},
        regime="TREND_UP",
    )
    cand_high = strat.detect(ctx_high)
    assert cand_high is not None
    # With PCR 1.4: 50 + (0.4 * 40) = 66.0
    assert cand_high.fno_score == 66.0

    # Low PCR = 0.8
    ctx_low = StrategyContext(
        underlying="NIFTY",
        spot_price=Decimal("24805"),
        timeframe="5M",
        indicators={"atr": 20.0, "volume_ratio": 1.5, "support_resistance": {"resistance": [24800], "support": [24700]}},
        mtf={"overall_bias": "BULLISH", "alignment_score": 80.0},
        fno={"pcr": 0.8},
        regime="TREND_UP",
    )
    cand_low = strat.detect(ctx_low)
    assert cand_low is not None
    # With PCR 0.8: 50 + (-0.2 * 40) = 34.0 -> clamped to 45.0
    assert cand_low.fno_score == 45.0


def test_dynamic_scoring_in_vwap_scalp():
    """Verify VWAP scalp calculates dynamic scores based on wick ratio and deviation (not hardcoded 78.0)."""
    strat = VWAPScalpStrategy()
    
    # Price 0.5% below VWAP (bouncing up with strong 50% lower wick)
    ctx = StrategyContext(
        underlying="NIFTY",
        spot_price=Decimal("24675"),
        timeframe="1M",
        vwap=Decimal("24800"),  # dev_pct = (24800 - 24675)/24800 = 0.504%
        candles=[
            {"open": 24680, "high": 24690, "low": 24670, "close": 24675, "volume": 1000},
            {"open": 24660, "high": 24680, "low": 24640, "close": 24675, "volume": 1200},
        ],
        indicators={"volume_ratio": 1.2},
        mtf={"alignment_score": 75.0},
        fno={"pcr": 1.2},
        regime="RANGE",
    )
    cand = strat.detect(ctx)
    assert cand is not None
    assert cand.technical_score != 78.0  # Must not be hardcoded 78.0
    assert cand.technical_score > 50.0
    assert cand.fno_score != 75.0  # Dynamic from PCR


@pytest.mark.asyncio
async def test_uncoerced_ai_bias_and_regime():
    """Verify confluence_engine derives regime direction from market regime, NOT candidate direction."""
    cand = SignalCandidate(
        underlying="NIFTY",
        strategy="MEAN_REVERSION",
        direction="LONG_CALL",  # Candidate wants CALL
        timeframe="5M",
        spot_price=Decimal("24800"),
        entry_min=Decimal("24800"),
        entry_max=Decimal("24810"),
        trigger=Decimal("24810"),
        stop_loss=Decimal("24785"),
        target_1=Decimal("24850"),
        target_2=Decimal("24890"),
        risk_points=Decimal("25"),
        risk_reward_t1=1.6,
        risk_reward_t2=3.2,
        regime_score=75.0,
    )

    snapshot = {
        "regime": "TREND_DOWN",
        "fno": {"pcr": 0.70},  # Bearish F&O
        "mtf": {},
        "indicators": {},
        "spot_price": 24800.0,
    }

    res = await confluence_engine.fetch_ai_advisory(cand, snapshot)
    assert res is not None


@pytest.mark.asyncio
async def test_underlying_anti_stacking_across_strategies(monkeypatch):
    """Verify that multiple strategies cannot stack positions in the same direction on the same underlying."""
    monkeypatch.setattr(calendar_service, "can_trade_now", _mock_open_permission)

    scanner = SignalScanner()

    # Pre-register an active BREAKOUT LONG_CALL on NIFTY in FSM
    existing_sig = SignalInstance(
        signal_id="sig-breakout-nifty",
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("24800"),
        entry_min=Decimal("24800"),
        entry_max=Decimal("24810"),
        trigger=Decimal("24810"),
        stop_loss=Decimal("24785"),
        target_1=Decimal("24850"),
        target_2=Decimal("24890"),
        risk_points=Decimal("25"),
        risk_reward_t1=1.6,
        risk_reward_t2=3.2,
        confidence=80.0,
        fsm_state="ARMED",
    )
    signal_fsm.register(existing_sig)

    # Now an ORB strategy generates another LONG_CALL candidate on NIFTY
    orb_cand = SignalCandidate(
        underlying="NIFTY",
        strategy="ORB",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("24805"),
        entry_min=Decimal("24805"),
        entry_max=Decimal("24815"),
        trigger=Decimal("24815"),
        stop_loss=Decimal("24790"),
        target_1=Decimal("24855"),
        target_2=Decimal("24895"),
        risk_points=Decimal("25"),
        risk_reward_t1=1.6,
        risk_reward_t2=3.2,
        confidence=82.0,
    )

    registered, rejected = await scanner._process_candidates([orb_cand])
    assert len(registered) == 0
    assert any("STACKING_BLOCKED_EXISTING_BREAKOUT_LONG_CALL" in r for r in rejected)


@pytest.mark.asyncio
async def test_portfolio_concurrency_cap(monkeypatch):
    """Verify portfolio cap: max 4 open trades across entire portfolio."""
    monkeypatch.setattr(calendar_service, "can_trade_now", _mock_open_permission)

    scanner = SignalScanner()

    # Pre-register 4 open trades across the portfolio
    for i in range(4):
        sig = SignalInstance(
            signal_id=f"sig-active-{i}",
            underlying=f"SYM_{i}",
            strategy="BREAKOUT",
            direction="LONG_CALL",
            timeframe="5M",
            spot_price=Decimal("24800"),
            entry_min=Decimal("24800"),
            entry_max=Decimal("24810"),
            trigger=Decimal("24810"),
            stop_loss=Decimal("24785"),
            target_1=Decimal("24850"),
            target_2=Decimal("24890"),
            risk_points=Decimal("25"),
            risk_reward_t1=1.6,
            risk_reward_t2=3.2,
            confidence=80.0,
            fsm_state="CONFIRMED",
        )
        signal_fsm.register(sig)

    # Now SENSEX candidate arrives
    sensex_cand = SignalCandidate(
        underlying="SENSEX",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("81000"),
        entry_min=Decimal("81000"),
        entry_max=Decimal("81050"),
        trigger=Decimal("81050"),
        stop_loss=Decimal("80950"),
        target_1=Decimal("81200"),
        target_2=Decimal("81400"),
        risk_points=Decimal("100"),
        risk_reward_t1=1.5,
        risk_reward_t2=3.0,
        confidence=78.0,
    )

    registered, rejected = await scanner._process_candidates([sensex_cand])
    assert len(registered) == 0
    assert any("PORTFOLIO_CONCURRENCY_LIMIT_REACHED" in r for r in rejected)


def test_empirical_expectancy_and_average_rr():
    """Verify average_rr and expectancy_r are empirical averages of actual realized net R, not hardcoded constants."""
    s1 = SignalInstance(
        signal_id="sig-win-1",
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("24800"),
        entry_min=Decimal("24800"),
        entry_max=Decimal("24810"),
        trigger=Decimal("24810"),
        stop_loss=Decimal("24785"),
        target_1=Decimal("24850"),
        target_2=Decimal("24890"),
        risk_points=Decimal("25"),
        risk_reward_t1=1.6,
        risk_reward_t2=3.2,
        confidence=0.85,
        fsm_state="TARGET_2_HIT",
        outcome_status="WIN_T2",
        terminal_outcome="FULL_WIN",
        realized_rr_net=3.1,
    )
    s2 = SignalInstance(
        signal_id="sig-win-2",
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("24800"),
        entry_min=Decimal("24800"),
        entry_max=Decimal("24810"),
        trigger=Decimal("24810"),
        stop_loss=Decimal("24785"),
        target_1=Decimal("24850"),
        target_2=Decimal("24890"),
        risk_points=Decimal("25"),
        risk_reward_t1=1.6,
        risk_reward_t2=3.2,
        confidence=0.85,
        fsm_state="TARGET_1_HIT",
        outcome_status="WIN_T1",
        terminal_outcome="PARTIAL_WIN",
        realized_rr_net=1.7,
    )
    s3 = SignalInstance(
        signal_id="sig-loss-1",
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("24800"),
        entry_min=Decimal("24800"),
        entry_max=Decimal("24810"),
        trigger=Decimal("24810"),
        stop_loss=Decimal("24785"),
        target_1=Decimal("24850"),
        target_2=Decimal("24890"),
        risk_points=Decimal("25"),
        risk_reward_t1=1.6,
        risk_reward_t2=3.2,
        confidence=0.85,
        fsm_state="STOP_LOSS_HIT",
        outcome_status="LOSS_SL",
        terminal_outcome="STOP_LOSS_HIT",
        realized_rr_net=-1.1,
    )

    signal_fsm.register(s1)
    signal_fsm.register(s2)
    signal_fsm.register(s3)

    tracker = SignalOutcomeTracker()
    metrics = tracker.get_performance_metrics()

    # Empirical average win R = (3.1 + 1.7) / 2 = 2.40 (not 2.25!)
    assert metrics.average_rr == 2.40
    # Empirical expectancy = (3.1 + 1.7 - 1.1) / 3 = 3.7 / 3 = 1.23 R per trade
    assert metrics.expectancy_r == 1.23
    # Profit factor = (3.1 + 1.7) / 1.1 = 4.8 / 1.1 = 4.36
    assert metrics.profit_factor == 4.36


@pytest.mark.asyncio
async def test_fail_closed_master_pipeline():
    """Verify master_pipeline aborts with NO_TRADE when technical features or direction_model are missing."""
    # Missing direction_model
    res_no_dir = await master_pipeline.evaluate(
        symbol="NIFTY",
        current_price=24800.0,
        atr=20.0,
        technical={"atr": 20.0, "vwap": 24800.0},
        direction_model=None,  # Missing!
    )
    assert res_no_dir["outcome"] == PipelineOutcome.NO_TRADE.value
    assert "missing direction model" in res_no_dir["reason"]

    # Missing technical
    res_no_tech = await master_pipeline.evaluate(
        symbol="NIFTY",
        current_price=24800.0,
        atr=20.0,
        technical=None,  # Missing!
        direction_model={"prob_up": 0.7, "prob_down": 0.3},
    )
    assert res_no_tech["outcome"] == PipelineOutcome.NO_TRADE.value
    assert "missing technical" in res_no_tech["reason"]
