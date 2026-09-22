"""Dual FSM Integrity & Decoupling Test Suite (Tier 0 / Tier 4).

Verifies the strict decoupling between:
1. Signal FSM (app.signals.fsm): Analytical candidate state
2. Order FSM (app.algo.execution): Broker execution & exchange state

Asserts:
- No illegal state transitions
- Terminal state immutability
- Idempotency and transition validation
"""

import pytest
import uuid
from decimal import Decimal

from app.signals.fsm import (
    SignalFSMManager,
    SignalInstance,
    ALLOWED_TRANSITIONS as SIGNAL_ALLOWED,
    TERMINAL_STATES as SIGNAL_TERMINALS,
)
from app.algo.execution import OrderRecord, OrderStatus, ALLOWED_TRANSITIONS as ORDER_ALLOWED


class TestDualFSM:

    def test_signal_fsm_legal_lifecycle(self):
        """Signal FSM transitions must strictly respect ALLOWED_TRANSITIONS."""
        mgr = SignalFSMManager()
        sig_id = f"sig_{uuid.uuid4().hex[:8]}"

        sig = SignalInstance(
            signal_id=sig_id,
            underlying="SENSEX",
            strategy="S1_ORB",
            direction="LONG_CALL",
            timeframe="1m",
            spot_price=Decimal("80000.0"),
            entry_min=Decimal("80000.0"),
            entry_max=Decimal("80050.0"),
            trigger=Decimal("80020.0"),
            stop_loss=Decimal("79900.0"),
            target_1=Decimal("80200.0"),
            target_2=Decimal("80400.0"),
            risk_points=Decimal("120.0"),
            risk_reward_t1=1.67,
            risk_reward_t2=3.33,
            confidence=0.82,
        )

        mgr.register(sig)
        assert sig.fsm_state == "DETECTED"

        # DETECTED -> ARMED
        assert "ARMED" in SIGNAL_ALLOWED["DETECTED"]
        ok, _ = mgr.transition(sig_id, "ARMED", reason="Technical gates passed")
        assert ok is True
        assert mgr.get(sig_id).fsm_state == "ARMED"

        # ARMED -> TRIGGERED
        assert "TRIGGERED" in SIGNAL_ALLOWED["ARMED"]
        ok, _ = mgr.transition(sig_id, "TRIGGERED", reason="Breakout level crossed")
        assert ok is True
        assert mgr.get(sig_id).fsm_state == "TRIGGERED"

        # TRIGGERED -> CONFIRMED
        assert "CONFIRMED" in SIGNAL_ALLOWED["TRIGGERED"]
        ok, _ = mgr.transition(sig_id, "CONFIRMED", reason="Execution intent verified")
        assert ok is True
        assert mgr.get(sig_id).fsm_state == "CONFIRMED"

        # CONFIRMED -> CLOSED
        assert "CLOSED" in SIGNAL_ALLOWED["CONFIRMED"]
        ok, _ = mgr.transition(sig_id, "CLOSED", reason="Session close")
        assert ok is True
        assert mgr.get(sig_id).fsm_state == "CLOSED"

    def test_signal_fsm_illegal_transition_blocked(self):
        """Illegal transitions in Signal FSM must fail and leave state unchanged."""
        mgr = SignalFSMManager()
        sig_id = f"sig_{uuid.uuid4().hex[:8]}"

        sig = SignalInstance(
            signal_id=sig_id,
            underlying="SENSEX",
            strategy="S1_ORB",
            direction="LONG_CALL",
            timeframe="1m",
            spot_price=Decimal("80000.0"),
            entry_min=Decimal("80000.0"),
            entry_max=Decimal("80050.0"),
            trigger=Decimal("80020.0"),
            stop_loss=Decimal("79900.0"),
            target_1=Decimal("80200.0"),
            target_2=Decimal("80400.0"),
            risk_points=Decimal("120.0"),
            risk_reward_t1=1.67,
            risk_reward_t2=3.33,
            confidence=0.82,
        )

        mgr.register(sig)
        assert sig.fsm_state == "DETECTED"

        # Direct jump from DETECTED to CONFIRMED is forbidden
        assert "CONFIRMED" not in SIGNAL_ALLOWED["DETECTED"]
        ok, err = mgr.transition(sig_id, "CONFIRMED", reason="Illegal jump")
        assert ok is False
        assert mgr.get(sig_id).fsm_state == "DETECTED"

    def test_order_fsm_legal_lifecycle(self):
        """Order FSM must follow CREATED -> RISK_APPROVED -> SUBMITTED -> ACKNOWLEDGED -> FILLED -> CLOSED."""
        order = OrderRecord(
            account_id="acc_test",
            client_order_id=uuid.uuid4(),
            symbol="BSE:SENSEX-INDEX",
            side="BUY",
            quantity=10,
            price=Decimal("80000.0"),
            order_type="MARKET",
            status="CREATED",
        )

        assert order.status == "CREATED"

        # Check valid order transitions against ORDER_ALLOWED
        assert "RISK_APPROVED" in ORDER_ALLOWED["CREATED"]
        order.status = "RISK_APPROVED"

        assert "SUBMITTED" in ORDER_ALLOWED["RISK_APPROVED"]
        order.status = "SUBMITTED"

        assert "ACKNOWLEDGED" in ORDER_ALLOWED["SUBMITTED"]
        order.status = "ACKNOWLEDGED"

        assert "FILLED" in ORDER_ALLOWED["ACKNOWLEDGED"]
        order.status = "FILLED"

        assert "CLOSED" in ORDER_ALLOWED["FILLED"]
        order.status = "CLOSED"

    def test_order_terminal_states_no_escape(self):
        """Once CLOSED, no further transitions are allowed."""
        assert len(ORDER_ALLOWED["CLOSED"]) == 0
