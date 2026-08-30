"""
Execution State Machine — §28

States:
SIGNAL_CREATED, ORDER_SUBMITTED, ACKNOWLEDGED, PARTIALLY_FILLED, FILLED,
OCO_ACTIVE, TARGET_TRIGGERED, STOP_TRIGGERED, CANCEL_PENDING, CANCELLED,
REJECTED, TIMEOUT, BROKER_DISCONNECTED, RECONCILIATION_REQUIRED, CLOSED

Must be idempotent. Duplicate broker events must not create duplicate orders/positions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid

from pydantic import BaseModel, Field


class ExecutionState(str, Enum):
    SIGNAL_CREATED = "SIGNAL_CREATED"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    OCO_ACTIVE = "OCO_ACTIVE"
    TARGET_TRIGGERED = "TARGET_TRIGGERED"
    STOP_TRIGGERED = "STOP_TRIGGERED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    TIMEOUT = "TIMEOUT"
    BROKER_DISCONNECTED = "BROKER_DISCONNECTED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    CLOSED = "CLOSED"


# Allowed transitions (directed graph) — ensures deterministic lifecycle
ALLOWED_TRANSITIONS: dict[ExecutionState, set[ExecutionState]] = {
    ExecutionState.SIGNAL_CREATED: {ExecutionState.ORDER_SUBMITTED, ExecutionState.REJECTED, ExecutionState.CANCELLED},
    ExecutionState.ORDER_SUBMITTED: {ExecutionState.ACKNOWLEDGED, ExecutionState.REJECTED, ExecutionState.TIMEOUT, ExecutionState.BROKER_DISCONNECTED, ExecutionState.CANCEL_PENDING},
    ExecutionState.ACKNOWLEDGED: {ExecutionState.PARTIALLY_FILLED, ExecutionState.FILLED, ExecutionState.REJECTED, ExecutionState.CANCEL_PENDING, ExecutionState.TIMEOUT},
    ExecutionState.PARTIALLY_FILLED: {ExecutionState.FILLED, ExecutionState.CANCEL_PENDING, ExecutionState.TIMEOUT, ExecutionState.BROKER_DISCONNECTED, ExecutionState.RECONCILIATION_REQUIRED},
    ExecutionState.FILLED: {ExecutionState.OCO_ACTIVE, ExecutionState.CLOSED, ExecutionState.RECONCILIATION_REQUIRED},
    ExecutionState.OCO_ACTIVE: {ExecutionState.TARGET_TRIGGERED, ExecutionState.STOP_TRIGGERED, ExecutionState.CANCEL_PENDING, ExecutionState.RECONCILIATION_REQUIRED, ExecutionState.BROKER_DISCONNECTED},
    ExecutionState.TARGET_TRIGGERED: {ExecutionState.CLOSED, ExecutionState.RECONCILIATION_REQUIRED},
    ExecutionState.STOP_TRIGGERED: {ExecutionState.CLOSED, ExecutionState.RECONCILIATION_REQUIRED},
    ExecutionState.CANCEL_PENDING: {ExecutionState.CANCELLED, ExecutionState.RECONCILIATION_REQUIRED, ExecutionState.TIMEOUT},
    ExecutionState.CANCELLED: {ExecutionState.CLOSED, ExecutionState.RECONCILIATION_REQUIRED},
    ExecutionState.REJECTED: {ExecutionState.CLOSED, ExecutionState.RECONCILIATION_REQUIRED},
    ExecutionState.TIMEOUT: {ExecutionState.RECONCILIATION_REQUIRED, ExecutionState.CANCEL_PENDING, ExecutionState.CLOSED},
    ExecutionState.BROKER_DISCONNECTED: {ExecutionState.RECONCILIATION_REQUIRED, ExecutionState.TIMEOUT, ExecutionState.CANCEL_PENDING},
    ExecutionState.RECONCILIATION_REQUIRED: {ExecutionState.CLOSED, ExecutionState.FILLED, ExecutionState.CANCELLED, ExecutionState.REJECTED},
    ExecutionState.CLOSED: set(),  # terminal
}


class ExecutionOrder(BaseModel):
    order_id: str = Field(default_factory=lambda: f"ORD-{uuid.uuid4().hex[:8].upper()}")
    analysis_id: str = Field(description="Correlation ID §40")
    symbol: str
    side: str  # BUY/SELL
    quantity: int
    state: ExecutionState = ExecutionState.SIGNAL_CREATED
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    state_version: int | None = None
    pricing: dict[str, Any] | None = None
    broker_order_id: str | None = None
    fill_quantity: int = 0
    avg_fill_price: float | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    # Idempotency: processed event IDs
    processed_event_ids: set[str] = Field(default_factory=set)


class ExecutionStateMachine:
    """
    Idempotent state machine. Duplicate broker events (same event_id) are ignored.
    """

    def __init__(self):
        self._orders: dict[str, ExecutionOrder] = {}

    def create_signal(self, symbol: str, side: str, quantity: int, analysis_id: str, state_version: int | None = None, pricing: dict | None = None) -> ExecutionOrder:
        order = ExecutionOrder(
            symbol=symbol,
            side=side,
            quantity=quantity,
            analysis_id=analysis_id,
            state=ExecutionState.SIGNAL_CREATED,
            state_version=state_version,
            pricing=pricing,
        )
        self._orders[order.order_id] = order
        order.events.append({"state": order.state.value, "at": order.created_at.isoformat(), "event_id": f"evt-{uuid.uuid4().hex[:6]}"})
        return order

    def get_order(self, order_id: str) -> ExecutionOrder | None:
        return self._orders.get(order_id)

    def list_orders(self) -> list[ExecutionOrder]:
        return list(self._orders.values())

    def transition(self, order_id: str, to_state: ExecutionState, event_id: str | None = None, metadata: dict[str, Any] | None = None) -> ExecutionOrder:
        order = self._orders.get(order_id)
        if not order:
            raise ValueError(f"order {order_id} not found")

        # Idempotency: if event_id already processed, return current without transition
        if event_id and event_id in order.processed_event_ids:
            return order

        # Validate transition allowed (unless same state – idempotent)
        if order.state == to_state:
            if event_id:
                order.processed_event_ids.add(event_id)
            return order

        allowed = ALLOWED_TRANSITIONS.get(order.state, set())
        if to_state not in allowed:
            raise ValueError(f"illegal transition {order.state.value} → {to_state.value}. Allowed: {[s.value for s in allowed]}")

        order.state = to_state
        order.updated_at = datetime.now(timezone.utc)
        if event_id:
            order.processed_event_ids.add(event_id)
        order.events.append({"state": to_state.value, "at": order.updated_at.isoformat(), "event_id": event_id or f"evt-{uuid.uuid4().hex[:6]}", "metadata": metadata or {}})
        # Broker-specific metadata
        if metadata:
            if "broker_order_id" in metadata:
                order.broker_order_id = metadata["broker_order_id"]
            if "fill_quantity" in metadata:
                order.fill_quantity = int(metadata["fill_quantity"])
            if "avg_fill_price" in metadata:
                order.avg_fill_price = float(metadata["avg_fill_price"])
        return order

    def handle_broker_event(self, order_id: str, event_type: str, event_id: str, payload: dict[str, Any] | None = None) -> ExecutionOrder:
        """
        Map broker event types to state transitions.
        Must be idempotent.
        """
        payload = payload or {}
        mapping = {
            "ACK": ExecutionState.ACKNOWLEDGED,
            "PARTIAL_FILL": ExecutionState.PARTIALLY_FILLED,
            "FILL": ExecutionState.FILLED,
            "REJECT": ExecutionState.REJECTED,
            "CANCEL": ExecutionState.CANCELLED,
            "TIMEOUT": ExecutionState.TIMEOUT,
            "DISCONNECT": ExecutionState.BROKER_DISCONNECTED,
            "OCO_ACTIVE": ExecutionState.OCO_ACTIVE,
            "TARGET_HIT": ExecutionState.TARGET_TRIGGERED,
            "STOP_HIT": ExecutionState.STOP_TRIGGERED,
        }
        to_state = mapping.get(event_type.upper())
        if not to_state:
            raise ValueError(f"unknown broker event {event_type}")
        return self.transition(order_id, to_state, event_id=event_id, metadata=payload)


# Singleton
execution_state_machine = ExecutionStateMachine()
