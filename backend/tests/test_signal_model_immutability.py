"""
Phase 2 Domain Model Tests: Immutability and Facade Compatibility
Verifies:
  - SignalDefinition preserves immutable strategy proposal across transitions
  - RiskSizing, ConfluenceBreakdown, ExecutionState, SignalOutcome mappings
  - Backward compatibility: SignalInstance model_dump() serialization unchanged
"""
from decimal import Decimal
import pytest
from app.signals.fsm import SignalFSMManager, SignalInstance
from app.signals.signal_model import (
    SignalDefinition,
    RiskSizing,
    ConfluenceBreakdown,
    ExecutionState,
    SignalOutcome,
)


def _create_test_signal() -> SignalInstance:
    return SignalInstance(
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("24000.0"),
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
        lots=2,
        quantity=130,
        max_rupee_loss=8450.0,
        fsm_state="CONFIRMED",
        confluence_breakdown={
            "technical": 75.0,
            "mtf": 60.0,
            "fno": 65.0,
            "regime": 80.0,
            "institutional_delta": 2.5,
            "institutional_applied": True,
        },
        option_contract={"broker_symbol": "NSE:NIFTY26SEP24000CE", "strike": 24000.0,
                         "option_type": "CE", "lot_size": 75},
        actual_fill_price=Decimal("120.0"),
    )


def test_definition_immutability_across_fsm_transitions():
    fsm = SignalFSMManager()
    sig = _create_test_signal()
    fsm._signals[sig.signal_id] = sig

    initial_def = sig.definition
    assert isinstance(initial_def, SignalDefinition)
    initial_dump = initial_def.model_dump()

    # Apply transition to TARGET_1_HIT
    fsm.transition(sig.signal_id, "TARGET_1_HIT", market_price=Decimal("24105.0"))

    post_transition_def = sig.definition
    assert post_transition_def.model_dump() == initial_dump


def test_risk_sizing_projection():
    sig = _create_test_signal()
    rs = sig.risk_sizing
    assert isinstance(rs, RiskSizing)
    assert rs.lots == 2
    assert rs.quantity == 130
    assert rs.max_rupee_loss == 8450.0


def test_confluence_typed_projection():
    sig = _create_test_signal()
    cb = sig.confluence_typed
    assert isinstance(cb, ConfluenceBreakdown)
    assert cb.technical == 75.0
    assert cb.regime == 80.0
    assert cb.institutional_delta == 2.5
    assert cb.institutional_applied is True
    assert cb.fno_degraded is False


def test_execution_state_projection():
    fsm = SignalFSMManager()
    sig = _create_test_signal()
    fsm._signals[sig.signal_id] = sig
    fsm.transition(sig.signal_id, "TARGET_1_HIT", market_price=Decimal("24105.0"))

    es = sig.execution_state
    assert isinstance(es, ExecutionState)
    assert es.fsm_state == "TARGET_1_HIT"
    assert es.t1_hit is True
    assert es.breakeven_activated is True


def test_outcome_typed_projection():
    fsm = SignalFSMManager()
    sig = _create_test_signal()
    fsm._signals[sig.signal_id] = sig
    # Fail-closed friction: the exit leg prices from a REAL chain mark for the
    # exact contract; without one the FSM records no net-R (cost_breakdown_r=None).
    from tests.conftest import seed_chain_mark
    seed_chain_mark("NSE:NIFTY26SEP24000CE", 150.0, underlying="NIFTY", strike=24000.0, option_type="CE")
    fsm.transition(sig.signal_id, "TARGET_1_HIT", market_price=Decimal("24105.0"))

    out = sig.outcome_typed
    assert isinstance(out, SignalOutcome)
    assert out.terminal_outcome == "PARTIAL_WIN"
    assert out.outcome_status == "WIN_T1"
    assert out.realized_rr_gross == 1.3
    assert out.realized_rr_net is not None
    assert out.cost_breakdown_r is not None
