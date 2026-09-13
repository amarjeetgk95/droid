"""
Lightweight In-Memory Event Bus for Signal Engine Lifecycle (Version 6.0)

Decouples FSM state transitions from infrastructure side-effects (persistence,
audit ledger, Telegram notifications, and SSE streaming).
Replaces scattered inline try/except blocks with clean, isolated event subscribers.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict
from enum import Enum
from typing import Any, Callable
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger()

MAX_FAILURE_LOG_ENTRIES: int = 500


class SignalEventType(str, Enum):
    REGISTERED = "signal.registered"
    TRANSITIONED = "signal.transitioned"
    BREAKEVEN_ACTIVATED = "signal.breakeven_activated"
    EXPIRED = "signal.expired"
    DELETED = "signal.deleted"


class SignalEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: SignalEventType
    signal_id: str
    occurred_at_utc: int = Field(default_factory=lambda: int(time.time() * 1000))
    payload: dict[str, Any] = Field(default_factory=dict)


class SignalEventBus:
    """
    In-memory asynchronous event bus with error isolation, failure logging,
    and diagnostic inspection.
    """

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = defaultdict(list)
        self._failure_log: list[dict[str, Any]] = []

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
        If no loop is running, invokes synchronous handlers immediately.
        """
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(self.publish(event))
                return
        except RuntimeError:
            pass

        # Fallback when no running event loop: run synchronous handlers directly
        key = event.event_type.value if isinstance(event.event_type, SignalEventType) else str(event.event_type)
        handlers = list(self._handlers.get(key, []))
        for handler in handlers:
            try:
                res = handler(event)
                if asyncio.iscoroutine(res):
                    res.close()
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
                    "signal_event_handler_sync_failed",
                    event_id=event.event_id,
                    event_type=key,
                    signal_id=event.signal_id,
                    handler=handler_name,
                    error=err_msg,
                )

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
        self._failure_log.append({
            "event_id": event_id,
            "event_type": event_type,
            "signal_id": signal_id,
            "handler": handler,
            "error": error,
            "timestamp_utc": int(time.time() * 1000),
        })

    def get_failure_log(self) -> list[dict[str, Any]]:
        """Return shallow copy of recorded handler failures for diagnostics."""
        return list(self._failure_log)

    def clear_failure_log(self) -> None:
        """Clear recorded failures."""
        self._failure_log.clear()

    def clear_handlers(self) -> None:
        """Clear all registered handlers (used primarily for test isolation)."""
        self._handlers.clear()


# Global singleton event bus
signal_event_bus = SignalEventBus()
