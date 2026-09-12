"""
Position Model & Position Lifecycle FSM
Represents portfolio reality derived from actual broker or paper fills.
State flow:
  OPEN -> T1_PARTIAL_EXIT -> T2_EXIT / STOP_LOSS / TIME_STOP -> CLOSED
Strictly decoupled from Signal market analysis thesis.
"""
from __future__ import annotations

import time
import uuid
from decimal import Decimal
from enum import Enum
from typing import Any
import structlog
from pydantic import BaseModel, Field

from app.signals.safety.decimal_types import D

logger = structlog.get_logger()


class PositionState(str, Enum):
    OPEN = "OPEN"
    T1_PARTIAL_EXIT = "T1_PARTIAL_EXIT"
    T2_EXIT = "T2_EXIT"
    STOP_LOSS = "STOP_LOSS"
    TIME_STOP = "TIME_STOP"
    CLOSED = "CLOSED"


ALLOWED_POSITION_TRANSITIONS: dict[PositionState, set[PositionState]] = {
    PositionState.OPEN: {PositionState.T1_PARTIAL_EXIT, PositionState.T2_EXIT, PositionState.STOP_LOSS, PositionState.TIME_STOP, PositionState.CLOSED},
    PositionState.T1_PARTIAL_EXIT: {PositionState.T2_EXIT, PositionState.STOP_LOSS, PositionState.TIME_STOP, PositionState.CLOSED},
    PositionState.T2_EXIT: {PositionState.CLOSED},
    PositionState.STOP_LOSS: {PositionState.CLOSED},
    PositionState.TIME_STOP: {PositionState.CLOSED},
    PositionState.CLOSED: set(),
}


class Position(BaseModel):
    position_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    signal_id: str
    execution_intent_id: str
    broker_order_id: str | None = None

    underlying: str
    instrument_symbol: str
    side: str = "BUY"
    lot_size: int = 75

    entry_price: Decimal
    entry_quantity: int
    remaining_quantity: int

    t1_price: Decimal | None = None
    t1_quantity: int = 0
    t1_fill_price: Decimal | None = None

    exit_price: Decimal | None = None
    exit_reason: str | None = None

    gross_pnl_inr: Decimal = Decimal(0)
    statutory_costs_inr: Decimal = Decimal(0)
    net_pnl_inr: Decimal = Decimal(0)

    position_state: PositionState = PositionState.OPEN
    opened_at_utc: int = Field(default_factory=lambda: int(time.time() * 1000))
    closed_at_utc: int | None = None
    history: list[dict[str, Any]] = Field(default_factory=list)

    def transition_to(self, new_state: PositionState, reason: str = "", fill_price: Decimal | None = None) -> bool:
        if new_state not in ALLOWED_POSITION_TRANSITIONS.get(self.position_state, set()):
            logger.error(
                "illegal_position_transition",
                position_id=self.position_id,
                from_state=self.position_state,
                to_state=new_state,
                reason=reason,
            )
            return False

        old_state = self.position_state
        self.position_state = new_state
        now_ms = int(time.time() * 1000)
        self.history.append({
            "from_state": old_state.value,
            "to_state": new_state.value,
            "reason": reason,
            "fill_price": str(fill_price) if fill_price else None,
            "timestamp_utc": now_ms,
        })

        if new_state in (PositionState.T2_EXIT, PositionState.STOP_LOSS, PositionState.TIME_STOP, PositionState.CLOSED):
            self.closed_at_utc = now_ms
            if new_state != PositionState.CLOSED:
                # Auto-transition terminal exit stages to CLOSED
                self.position_state = PositionState.CLOSED
                self.history.append({
                    "from_state": new_state.value,
                    "to_state": PositionState.CLOSED.value,
                    "reason": "TERMINAL_STATE_FINALIZED",
                    "timestamp_utc": now_ms,
                })

        logger.info(
            "position_transition",
            position_id=self.position_id,
            signal_id=self.signal_id,
            to_state=self.position_state.value,
            reason=reason,
        )
        return True


class PositionRegistry:
    """
    Registry for active and historical positions.
    """
    def __init__(self):
        self._positions: dict[str, Position] = {}

    def register(self, position: Position) -> Position:
        self._positions[position.position_id] = position
        return position

    def get(self, position_id: str) -> Position | None:
        return self._positions.get(position_id)

    def get_by_signal(self, signal_id: str) -> Position | None:
        for p in self._positions.values():
            if p.signal_id == signal_id:
                return p
        return None

    def list_open(self) -> list[Position]:
        return [p for p in self._positions.values() if p.position_state != PositionState.CLOSED]

    def all_positions(self) -> list[Position]:
        return list(self._positions.values())

    def clear(self) -> None:
        self._positions.clear()


position_registry = PositionRegistry()
