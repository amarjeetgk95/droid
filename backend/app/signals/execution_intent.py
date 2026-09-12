"""
Execution Intent Model & Deterministic Idempotency Ledger
Represents one discrete attempt to turn an approved signal into a broker order.
Guarantees: 1 execution_intent_id -> at most 1 broker order.
Deterministic SHA-256 hashing eliminates duplicate orders across retries/network timeouts.
"""
from __future__ import annotations

import hashlib
import time
from decimal import Decimal
from enum import Enum
from typing import Any
import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger()


class IntentState(str, Enum):
    CREATED = "CREATED"
    GUARD_PASSED = "GUARD_PASSED"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


ALLOWED_INTENT_TRANSITIONS: dict[IntentState, set[IntentState]] = {
    IntentState.CREATED: {IntentState.GUARD_PASSED, IntentState.REJECTED, IntentState.EXPIRED},
    IntentState.GUARD_PASSED: {IntentState.SUBMITTED, IntentState.REJECTED, IntentState.EXPIRED, IntentState.RECONCILIATION_REQUIRED},
    IntentState.SUBMITTED: {IntentState.FILLED, IntentState.PARTIALLY_FILLED, IntentState.REJECTED, IntentState.RECONCILIATION_REQUIRED, IntentState.EXPIRED},
    IntentState.PARTIALLY_FILLED: {IntentState.FILLED, IntentState.RECONCILIATION_REQUIRED},
    IntentState.RECONCILIATION_REQUIRED: {IntentState.FILLED, IntentState.PARTIALLY_FILLED, IntentState.REJECTED, IntentState.EXPIRED},
    IntentState.FILLED: set(),
    IntentState.REJECTED: set(),
    IntentState.EXPIRED: set(),
}


def make_execution_intent_id(
    signal_id: str,
    signal_version: int = 1,
    action: str = "BUY_TO_OPEN",
    position_id: str = "",
    trigger_version: int = 1,
) -> str:
    """
    Computes deterministic 32-character SHA-256 idempotency key.
    A retry of the identical logical action produces the identical intent ID.
    """
    canonical_str = f"{signal_id}:{signal_version}:{action}:{position_id}:{trigger_version}"
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()[:32]


def make_fyers_order_tag(execution_intent_id: str) -> str:
    """
    FYERS order tag format: max 30 alphanumeric characters.
    """
    return f"DRD_{execution_intent_id[:20]}"


class ExecutionIntent(BaseModel):
    execution_intent_id: str
    signal_id: str
    signal_version: int = 1
    action: str = "BUY_TO_OPEN"
    position_id: str | None = None
    state: IntentState = IntentState.CREATED

    broker_client_order_id: str = Field(default="")
    broker_order_id: str | None = None

    instrument_symbol: str = ""
    side: str = "BUY"
    intended_price: Decimal | None = None
    intended_quantity: int = 0

    actual_fill_price: Decimal | None = None
    filled_quantity: int = 0

    guard_snapshot: dict[str, Any] = Field(default_factory=dict)
    reconciliation_details: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None

    created_at_utc: int = Field(default_factory=lambda: int(time.time() * 1000))
    updated_at_utc: int = Field(default_factory=lambda: int(time.time() * 1000))

    def transition_to(self, new_state: IntentState, reason: str = "", details: dict[str, Any] | None = None) -> bool:
        if new_state not in ALLOWED_INTENT_TRANSITIONS.get(self.state, set()):
            logger.error(
                "illegal_intent_transition",
                intent_id=self.execution_intent_id,
                from_state=self.state,
                to_state=new_state,
                reason=reason,
            )
            return False

        self.state = new_state
        self.updated_at_utc = int(time.time() * 1000)
        if details:
            self.reconciliation_details.update(details)
        if reason:
            self.reconciliation_details["last_transition_reason"] = reason

        logger.info(
            "execution_intent_transition",
            intent_id=self.execution_intent_id,
            signal_id=self.signal_id,
            to_state=new_state.value,
            reason=reason,
        )
        return True


class ExecutionIntentLedger:
    """
    Authoritative in-memory registry with duplicate rejection.
    Ensures: 1 execution_intent_id -> at most 1 broker order.
    """
    def __init__(self):
        self._intents: dict[str, ExecutionIntent] = {}

    def register(self, intent: ExecutionIntent) -> tuple[ExecutionIntent, bool]:
        """
        Registers intent. If intent already exists:
        returns existing intent and is_duplicate=True.
        """
        existing = self._intents.get(intent.execution_intent_id)
        if existing:
            return existing, True

        if not intent.broker_client_order_id:
            intent.broker_client_order_id = make_fyers_order_tag(intent.execution_intent_id)

        self._intents[intent.execution_intent_id] = intent
        return intent, False

    def get(self, execution_intent_id: str) -> ExecutionIntent | None:
        return self._intents.get(execution_intent_id)

    def get_by_signal(self, signal_id: str) -> list[ExecutionIntent]:
        return [it for it in self._intents.values() if it.signal_id == signal_id]

    def count(self) -> int:
        return len(self._intents)

    def clear(self) -> None:
        self._intents.clear()


intent_ledger = ExecutionIntentLedger()
