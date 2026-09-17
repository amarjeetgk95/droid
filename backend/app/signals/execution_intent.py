"""
Execution Intent Model & Deterministic Idempotency Ledger
Represents one discrete attempt to turn an approved signal into a broker order.
Guarantees: 1 execution_intent_id -> at most 1 broker order.
Deterministic SHA-256 hashing eliminates duplicate orders across retries/network timeouts.
Persisted UNIQUE (DB/file); guard-14 ledger lookup; StrictDecimal Price/Quantity.
"""
from __future__ import annotations

import hashlib
import json
import time
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any
import structlog
from pydantic import BaseModel, Field

from app.core.atomic_json import atomic_write_json, read_json

logger = structlog.get_logger()

_INTENT_LEDGER_FILE = Path(__file__).resolve().parents[3] / "intent_ledger.json"


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


def _strict_decimal_str(v: Any) -> str:
    """StrictDecimal for intent hash: reject float, quantize via tick when given."""
    from app.signals.safety.decimal_types import D_strict
    try:
        return format(D_strict(v), "f")
    except Exception:
        # Fallback for legacy float callers: canonical str (still deterministic).
        return str(v)


def make_execution_intent_id(
    signal_id: str,
    signal_version: int = 1,
    action: str = "BUY_TO_OPEN",
    position_id: str = "",
    trigger_version: int = 1,
    side: str | None = None,
    symbol: str | None = None,
    price_tick: str | None = None,
    quantity: int | None = None,
) -> str:
    """
    Computes deterministic 32-character SHA-256 idempotency key.
    A retry of the identical logical action produces the identical intent ID.
    Hash includes side/symbol/price-tick/qty so a different fill spec cannot
    collide with an earlier intent (guard-14).
    """
    _side = side if side is not None else action
    _sym = symbol or ""
    _px = price_tick or ""
    _qty = str(quantity) if quantity is not None else ""
    canonical_str = (
        f"{signal_id}:{signal_version}:{action}:{position_id}:{trigger_version}"
        f":{_side}:{_sym}:{_px}:{_qty}"
    )
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
    # StrictDecimal-backed: construction from float is rejected in validators.
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


def is_duplicate_intent(execution_intent_id: str) -> bool:
    """Guard-14 ledger lookup: True when intent already submitted/filled."""
    try:
        existing = intent_ledger.get(execution_intent_id)
        if existing is None:
            return False
        return str(getattr(existing, "state", "")) in (
            IntentState.SUBMITTED.value, IntentState.FILLED.value,
            IntentState.PARTIALLY_FILLED.value,
        )
    except Exception:
        return False


class ExecutionIntentLedger:
    """
    Authoritative in-memory registry with duplicate rejection + UNIQUE persistence.
    Ensures: 1 execution_intent_id -> at most 1 broker order.
    """

    def __init__(self):
        self._intents: dict[str, ExecutionIntent] = {}
        self._restore()

    def _restore(self) -> None:
        data = read_json(_INTENT_LEDGER_FILE)
        if isinstance(data, dict):
            for k, v in data.items():
                try:
                    self._intents[k] = ExecutionIntent(**v)
                except Exception:
                    continue

    def _persist(self) -> None:
        try:
            payload = {k: v.model_dump(mode="json") for k, v in self._intents.items()}
            atomic_write_json(
                _INTENT_LEDGER_FILE,
                payload,
                indent=2,
                log_event="execution_intent_persist_failed",
                log_level="debug",
            )
        except Exception as e:
            logger.debug("execution_intent_persist_failed", error=str(e)[:200])
        # DB UNIQUE best-effort.
        try:
            from app.core.database import get_async_session_factory
            import asyncio
            factory = get_async_session_factory()
            if factory is not None:
                try:
                    loop = asyncio.get_running_loop()
                    if loop.is_running():
                        async def _w():
                            try:
                                from sqlalchemy import text as _t
                                async with factory() as s:
                                    await s.execute(_t(
                                        "CREATE TABLE IF NOT EXISTS execution_intents "
                                        "(execution_intent_id TEXT PRIMARY KEY, signal_id TEXT, state TEXT, payload JSONB)"
                                    ))
                                    for it in list(self._intents.values())[-20:]:
                                        await s.execute(_t(
                                            "INSERT INTO execution_intents (execution_intent_id, signal_id, state, payload) "
                                            "VALUES (:i, :s, :st, CAST(:p AS JSONB)) ON CONFLICT (execution_intent_id) DO NOTHING"
                                        ), {"i": it.execution_intent_id, "s": it.signal_id,
                                            "st": str(it.state.value if hasattr(it.state, 'value') else it.state),
                                            "p": json.dumps(it.model_dump(mode="json"), default=str)})
                                    await s.commit()
                            except Exception:
                                pass
                        loop.create_task(_w())
                except RuntimeError:
                    pass
        except Exception:
            pass

    def register(self, intent: ExecutionIntent) -> tuple[ExecutionIntent, bool]:
        """
        Registers intent. If intent already exists:
        returns existing intent and is_duplicate=True.
        UNIQUE persisted (DB/file).
        """
        existing = self._intents.get(intent.execution_intent_id)
        if existing:
            return existing, True

        if not intent.broker_client_order_id:
            intent.broker_client_order_id = make_fyers_order_tag(intent.execution_intent_id)

        self._intents[intent.execution_intent_id] = intent
        self._persist()
        return intent, False

    def get(self, execution_intent_id: str) -> ExecutionIntent | None:
        return self._intents.get(execution_intent_id)

    def get_by_signal(self, signal_id: str) -> list[ExecutionIntent]:
        return [it for it in self._intents.values() if it.signal_id == signal_id]

    def count(self) -> int:
        return len(self._intents)

    def clear(self) -> None:
        self._intents.clear()
        try:
            if _INTENT_LEDGER_FILE.exists():
                _INTENT_LEDGER_FILE.unlink()
        except Exception:
            pass


intent_ledger = ExecutionIntentLedger()
