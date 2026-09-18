"""
Phase 3 Scanner Pipeline Tests: Modular Testing of Pipeline Stages
Verifies:
  - GateChain evaluation and individual Gate logic
  - Scalp vs Intraday strategy selection & execution
  - Session VWAP calculation isolation
  - Signal factory construction
"""
from decimal import Decimal
from datetime import datetime, time as dt_time, timedelta
from zoneinfo import ZoneInfo
import pytest
from app.signals.strategies.base import SignalCandidate
from app.signals.pipeline.gates import (
    GateChain,
    KillSwitchGate,
    FeedCircuitGate,
    FNOIntegrityGate,
    DeskConcurrencyGate,
    PortfolioConcurrencyGate,
    CrossDeskArbiterGate,
    RSIGate,
    MarketStructureGate,
    TriggerIntegrityGate,
    OptionViabilityGate,
)
from app.signals.pipeline.data_acquisition import calculate_session_vwap, detect_market_regime
from app.signals.pipeline.signal_factory import build_signal_instance
from app.signals.risk_engine import ValidatedRiskDecision


def _sample_candidate(strategy="BREAKOUT", direction="LONG_CALL", spot=Decimal("24000.0")) -> SignalCandidate:
    return SignalCandidate(
        underlying="NIFTY",
        strategy=strategy,
        direction=direction,
        timeframe="5M",
        spot_price=spot,
        entry_min=Decimal("24010.0"),
        entry_max=Decimal("24020.0"),
        trigger=Decimal("24015.0"),
        stop_loss=Decimal("23950.0"),
        target_1=Decimal("24100.0"),
        target_2=Decimal("24180.0"),
        risk_points=Decimal("65.0"),
        risk_reward_t1=1.3,
        risk_reward_t2=2.5,
        confidence=80.0,
        context_snapshot={
            "indicators": {
                "rsi": 60.0,
                "volatility": {"atr": 25.0},
                "support_resistance": {"support": [23900.0], "resistance": [24200.0]},
            }
        },
    )


def test_session_vwap_calculation():
    """P0-2 fail-closed: a stale candle pool must NOT yield a VWAP.

    Only true session-anchored bars (>= 09:15:00 IST of the latest bar's date)
    may price the VWAP; otherwise the honest answer is (None, degraded=True, 0).
    """
    stale_candles = [
        {"timestamp": 1700000000000, "high": 24050.0, "low": 23950.0, "close": 24000.0, "volume": 1000},
        {"timestamp": 1700000300000, "high": 24080.0, "low": 23980.0, "close": 24050.0, "volume": 2000},
    ]
    vwap, degraded, cov = calculate_session_vwap(stale_candles)
    assert vwap is None
    assert degraded is True
    assert cov == 0.0

    # Positive case: true session candles anchored at today's 09:15 IST.
    ist = ZoneInfo("Asia/Kolkata")
    session_open = datetime.combine(datetime.now(ist).date(), dt_time(9, 15), tzinfo=ist)
    session_candles = [
        {
            "timestamp": int((session_open + timedelta(minutes=5)).timestamp() * 1000),
            "high": 24050.0,
            "low": 23950.0,
            "close": 24000.0,
            "volume": 1000,
        },
        {
            "timestamp": int((session_open + timedelta(minutes=10)).timestamp() * 1000),
            "high": 24080.0,
            "low": 23980.0,
            "close": 24050.0,
            "volume": 2000,
        },
    ]
    vwap2, degraded2, cov2 = calculate_session_vwap(session_candles)
    assert vwap2 is not None
    assert isinstance(vwap2, Decimal)
    assert vwap2 > 0
    assert degraded2 is False
    assert cov2 == 100.0


def test_detect_market_regime():
    ta_trending = {
        "momentum": {"adx": 30.0},
        "trend": {"trend": "BULLISH"},
        "volatility": {"atr_percentile": 50.0, "bb_width_pctile": 50.0},
    }
    assert detect_market_regime(ta_trending) == "TREND_UP"

    ta_compression = {
        "momentum": {"adx": 15.0},
        "trend": {"trend": "RANGE"},
        "volatility": {"atr_percentile": 40.0, "bb_width_pctile": 15.0},
    }
    assert detect_market_regime(ta_compression) == "COMPRESSION_SQUEEZE"


def _synthetic_candles(n: int) -> list[dict]:
    import math

    candles = []
    price = 25000.0
    for i in range(n):
        move = math.sin(i / 7.0) * 40.0 + i * 0.5
        o = price
        c = price + move * 0.2
        h = max(o, c) + 15.0
        l = min(o, c) - 15.0
        candles.append(
            {
                "timestamp": 1700000000000 + i * 300000,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": 10000 + i * 100,
            }
        )
        price = c
    return candles


def test_analyze_timeframe_supplies_regime_percentiles():
    """Regression: TA must emit the percentile inputs detect_market_regime reads.

    Without atr_percentile/bb_width_pctile every production scan failed closed
    with ta_unavailable_regime_unknown and zero strategies ever ran.
    """
    from app.technical_analysis.analyzer import analyze_timeframe

    ta = analyze_timeframe(_synthetic_candles(120), symbol="NIFTY", timeframe="5M")
    vol = ta["volatility"]
    assert vol["atr_percentile"] is not None
    assert vol["bb_width_pctile"] is not None
    assert 0.0 <= vol["atr_percentile"] <= 100.0
    assert 0.0 <= vol["bb_width_pctile"] <= 100.0
    assert vol["bollinger_bandwidth_percentile"] == vol["bb_width_pctile"]
    assert vol["bandwidth_percentile"] == vol["bb_width_pctile"]
    assert detect_market_regime(ta) != "UNKNOWN"


def test_regime_percentiles_fail_closed_on_thin_history():
    """Thin history must stay honest: no percentile, no fabricated regime."""
    from app.technical_analysis.analyzer import analyze_timeframe

    ta = analyze_timeframe(_synthetic_candles(15), symbol="NIFTY", timeframe="5M")
    vol = ta["volatility"]
    assert vol["atr_percentile"] is None
    assert vol["bb_width_pctile"] is None
    assert detect_market_regime(ta) == "UNKNOWN"


def test_gate_chain_evaluation_passes_valid_candidate():
    cand = _sample_candidate()
    chain = GateChain([
        KillSwitchGate(),
        FeedCircuitGate(),
        FNOIntegrityGate(),
        RSIGate(),
        TriggerIntegrityGate(),
    ])
    passed, results = chain.evaluate(cand)
    assert passed is True
    assert all(r.passed for r in results)


def test_rsi_gate_rejection():
    cand = _sample_candidate(strategy="BREAKOUT", direction="LONG_CALL")
    # RSI of 40 is below the 52-82 range for Breakout Call
    cand.context_snapshot["indicators"]["rsi"] = 40.0
    gate = RSIGate()
    res = gate.evaluate(cand)
    assert res.passed is False
    assert "RSI_REJECTION" in str(res.reason_code)


def test_build_signal_instance():
    cand = _sample_candidate()
    risk_dec = ValidatedRiskDecision(
        accepted=True,
        entry_price=Decimal("24015.0"),
        stop_loss=Decimal("23950.0"),
        target_1=Decimal("24100.0"),
        target_2=Decimal("24180.0"),
        risk_points=65.0,
        reward_t1_points=85.0,
        reward_t2_points=165.0,
        risk_reward_t1=1.3,
        risk_reward_t2=2.5,
        lots=2,
        quantity=130,
        lot_size=65,
        max_rupee_loss=8450.0,
        trigger_ttl_seconds=300,
        active_time_stop_seconds=3600,
    )
    sig = build_signal_instance(
        cand=cand,
        fused_score=82.0,
        fsm_init_state="ARMED",
        risk_decision=risk_dec,
        inst_overlay={"applied": True, "delta": 2.0},
        ai_advice=None,
        ml_pred=None,
        overlay=None,
        explain_bundle=None,
        fno_is_degraded=False,
    )
    assert sig.underlying == "NIFTY"
    assert sig.fsm_state == "ARMED"
    assert sig.lots == 2
    assert sig.quantity == 130
