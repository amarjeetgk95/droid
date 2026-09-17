"""
Lightweight In-Memory Event Bus for Signal Engine Lifecycle (Version 6.0)

Decouples FSM state transitions from infrastructure side-effects (persistence,
audit ledger, Telegram notifications, and SSE streaming).
Replaces scattered inline try/except blocks with clean, isolated event subscribers.
Seq + canonical_ts on every event; failure_log persisted + drop counter.
"""
from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict
from enum import Enum
from pathlib import Path
from typing import Any, Callable
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger()

MAX_FAILURE_LOG_ENTRIES: int = 500

_FAILURE_LOG_FILE = Path(__file__).resolve().parents[3] / "event_bus_failures.jsonl"


class SignalEventType(str, Enum):
    REGISTERED = "signal.registered"
    TRANSITIONED = "signal.transitioned"
    BREAKEVEN_ACTIVATED = "signal.breakeven_activated"
    EXPIRED = "signal.expired"
    DELETED = "signal.deleted"


class SignalEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: __import__("uuid").uuid4().__str__())
    event_type: SignalEventType
    signal_id: str
    occurred_at_utc: int = Field(default_factory=lambda: int(time.time() * 1000))
    payload: dict[str, Any] = Field(default_factory=dict)
    # Monotonic ordering + canonical event time (ns + ms).
    seq: int = 0
    canonical_ts: int = 0


class SignalEventBus:
    """
    In-memory asynchronous event bus with error isolation, failure logging,
    and diagnostic inspection.
    """

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = defaultdict(list)
        self._failure_log: list[dict[str, Any]] = []
        self._seq: int = 0
        self._drop_count: int = 0

    def _assign_seq(self, event: SignalEvent) -> SignalEvent:
        try:
            self._seq += 1
            object.__setattr__(event, "seq", self._seq) if hasattr(event, "__dict__") else None
            # Pydantic v2: direct assignment works when validate_assignment off;
            # fallback to model_copy.
            try:
                event.seq = self._seq
            except Exception:
                pass
            try:
                event.canonical_ts = int(event.occurred_at_utc or int(time.time() * 1000))
            except Exception:
                pass
        except Exception:
            pass
        return event

    def subscribe(self, event_type: SignalEventType | str, handler: Callable) -> None:
        """Subscribe a callable (sync or async) to an event type."""
        key = event_type.value if isinstance(event_type, SignalEventType) else str(event_type)
        if handler not in self._handlers[key]:
            self._handlers[key].append(handler)

    def unsubscribe(self, event_type: SignalEventType | str, handler: Callable) -> None:
        """Unsubscribe a callable from an event type."""
        key = event_type.value if isinstance(event_type, SignalEventType) else str(event_type)
        if handler in self._handlers[key]:
            self._handlers[key].remove(handler)

    async def publish(self, event: SignalEvent) -> None:
        """
        Publish an event to all subscribed handlers.
        Each handler executes in isolation: failures are logged and recorded
        in _failure_log without propagating to the caller or other handlers.
        """
        self._assign_seq(event)
        key = event.event_type.value if isinstance(event.event_type, SignalEventType) else str(event.event_type)
        handlers = list(self._handlers.get(key, []))

        for handler in handlers:
            try:
                res = handler(event)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                handler_name = getattr(handler, "__name__", repr(handler))
                err_msg = str(e)[:250]
                self._record_failure(
                    event_id=event.event_id,
                    event_type=key,
                    signal_id=event.signal_id,
                    handler=handler_name,
                    error=err_msg,
                )
                logger.warning(
                    "signal_event_handler_failed",
                    event_id=event.event_id,
                    event_type=key,
                    signal_id=event.signal_id,
                    handler=handler_name,
                    error=err_msg,
                )

    def publish_sync(self, event: SignalEvent) -> None:
        """
        Synchronous-safe publisher.
        If an asyncio event loop is running, schedules publish() as a background task.
        If no loop is running, runs the async pipeline via asyncio.run (never close()).
        """
        self._assign_seq(event)
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(self.publish(event))
                return
        except RuntimeError:
            pass

        # No running loop: drive async handlers to completion via asyncio.run.
        # Never call .close() on a coroutine (leaks + warns); asyncio.run owns the loop.
        # Detect async without invoking (avoids leaked coroutines).
        key = event.event_type.value if isinstance(event.event_type, SignalEventType) else str(event.event_type)
        handlers = list(self._handlers.get(key, []))
        if not handlers:
            return
        has_async = False
        try:
            import inspect as _inspect
            has_async = any(_inspect.iscoroutinefunction(h) for h in handlers)
        except Exception:
            has_async = True
        if not has_async:
            # All sync: invoke directly with isolation.
            for h in handlers:
                try:
                    h(event)
                except Exception as e:
                    handler_name = getattr(h, "__name__", repr(h))
                    err_msg = str(e)[:250]
                    self._record_failure(event.event_id, key, event.signal_id, handler_name, err_msg)
            return
        # Re-dispatch through async publish so every handler runs uniformly.

        async def _drain():
            await self.publish(event)

        try:
            asyncio.run(_drain())
        except RuntimeError:
            # Already inside a loop edge-case: schedule as task on a new loop is
            # impossible; fall back to recording a drop (counted, not silent).
            self._drop_count += 1
            self._record_failure(event.event_id, key, event.signal_id, "publish_sync", "event loop conflict: dropped+counted")

    def _record_failure(
        self,
        event_id: str,
        event_type: str,
        signal_id: str,
        handler: str,
        error: str,
    ) -> None:
        if len(self._failure_log) >= MAX_FAILURE_LOG_ENTRIES:
            self._failure_log.pop(0)
            self._drop_count += 1
        self._failure_log.append({
            "event_id": event_id,
            "event_type": event_type,
            "signal_id": signal_id,
            "handler": handler,
            "error": error,
            "timestamp_utc": int(time.time() * 1000),
        })
        # Persist failure log (best-effort, JSONL append).
        try:
            with open(_FAILURE_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(self._failure_log[-1], default=str) + "\n")
        except Exception:
            pass

    def get_failure_log(self) -> list[dict[str, Any]]:
        """Return shallow copy of recorded handler failures for diagnostics."""
        return list(self._failure_log)

    def clear_failure_log(self) -> None:
        """Clear recorded failures."""
        self._failure_log.clear()

    def clear_handlers(self) -> None:
        """Clear all registered handlers (used primarily for test isolation)."""
        self._handlers.clear()

    def drop_count(self) -> int:
        return self._drop_count


# Global singleton event bus
signal_event_bus = SignalEventBus()
