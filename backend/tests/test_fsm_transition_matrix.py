"""
Phase 0 Characterization Test: Exhaustive 13-State FSM Transition Matrix
Tests all 13 x 13 = 169 state transitions to freeze current FSM behavior.
"""
from decimal import Decimal
import pytest
from app.signals.fsm import (
    ALLOWED_TRANSITIONS,
    SignalFSMManager,
    SignalInstance,
    SignalFSMState,
)

ALL_STATES: list[SignalFSMState] = [
    "DETECTED",
    "VALIDATED",
    "ARMED",
    "TRIGGERED",
    "CONFIRMED",
    "TARGET_1_HIT",
    "TARGET_2_HIT",
    "STOP_LOSS_HIT",
    "TIME_STOP_HIT",
    "RUNNER_TIME_STOP_HIT",
    "INVALIDATED",
    "EXPIRED",
    "CLOSED",
]


def _create_dummy_signal(initial_state: SignalFSMState, fno_degraded: bool = False) -> SignalInstance:
    sig = SignalInstance(
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
        confluence_breakdown={"fno_degraded": fno_degraded},
        fsm_state=initial_state,
    )
    return sig


def test_transition_matrix_completeness():
    """Verify ALLOWED_TRANSITIONS defines sets for all 13 states."""
    assert len(ALL_STATES) == 13
    assert set(ALLOWED_TRANSITIONS.keys()) == set(ALL_STATES)


def test_terminal_states_only_allow_closed():
    """Verify terminal states can only transition to CLOSED, and CLOSED has no exits."""
    terminal_to_closed = {
        "TARGET_2_HIT",
        "STOP_LOSS_HIT",
        "TIME_STOP_HIT",
        "RUNNER_TIME_STOP_HIT",
        "INVALIDATED",
        "EXPIRED",
    }
    for state in terminal_to_closed:
        assert ALLOWED_TRANSITIONS[state] == {"CLOSED"}, f"{state} should only transition to CLOSED"

    assert ALLOWED_TRANSITIONS["CLOSED"] == set(), "CLOSED must be strictly terminal"


@pytest.mark.parametrize("from_state", ALL_STATES)
@pytest.mark.parametrize("to_state", ALL_STATES)
def test_all_169_fsm_transition_pairs(from_state: SignalFSMState, to_state: SignalFSMState):
    """
    Exhaustively test all 169 state pairs against SignalFSMManager.transition().
    Ensures exact compliance with ALLOWED_TRANSITIONS.
    """
    fsm = SignalFSMManager()
    sig = _create_dummy_signal(from_state, fno_degraded=False)
    fsm._signals[sig.signal_id] = sig

    ok, err = fsm.transition(sig.signal_id, to_state, market_price=Decimal("24050.0"))

    if from_state == to_state:
        # Reflexive transitions return True, None (noop)
        assert ok is True
        assert err is None
        assert sig.fsm_state == to_state
    elif to_state in ALLOWED_TRANSITIONS[from_state]:
        assert ok is True
        assert err is None
        assert sig.fsm_state == to_state
    else:
        assert ok is False
        assert f"Illegal transition {from_state} -> {to_state}" in str(err)
        assert sig.fsm_state == from_state


def test_fno_degraded_guard_blocks_arm_trigger_confirm():
    """Verify degraded F&O data blocks transitions to ARMED, TRIGGERED, CONFIRMED."""
    for target in ("ARMED", "TRIGGERED", "CONFIRMED"):
        fsm = SignalFSMManager()
        # DETECTED can transition to ARMED/CONFIRMED if not degraded
        sig = _create_dummy_signal("DETECTED", fno_degraded=True)
        fsm._signals[sig.signal_id] = sig
        if target in ALLOWED_TRANSITIONS["DETECTED"]:
            ok, err = fsm.transition(sig.signal_id, target)
            assert ok is False
            assert err == "FNO_DATA_DEGRADED_CANNOT_ARM"
            assert sig.fsm_state == "DETECTED"
