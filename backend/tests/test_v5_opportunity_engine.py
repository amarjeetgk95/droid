"""
DROID v5.1 Production-Hardened Opportunity Engine Test Suite
Verifies:
  - Fail-closed defaults on SignalInstance and ValidatedRiskDecision
  - Decoupling of Opportunity Intelligence (Market State) and Execution Feasibility
  - Blocked candidates preserve opportunity data, are paper/observation eligible, but cannot execute live (live_lots = 0)
  - Safety-blocked setups fail closed (observation_eligible = False, hypothetical_paper_lots = 0)
  - FSM state is not artificially promoted by execution constraints
  - Enabled workhorse strategies in STRATEGY_ENABLED
"""
from decimal import Decimal
import pytest

from app.signals.types import ExecutionStatus
from app.signals.fsm import SignalInstance
from app.signals.risk_engine import StrategySetup, ValidatedRiskDecision, CentralRiskEngine
from app.signals.pipeline.signal_factory import build_signal_instance
from app.signals.strategies.base import SignalCandidate
from app.signals.strategies import STRATEGY_ENABLED


def _make_candidate(
    strategy: str = "TREND_PULLBACK",
    direction: str = "LONG_CALL",
    spot: Decimal = Decimal("24000.0"),
    trigger: Decimal = Decimal("24020.0"),
    stop_loss: Decimal = Decimal("23995.0"),
    confidence: float = 75.0,
) -> SignalCandidate:
    risk_pts = abs(trigger - stop_loss)
    t1 = trigger + (risk_pts * Decimal("1.5")) if direction == "LONG_CALL" else trigger - (risk_pts * Decimal("1.5"))
    t2 = trigger + (risk_pts * Decimal("2.0")) if direction == "LONG_CALL" else trigger - (risk_pts * Decimal("2.0"))
    return SignalCandidate(
        underlying="NIFTY",
        strategy=strategy,
        direction=direction,
        timeframe="5M",
        spot_price=spot,
        entry_min=trigger - Decimal("5.0"),
        entry_max=trigger + Decimal("5.0"),
        trigger=trigger,
        stop_loss=stop_loss,
        target_1=t1,
        target_2=t2,
        risk_points=risk_pts,
        risk_reward_t1=1.5,
        risk_reward_t2=2.0,
        confidence=confidence,
    )


def test_fail_closed_defaults():
    """Verify that defaults fail closed with no magic defaults or unearned scores."""
    sig = SignalInstance(
        underlying="NIFTY",
        strategy="TEST",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("24000.0"),
        entry_min=Decimal("24010.0"),
        entry_max=Decimal("24020.0"),
        trigger=Decimal("24015.0"),
        stop_loss=Decimal("23990.0"),
        target_1=Decimal("24050.0"),
        target_2=Decimal("24080.0"),
        risk_points=Decimal("25.0"),
        risk_reward_t1=1.4,
        risk_reward_t2=2.6,
        confidence=65.0,
    )
    assert sig.opportunity_score is None, "opportunity_score must default to None"
    assert sig.execution_score is None, "execution_score must default to None"
    assert sig.live_executable is False, "live_executable must default to False"
    assert sig.paper_eligible is False, "paper_eligible must default to False"
    assert sig.observation_eligible is False, "observation_eligible must default to False"
    assert sig.execution_status == "SAFETY_BLOCKED", "execution_status must default to SAFETY_BLOCKED"
    assert sig.live_lots == 0, "live_lots must default to 0"
    assert sig.hypothetical_paper_lots == 0, "hypothetical_paper_lots must default to 0"

    dec = ValidatedRiskDecision(
        accepted=False,
        rejection_reason="DEFAULT_TEST",
        entry_price=Decimal("24015.0"),
        stop_loss=Decimal("23990.0"),
        target_1=Decimal("24050.0"),
        target_2=Decimal("24080.0"),
        risk_points=25.0,
        reward_t1_points=35.0,
        reward_t2_points=65.0,
        risk_reward_t1=1.4,
        risk_reward_t2=2.6,
        trigger_ttl_seconds=300,
        active_time_stop_seconds=900,
        lots=0,
        quantity=0,
        max_rupee_loss=0.0,
        lot_size=75,
    )
    assert dec.opportunity_score is None
    assert dec.live_executable is False
    assert dec.paper_eligible is False
    assert dec.observation_eligible is False
    assert dec.execution_status == "SAFETY_BLOCKED"
    assert dec.live_lots == 0
    assert dec.hypothetical_paper_lots == 0


def test_blocked_candidate_cannot_execute_live():
    """Candidates failing capital sizing are blocked from live execution but preserved for paper/observation."""
    engine = CentralRiskEngine()
    setup = StrategySetup(
        strategy_name="TREND_PULLBACK",
        underlying="NIFTY",
        direction="LONG_CALL",
        timeframe="5M",
        is_scalp=False,
        spot_price=Decimal("24000.0"),
        entry_trigger=Decimal("24020.0"),
        raw_structural_stop=Decimal("23995.0"),  # 25 pts risk
        structural_target_candidates=[Decimal("24060.0"), Decimal("24100.0")],
        atr_5m=Decimal("20.0"),
        confidence=72.0,
    )

    # ₹10,000 capital with 1% risk = ₹100 max risk.
    # 25 pts index stop * 0.50 delta = 12.5 pts option stop * 75 lot_size = ₹937.50 risk per lot.
    # ₹100 / ₹937.50 = 0 lots -> INSUFFICIENT_CAPITAL_FOR_1_LOT.
    decision = engine.evaluate(
        setup=setup,
        available_capital=10000.0,
        risk_per_trade_pct=1.0,
        allow_closed_market=True,
    )

    assert decision.accepted is False
    assert decision.live_executable is False, "Must not be live executable"
    assert decision.live_lots == 0, "Live lots must be 0"
    assert decision.paper_eligible is True, "Must be paper eligible"
    assert decision.hypothetical_paper_lots == 1, "Hypothetical paper lots must be 1"
    assert decision.observation_eligible is True, "Must be observation eligible"
    assert decision.execution_status == "BLOCKED_CAPITAL"
    assert "INSUFFICIENT_CAPITAL_FOR_1_LOT" in decision.rejection_reason

    # Build SignalInstance to verify taxonomy propagation
    cand = _make_candidate(
        strategy="TREND_PULLBACK",
        direction="LONG_CALL",
        spot=Decimal("24000.0"),
        trigger=Decimal("24020.0"),
        stop_loss=Decimal("23995.0"),
        confidence=72.0,
    )
    sig = build_signal_instance(
        cand=cand,
        fused_score=72.0,
        fsm_init_state="ARMED",
        risk_decision=decision,
        inst_overlay={},
        ai_advice=None,
        ml_pred=None,
        overlay=None,
        explain_bundle=None,
        fno_is_degraded=False,
    )

    assert sig.live_executable is False
    assert sig.live_lots == 0
    assert sig.paper_eligible is True
    assert sig.hypothetical_paper_lots == 1
    assert sig.observation_eligible is True
    assert sig.execution_status == "BLOCKED_CAPITAL"
    assert sig.fsm_state == "ARMED", "Market state remains ARMED while execution is BLOCKED"


def test_safety_blocked_candidate_fails_closed():
    """True safety invariant violation (e.g. inverted stop) fails closed completely."""
    engine = CentralRiskEngine()
    setup = StrategySetup(
        strategy_name="TREND_PULLBACK",
        underlying="NIFTY",
        direction="LONG_CALL",
        timeframe="5M",
        is_scalp=False,
        spot_price=Decimal("24000.0"),
        entry_trigger=Decimal("24020.0"),
        raw_structural_stop=Decimal("24030.0"),  # INVALID: SL above entry for CALL
        structural_target_candidates=[Decimal("24080.0")],
        atr_5m=Decimal("20.0"),
        confidence=75.0,
    )
    decision = engine.evaluate(setup=setup, allow_closed_market=True)
    assert decision.accepted is False
    assert decision.live_executable is False
    assert decision.paper_eligible is False
    assert decision.observation_eligible is False
    assert decision.execution_status == "SAFETY_BLOCKED"
    assert decision.live_lots == 0
    assert decision.hypothetical_paper_lots == 0
    assert "INVALID_STOP_ORIENTATION" in decision.rejection_reason


def test_structural_risk_exceeds_envelope():
    """Wide stop (> 35 pts on NIFTY 5m) is blocked from live execution but observed with raw stop intact."""
    engine = CentralRiskEngine()
    setup = StrategySetup(
        strategy_name="VOLATILITY_BREAKOUT",
        underlying="NIFTY",
        direction="LONG_CALL",
        timeframe="5M",
        is_scalp=False,
        spot_price=Decimal("24000.0"),
        entry_trigger=Decimal("24020.0"),
        raw_structural_stop=Decimal("23970.0"),  # 50 pts risk > 35 max allowed
        structural_target_candidates=[Decimal("24120.0")],
        atr_5m=Decimal("20.0"),
        confidence=80.0,
    )
    decision = engine.evaluate(setup=setup, allow_closed_market=True)
    assert decision.accepted is False
    assert decision.live_executable is False
    assert decision.paper_eligible is True
    assert decision.observation_eligible is True
    assert decision.execution_status == "BLOCKED_ENVELOPE"
    assert decision.live_lots == 0
    assert decision.hypothetical_paper_lots == 1
    # Critical invariant: stop loss was NOT clamped inward to an arbitrary value
    assert decision.stop_loss == Decimal("23970.0"), "Structural stop must be preserved"


def test_fsm_decoupling_market_state_not_promoted():
    """A low-score candidate (score < 60) blocked by capital must remain VALIDATED, not promoted to ARMED."""
    cand = _make_candidate(
        strategy="MEAN_REVERSION",
        direction="LONG_CALL",
        spot=Decimal("24000.0"),
        trigger=Decimal("24020.0"),
        stop_loss=Decimal("23995.0"),
        confidence=45.0,
    )
    risk_dec = ValidatedRiskDecision(
        accepted=False,
        rejection_reason="INSUFFICIENT_CAPITAL_FOR_1_LOT: Budget ₹500 cannot absorb ₹938 risk per lot",
        entry_price=Decimal("24020.0"),
        stop_loss=Decimal("23995.0"),
        target_1=Decimal("24060.0"),
        target_2=Decimal("24100.0"),
        risk_points=25.0,
        reward_t1_points=40.0,
        reward_t2_points=80.0,
        risk_reward_t1=1.6,
        risk_reward_t2=3.2,
        trigger_ttl_seconds=300,
        active_time_stop_seconds=900,
        lots=0,
        quantity=0,
        max_rupee_loss=0.0,
        lot_size=75,
        live_executable=False,
        paper_eligible=True,
        observation_eligible=True,
        execution_status="BLOCKED_CAPITAL",
        execution_blocked_reason="INSUFFICIENT_CAPITAL_FOR_1_LOT",
        live_lots=0,
        hypothetical_paper_lots=1,
    )
    sig = build_signal_instance(
        cand=cand,
        fused_score=45.0,
        fsm_init_state="VALIDATED",  # Score 45 < 60 threshold
        risk_decision=risk_dec,
        inst_overlay={},
        ai_advice=None,
        ml_pred=None,
        overlay=None,
        explain_bundle=None,
        fno_is_degraded=False,
    )
    assert sig.fsm_state == "VALIDATED", "Developing setup must not be promoted to ARMED"
    assert sig.execution_status == "BLOCKED_CAPITAL"
    assert sig.live_lots == 0
    assert sig.hypothetical_paper_lots == 1


def test_accepted_trade_is_live_executable():
    """A setup with sufficient capital and within envelope ceilings is live executable."""
    engine = CentralRiskEngine()
    setup = StrategySetup(
        strategy_name="TREND_PULLBACK",
        underlying="NIFTY",
        direction="LONG_CALL",
        timeframe="5M",
        is_scalp=False,
        spot_price=Decimal("24000.0"),
        entry_trigger=Decimal("24020.0"),
        raw_structural_stop=Decimal("23995.0"),  # 25 pts risk
        structural_target_candidates=[Decimal("24060.0"), Decimal("24100.0")],
        atr_5m=Decimal("20.0"),
        confidence=80.0,
    )
    decision = engine.evaluate(
        setup=setup,
        available_capital=500000.0,  # ₹5,00,000 capital
        risk_per_trade_pct=1.0,
        allow_closed_market=True,
    )
    assert decision.accepted is True
    assert decision.live_executable is True
    assert decision.paper_eligible is True
    assert decision.observation_eligible is True
    assert decision.execution_status == "LIVE_EXECUTABLE"
    assert decision.live_lots >= 1
    assert decision.hypothetical_paper_lots == decision.live_lots
    assert decision.execution_blocked_reason is None


def test_enabled_workhorse_strategies():
    """Verify that the 4 workhorse strategies are enabled alongside the core keepers."""
    expected_active = [
        "VOLATILITY_BREAKOUT",
        "BREAKOUT",
        "ORB",
        "VWAP_SCALP",
        "TREND_PULLBACK",
        "MEAN_REVERSION",
        "MICRO_MOMENTUM",
        "MOMENTUM_REACCELERATION",
    ]
    for strat in expected_active:
        assert STRATEGY_ENABLED.get(strat) is True, f"Strategy {strat} must be enabled"
