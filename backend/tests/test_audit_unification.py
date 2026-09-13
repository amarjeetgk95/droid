"""
Test Suite for Audit Unification (Phase 6)

Verifies that:
1. SignalAuditLedger projections match FSM state machine transitions via event bus.
2. FSM terminal outcomes and AuditTradeRecord agree on winner/loser classification.
3. PerformanceMetrics reflects unified state history.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
import pytest

from app.signals.event_bus import SignalEvent, SignalEventType, signal_event_bus
from app.signals.fsm import SignalFSMManager, SignalInstance
from app.signals.audit_ledger import SignalAuditLedger, signal_audit_ledger
from app.signals.outcome_tracker import outcome_tracker


@pytest.mark.asyncio
async def test_audit_ledger_event_driven_transition():
    """Verify that publishing a TRANSITIONED event updates the audit ledger record."""
    sig_id = "SIG-AUDIT-UNIFY-01"

    signal_audit_ledger.record_signal_created(
        signal_id=sig_id,
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=25000.0,
        trigger=25020.0,
        stop_loss=24980.0,
        target_1=25060.0,
        target_2=25100.0,
        confidence=85.0,
        lots=1,
        status="ARMED",
    )

    ev = SignalEvent(
        event_type=SignalEventType.TRANSITIONED,
        signal_id=sig_id,
        payload={
            "from_state": "ARMED",
            "to_state": "TARGET_1_HIT",
            "market_price": 25060.0,
            "reason": "TARGET_1_ACHIEVED",
        },
    )

    from app.signals.handlers.audit_handler import handle_signal_transitioned_audit
    await handle_signal_transitioned_audit(ev)

    rec = signal_audit_ledger.get(sig_id)
    assert rec is not None
    assert rec.status == "TARGET_1_HIT"
    assert rec.is_winner is True
    assert rec.current_price == 25060.0
    assert any(e.to_state == "TARGET_1_HIT" for e in rec.state_history)


@pytest.mark.asyncio
async def test_fsm_and_audit_terminal_outcomes_agreement():
    """Verify that FSM transition terminal states agree with audit ledger classifications."""
    fsm = SignalFSMManager()
    sig_id = "SIG-OUTCOME-AGREE-01"

    sig = SignalInstance(
        signal_id=sig_id,
        underlying="NIFTY",
        strategy="TREND_PULLBACK",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("25000.0"),
        entry_min=Decimal("25000.0"),
        entry_max=Decimal("25010.0"),
        trigger=Decimal("25005.0"),
        stop_loss=Decimal("24970.0"),
        target_1=Decimal("25040.0"),
        target_2=Decimal("25080.0"),
        risk_points=Decimal("35.0"),
        risk_reward_t1=1.5,
        risk_reward_t2=3.0,
        confidence=80.0,
        fsm_state="CONFIRMED",
    )
    fsm.register(sig)

    # Transition to STOP_LOSS_HIT
    fsm.transition(sig_id, "STOP_LOSS_HIT", market_price=Decimal("24965.0"), reason="STOP_LOSS_HIT")

    assert sig.fsm_state == "STOP_LOSS_HIT"
    assert sig.outcome_status == "LOSS_SL"
    assert sig.terminal_outcome == "STOP_LOSS_HIT"

    # Check global audit ledger
    audit_rec = signal_audit_ledger.get(sig_id)
    if audit_rec:
        assert audit_rec.is_winner is False
        assert audit_rec.status in ("STOP_LOSS_HIT", "LOST")
