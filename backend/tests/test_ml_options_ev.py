"""Unit and integration tests for DROID ML Engine Milestone 3.

Covers:
- Options Intelligence & Strike Selection Model (Greeks, Delta-Gamma-Theta holding returns)
- Expected Value (EV) Engine with granular Indian statutory, brokerage, and friction accounting
- Dynamic Position Sizer with half-Kelly bounds and Risk Engine cap enforcement
- Drift Monitor & Population Stability Index (PSI) calculation
- Data Quality Gate & Safe-Mode Circuit Breaker
- Stage C Soft Authority integration in enrichment pipeline
"""
from decimal import Decimal
import time
import numpy as np
import pytest

from app.ml.models.ev_engine import ev_engine
from app.ml.models.option_model import options_intelligence_model
from app.ml.monitoring.drift_monitor import drift_monitor
from app.ml.risk.dynamic_sizer import dynamic_position_sizer
from app.ml.validation.data_quality import data_quality_gate
from app.signals.pipeline.enrichment import enrich_candidate
from app.signals.strategies.base import SignalCandidate


def test_options_intelligence_strike_selection():
    """Verifies that the Options Intelligence model evaluates ITM-1, ATM, OTM-1 and picks optimal strike."""
    res = options_intelligence_model.evaluate_strikes(
        underlying="NIFTY",
        direction="LONG_CALL",
        spot_price=25000.0,
        target_1=25080.0,
        stop_loss=24960.0,
        p_target=0.65,
        p_stop=0.25,
        p_timeout=0.10,
        dte_days=2.0,
        atm_iv=0.14,
        expected_bars_held=15,
    )

    assert res["underlying"] == "NIFTY"
    assert res["lot_size"] == 75
    assert len(res["evaluations"]) == 3
    assert res["selected_strike"] in [24950.0, 25000.0, 25050.0]
    assert res["selected_premium"] > 0
    assert res["selected_delta"] > 0
    assert any(e["is_recommended"] for e in res["evaluations"])


def test_ev_engine_friction_breakdown():
    """Verifies statutory and execution frictions match Indian exchange formulas."""
    friction = ev_engine.calculate_friction(
        entry_premium=120.0,
        expected_exit_premium=150.0,
        quantity=75,
        spread_points=0.80,
        slippage_points=0.40,
    )

    assert friction.brokerage == 40.0  # ₹20 * 2 legs
    assert friction.stt > 0            # 0.1% on sell turnover
    assert friction.exchange_charges > 0 # 0.05% turnover
    assert friction.gst > 0            # 18% on service charges
    assert friction.spread_friction == round(0.80 * 75, 2)
    assert friction.slippage_friction == round(0.40 * 75, 2)
    assert friction.total_friction > friction.total_statutory_charges


def test_ev_engine_viable_trade_calculation():
    """Verifies that a high win-rate setup produces positive Net EV and passes viability gate."""
    res = ev_engine.calculate_trade_ev(
        entry_premium=120.0,
        lot_size=75,
        lots=1,
        expected_gain_at_t1=40.0,
        expected_loss_at_sl=20.0,
        expected_timeout_pnl=-3.0,
        p_target=0.70,
        p_stop=0.20,
        p_timeout=0.10,
    )

    assert res.gross_ev_total > 0
    assert res.net_ev_total > 0
    assert res.is_viable is True
    assert res.ev_risk_ratio > 0.10
    assert res.rejection_reason is None


def test_ev_engine_negative_ev_rejection():
    """Verifies that an unfavorable payoff setup with negative Net EV is rejected."""
    res = ev_engine.calculate_trade_ev(
        entry_premium=120.0,
        lot_size=75,
        lots=1,
        expected_gain_at_t1=10.0,
        expected_loss_at_sl=35.0,
        expected_timeout_pnl=-10.0,
        p_target=0.35,
        p_stop=0.55,
        p_timeout=0.10,
    )

    assert res.net_ev_total < 0
    assert res.is_viable is False
    assert "NEGATIVE_NET_EV" in str(res.rejection_reason)


def test_dynamic_position_sizer_bounds():
    """Verifies Half-Kelly mapping, EV rejection, and Risk Engine maximum lot cap."""
    # Case 1: Non-viable EV yields 0 lots
    rej_res = dynamic_position_sizer.compute_size(
        base_lots=2,
        max_lots=4,
        calibrated_p_win=0.40,
        expected_mfe_r=1.0,
        expected_mae_r=1.0,
        net_ev_total=-500.0,
        is_ev_viable=False,
    )
    assert rej_res.recommended_lots == 0
    assert rej_res.is_authorized is False

    # Case 2: High edge expands lots up to max_lots bound
    win_res = dynamic_position_sizer.compute_size(
        base_lots=2,
        max_lots=3,
        calibrated_p_win=0.75,
        expected_mfe_r=2.5,
        expected_mae_r=0.8,
        net_ev_total=2500.0,
        is_ev_viable=True,
    )
    assert win_res.is_authorized is True
    assert win_res.sizing_multiplier >= 1.0
    assert win_res.recommended_lots <= 3  # Never exceed max_lots

    # Case 3: Severe drawdown enforces defensive floor
    dd_res = dynamic_position_sizer.compute_size(
        base_lots=2,
        max_lots=4,
        calibrated_p_win=0.60,
        expected_mfe_r=1.5,
        expected_mae_r=1.0,
        net_ev_total=1000.0,
        is_ev_viable=True,
        current_drawdown_pct=4.5,
    )
    assert dd_res.sizing_multiplier == 0.50
    assert dd_res.recommended_lots == 1


def test_drift_monitor_psi():
    """Verifies that DriftMonitor detects stability and severe distribution shifts."""
    np.random.seed(42)
    base = np.random.normal(0, 1, 500)
    same = np.random.normal(0, 1, 500)
    shifted = np.random.normal(1.5, 1.2, 500)

    psi_stable = drift_monitor.compute_psi(base, same)
    psi_drifted = drift_monitor.compute_psi(base, shifted)

    assert psi_stable < 0.10
    assert psi_drifted > 0.25


def test_data_quality_gate_states():
    """Verifies Data Quality Gate circuit breaker transitions."""
    now_ms = int(time.time() * 1000)

    # 1. Healthy
    res_ok = data_quality_gate.validate_features([0.1, 0.2, 0.3], now_ms, now_ms - 2000, 25000.0)
    assert res_ok.status == "ACTIVE"
    assert res_ok.circuit_breaker_action == "NORMAL"

    # 2. Mild Staleness warning
    res_warn = data_quality_gate.validate_features([0.1, 0.2, 0.3], now_ms, now_ms - 15000, 25000.0)
    assert res_warn.status == "DEGRADED"
    assert res_warn.circuit_breaker_action == "SHADOW_ONLY"

    # 3. Corrupt NaNs -> Circuit Broken
    res_bad = data_quality_gate.validate_features([0.1, float("nan"), 0.3], now_ms, now_ms, 25000.0)
    assert res_bad.status == "CIRCUIT_BROKEN"
    assert res_bad.circuit_breaker_action == "SAFE_MODE_BYPASS"


class MockRiskDecision:
    def __init__(self, lots: int = 2, quantity: int = 150):
        self.lots = lots
        self.quantity = quantity


@pytest.mark.asyncio
async def test_stage_c_soft_sizing_integration():
    """Verifies that enrichment pipeline evaluates Options EV and soft-sizes lots in Stage C."""
    now_ms = int(time.time() * 1000)
    cand = SignalCandidate(
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("25000.0"),
        entry_min=Decimal("25000.0"),
        entry_max=Decimal("25020.0"),
        trigger=Decimal("25010.0"),
        stop_loss=Decimal("24975.0"),
        target_1=Decimal("25050.0"),
        target_2=Decimal("25100.0"),
        risk_points=Decimal("25.0"),
        risk_reward_t1=2.0,
        risk_reward_t2=4.0,
        confidence=80.0,
        regime_score=80.0,
        context_snapshot={"timestamp_ms": now_ms, "regime": "TREND_UP"},
    )

    candles = [
        {
            "timestamp": now_ms,
            "timestamp_ms": now_ms,
            "open": 25000.0,
            "high": 25010.0,
            "low": 24990.0,
            "close": 25005.0,
            "volume": 1000,
        }
    ]

    risk_decision = MockRiskDecision(lots=2, quantity=150)

    fused_score, inst_overlay, explain, fsm_state, ai_advice, ml_pred = await enrich_candidate(
        cand=cand,
        active_candles=candles,
        fno_data=None,
        fno_is_degraded=False,
        risk_decision=risk_decision,
        overlay={},
        rejected_gates=[],
        decision_timestamp_ms=now_ms,
    )

    assert "ml_options_ev" in cand.context_snapshot
    assert "ml_sizing" in cand.context_snapshot
    ev_info = cand.context_snapshot["ml_options_ev"]
    assert "selected_strike" in ev_info
    assert "net_ev" in ev_info
    assert any("ML Strike:" in r for r in cand.rationale)
    assert risk_decision.lots >= 1
