import pytest
from decimal import Decimal
from app.signals.strategies.base import SignalCandidate
from app.signals.risk_engine import central_risk_engine, StrategySetup
from app.event_engine.risk_overlay import EventRiskParameters
from app.algo.signal_fusion import conflict_resolver, ConflictResolver
from app.signals.confluence import confluence_engine, AIAdviceResult


def test_event_risk_overlay_blocks_entry_on_blackout():
    """Verify central_risk_engine rejects setups during event blackout windows."""
    setup = StrategySetup(
        strategy_name="BREAKOUT",
        underlying="NIFTY",
        direction="LONG_CALL",
        timeframe="5M",
        is_scalp=False,
        spot_price=Decimal("24800"),
        entry_trigger=Decimal("24810"),
        raw_structural_stop=Decimal("24785"),
        structural_target_candidates=[Decimal("24850"), Decimal("24890")],
        atr_5m=Decimal("20.0"),
        confidence=80.0,
    )
    
    # Mock blackout overlay
    blackout_overlay = EventRiskParameters(
        underlying="NIFTY",
        proximity_state="BLACKOUT_WINDOW",
        can_enter=False,
        sizing_multiplier=0.0,
        rejection_reason="EVENT_BLACKOUT_ACTIVE: RBI MPC decision imminent",
    )
    
    decision = central_risk_engine.evaluate(setup, allow_closed_market=True, event_overlay=blackout_overlay)
    assert decision.accepted is False
    assert "EVENT_RISK_REJECTED" in decision.rejection_reason


def test_event_risk_overlay_dampens_sizing():
    """Verify central_risk_engine scales down risk/sizing during approach window."""
    setup = StrategySetup(
        strategy_name="BREAKOUT",
        underlying="NIFTY",
        direction="LONG_CALL",
        timeframe="5M",
        is_scalp=False,
        spot_price=Decimal("24800"),
        entry_trigger=Decimal("24810"),
        raw_structural_stop=Decimal("24785"),
        structural_target_candidates=[Decimal("24850"), Decimal("24890")],
        atr_5m=Decimal("20.0"),
        confidence=80.0,
    )
    
    normal_decision = central_risk_engine.evaluate(
        setup, available_capital=500_000.0, allow_closed_market=True, event_overlay=None
    )
    
    dampened_overlay = EventRiskParameters(
        underlying="NIFTY",
        proximity_state="APPROACHING_WINDOW",
        can_enter=True,
        sizing_multiplier=0.5,
    )
    dampened_decision = central_risk_engine.evaluate(
        setup, available_capital=500_000.0, allow_closed_market=True, event_overlay=dampened_overlay
    )
    
    assert dampened_decision.accepted is True
    # Position sizing should be halved or reduced
    assert dampened_decision.lots <= normal_decision.lots


def test_candidate_conflict_arbitration_tie_rejection():
    """Verify opposing candidates with near-equal confidence (<5pts diff) are both rejected (NO_TRADE)."""
    call_cand = SignalCandidate(
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
        overall_confidence=78.0,
    )
    put_cand = SignalCandidate(
        underlying="NIFTY",
        strategy="MEAN_REVERSION",
        direction="LONG_PUT",
        timeframe="5M",
        spot_price=Decimal("24800"),
        entry_min=Decimal("24790"),
        entry_max=Decimal("24800"),
        trigger=Decimal("24790"),
        stop_loss=Decimal("24815"),
        target_1=Decimal("24750"),
        target_2=Decimal("24710"),
        risk_points=Decimal("25"),
        risk_reward_t1=1.6,
        risk_reward_t2=3.2,
        overall_confidence=76.0,  # Diff is 2.0 < epsilon(5.0)
    )
    
    approved, dropped = conflict_resolver.resolve_candidate_conflicts([call_cand, put_cand], tie_epsilon=5.0)
    assert len(approved) == 0  # Both rejected on tie
    assert len(dropped) == 1
    assert "CONFLICT_TIE_REJECT_BOTH" in dropped[0]


def test_candidate_conflict_arbitration_clear_winner():
    """Verify higher confidence candidate wins when difference exceeds epsilon."""
    call_cand = SignalCandidate(
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
        overall_confidence=85.0,  # Dominant
    )
    put_cand = SignalCandidate(
        underlying="NIFTY",
        strategy="MEAN_REVERSION",
        direction="LONG_PUT",
        timeframe="5M",
        spot_price=Decimal("24800"),
        entry_min=Decimal("24790"),
        entry_max=Decimal("24800"),
        trigger=Decimal("24790"),
        stop_loss=Decimal("24815"),
        target_1=Decimal("24750"),
        target_2=Decimal("24710"),
        risk_points=Decimal("25"),
        risk_reward_t1=1.6,
        risk_reward_t2=3.2,
        overall_confidence=68.0,  # Diff is 17.0 > 5.0
    )
    
    approved, dropped = conflict_resolver.resolve_candidate_conflicts([call_cand, put_cand], tie_epsilon=5.0)
    assert len(approved) == 1
    assert approved[0].strategy == "BREAKOUT"
    assert approved[0].direction == "LONG_CALL"
    assert len(dropped) == 1
    assert "DROPPED_IN_FAVOR_OF" in dropped[0]


def test_confluence_dynamic_weight_renormalization():
    """Verify dynamic weight renormalization sums to 1.0 when AI and ML are offline vs online."""
    cand = SignalCandidate(
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
        technical_score=80.0,
        mtf_score=75.0,
        fno_score=70.0,
        regime_score=85.0,
    )
    
    # 1. Base without AI or ML: unified weights tech 40 / mtf 20 / fno 15 / regime 10
    # (sum 0.85, renormalized) minus AI-unavailable haircut 8.0 (scoring_weights v2).
    score_base = confluence_engine.fuse(cand, ai_result=None, ml_prediction=None)
    expected_base = (80.0 * 0.40/0.85) + (75.0 * 0.20/0.85) + (70.0 * 0.15/0.85) + (85.0 * 0.10/0.85) - 8.0
    assert abs(score_base - expected_base) < 0.2
    
    # 2. With AI Available (no haircut; weights sum 0.95)
    ai_res = AIAdviceResult(status="AVAILABLE", score=90.0, confidence=0.9)
    score_with_ai = confluence_engine.fuse(cand, ai_result=ai_res, ml_prediction=None)
    expected_ai = (80.0 * 0.40/0.95) + (75.0 * 0.20/0.95) + (70.0 * 0.15/0.95) + (85.0 * 0.10/0.95) + (90.0 * 0.10/0.95)
    assert abs(score_with_ai - expected_ai) < 0.2
    
    # 3. With both AI and ML Available
    ml_pred = {"is_available": True, "bullish_pct": 85.0, "bearish_pct": 10.0}
    score_with_all = confluence_engine.fuse(cand, ai_result=ai_res, ml_prediction=ml_pred)
    assert score_with_all > 0.0
