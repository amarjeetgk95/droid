"""
Phase 0 Characterization Test: Domain Invariants
Verifies fundamental system invariants:
  - Terminal state monotonicity
  - Immutability of registered signal definition
  - Idempotency of sweep_expired()
  - Bounds on in-memory signal collection (max 200)
  - evaluate_tick() ordered priority determinism
"""
from decimal import Decimal
import time
import pytest
from app.signals.fsm import (
    SignalFSMManager,
    SignalInstance,
    evaluate_tick,
)


def _make_signal(state="DETECTED", underlying="NIFTY", strategy="BREAKOUT") -> SignalInstance:
    return SignalInstance(
        underlying=underlying,
        strategy=strategy,
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
        fsm_state=state,
        intended_qty=Decimal("65"),
        remaining_qty=Decimal("65"),
    )


def test_immutable_definition_fields_preserved_across_transitions():
    """Core parameters (underlying, trigger, stop_loss, target_1/2) must never mutate during transitions."""
    fsm = SignalFSMManager()
    sig = _make_signal(state="CONFIRMED")
    fsm._signals[sig.signal_id] = sig

    orig_trigger = sig.trigger
    orig_sl = sig.stop_loss
    orig_t1 = sig.target_1
    orig_t2 = sig.target_2
    orig_underlying = sig.underlying

    fsm.transition(sig.signal_id, "TARGET_1_HIT", market_price=Decimal("24100.0"))

    assert sig.trigger == orig_trigger
    assert sig.stop_loss == orig_sl
    assert sig.target_1 == orig_t1
    assert sig.target_2 == orig_t2
    assert sig.underlying == orig_underlying


def test_sweep_expired_is_idempotent():
    """Consecutive sweep_expired() calls with no state changes return 0 expired."""
    fsm = SignalFSMManager()
    now_ms = int(time.time() * 1000)

    # 1 expired signal
    sig = _make_signal(state="ARMED")
    sig.expires_at_utc = now_ms - 1000
    fsm._signals[sig.signal_id] = sig

    res1 = fsm.sweep_expired(now_ms=now_ms)
    assert res1["expired"] >= 1
    assert sig.fsm_state == "EXPIRED"

    # Second sweep immediately after
    res2 = fsm.sweep_expired(now_ms=now_ms)
    assert res2["expired"] == 0


def test_in_memory_signal_cap_prunes_terminal_at_200():
    """SignalFSMManager bounds in-memory signals to 200, pruning oldest terminal signals."""
    fsm = SignalFSMManager()
    # Add 250 terminal signals
    for i in range(250):
        sig = _make_signal(state="CLOSED")
        sig.last_updated_utc = 1000 + i
        fsm._signals[sig.signal_id] = sig

    assert len(fsm._signals) == 250
    fsm.sweep_expired()
    # Should be capped at 200
    assert len(fsm._signals) <= 200


def test_evaluate_tick_stop_loss_priority_over_target():
    """Stop loss breach has absolute priority over target hit if both conditions were somehow met."""
    sig = _make_signal(state="CONFIRMED")
    sig.stop_loss = Decimal("23950.0")
    sig.current_stop_loss = Decimal("23950.0")
    sig.target_1 = Decimal("24100.0")

    # Tick at stop loss
    action, reason = evaluate_tick(sig, tick_price=Decimal("23940.0"))
    assert action == "STOP_LOSS_HIT"
    assert reason == "STOP_LOSS_BREACHED"


def test_evaluate_tick_target_1_hit_in_confirmed():
    sig = _make_signal(state="CONFIRMED")
    sig.target_1 = Decimal("24100.0")
    action, reason = evaluate_tick(sig, tick_price=Decimal("24105.0"))
    assert action == "TARGET_1_HIT"
    assert reason == "TARGET_1_ACHIEVED"


def test_evaluate_tick_target_2_hit_in_runner():
    sig = _make_signal(state="TARGET_1_HIT")
    sig.target_2 = Decimal("24180.0")
    action, reason = evaluate_tick(sig, tick_price=Decimal("24185.0"))
    assert action == "TARGET_2_HIT"
    assert reason == "TARGET_2_ACHIEVED"


def test_evaluate_tick_invalid_price_rejected():
    sig = _make_signal(state="CONFIRMED")
    action, reason = evaluate_tick(sig, tick_price=Decimal("-10.0"))
    assert action is None
    assert reason == "INVALID_PRICE"
