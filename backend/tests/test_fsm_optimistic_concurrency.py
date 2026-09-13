"""
Phase 4 Tests: FSM Optimistic Concurrency & Pure Transition Architecture
Verifies:
  - Version increments deterministically on state transitions
  - Stale expected_version triggers optimistic concurrency conflict
  - apply_fsm_transition_pure produces deterministic state without manager dependencies
  - Multi-threaded transitions are serialized and thread-safe
"""
from decimal import Decimal
import threading
import pytest
from app.signals.fsm import (
    SignalFSMManager,
    SignalInstance,
    apply_fsm_transition_pure,
)


def _sample_signal() -> SignalInstance:
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
        fsm_state="ARMED",
        version=1,
    )


def test_version_increments_on_transition():
    fsm = SignalFSMManager()
    sig = _sample_signal()
    fsm._signals[sig.signal_id] = sig
    assert sig.version == 1

    ok, err = fsm.transition(sig.signal_id, "TRIGGERED")
    assert ok is True
    assert sig.version == 2

    ok, err = fsm.transition(sig.signal_id, "CONFIRMED")
    assert ok is True
    assert sig.version == 3


def test_optimistic_concurrency_conflict():
    fsm = SignalFSMManager()
    sig = _sample_signal()
    fsm._signals[sig.signal_id] = sig

    # Transition with correct expected version
    ok, err = fsm.transition(sig.signal_id, "TRIGGERED", expected_version=1)
    assert ok is True
    assert sig.version == 2

    # Attempt transition with stale expected version (1 instead of 2)
    ok, err = fsm.transition(sig.signal_id, "CONFIRMED", expected_version=1)
    assert ok is False
    assert "Optimistic concurrency conflict" in str(err)
    assert sig.fsm_state == "TRIGGERED"
    assert sig.version == 2


def test_pure_transition_function():
    sig = _sample_signal()
    assert sig.version == 1

    # Transition to TRIGGERED
    ok, err = apply_fsm_transition_pure(sig, "TRIGGERED", timestamp_ms=1000)
    assert ok is True
    assert sig.fsm_state == "TRIGGERED"
    assert sig.triggered_at_utc == 1000
    assert sig.version == 2

    # Illegal transition directly to CLOSED
    ok, err = apply_fsm_transition_pure(sig, "CLOSED")
    assert ok is False
    assert "Illegal transition" in str(err)
    assert sig.fsm_state == "TRIGGERED"
    assert sig.version == 2


def test_concurrent_transitions_thread_safety():
    fsm = SignalFSMManager()
    sig = _sample_signal()
    fsm._signals[sig.signal_id] = sig

    results = []

    def _worker(target_state, expected_v):
        ok, err = fsm.transition(sig.signal_id, target_state, expected_version=expected_v)
        results.append((target_state, ok, err))

    # Two concurrent attempts to transition from ARMED: one to TRIGGERED, one to INVALIDATED
    t1 = threading.Thread(target=_worker, args=("TRIGGERED", 1))
    t2 = threading.Thread(target=_worker, args=("INVALIDATED", 1))

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Exactly one must succeed with version 1, the other must fail with concurrency conflict or illegal transition
    succeeded = [r for r in results if r[1] is True]
    failed = [r for r in results if r[1] is False]
    assert len(succeeded) == 1
    assert len(failed) == 1
    assert "conflict" in str(failed[0][2]).lower() or "illegal" in str(failed[0][2]).lower()
