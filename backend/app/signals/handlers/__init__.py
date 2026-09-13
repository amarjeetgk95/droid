"""
Event Handlers for Droid Signal Engine (Version 6.0)

Provides unified subscription registration for persistence, audit, SSE, and notifications.
"""
from __future__ import annotations

from app.signals.event_bus import SignalEventType, signal_event_bus
from app.signals.handlers.persistence_handler import (
    handle_signal_registered,
    handle_signal_transitioned,
    handle_signal_breakeven_activated,
    handle_signal_expired,
    handle_signal_deleted,
)
from app.signals.handlers.audit_handler import handle_signal_transitioned_audit
from app.signals.handlers.sse_handler import (
    handle_signal_transitioned_sse,
    handle_breakeven_activated_sse,
)
from app.signals.handlers.telegram_handler import handle_signal_registered_telegram

_REGISTERED = False


def register_default_handlers() -> None:
    """Registers default production event handlers on the global signal_event_bus."""
    global _REGISTERED
    if _REGISTERED:
        return

    # Persistence handlers
    signal_event_bus.subscribe(SignalEventType.REGISTERED, handle_signal_registered)
    signal_event_bus.subscribe(SignalEventType.TRANSITIONED, handle_signal_transitioned)
    signal_event_bus.subscribe(SignalEventType.BREAKEVEN_ACTIVATED, handle_signal_breakeven_activated)
    signal_event_bus.subscribe(SignalEventType.EXPIRED, handle_signal_expired)
    signal_event_bus.subscribe(SignalEventType.DELETED, handle_signal_deleted)

    # Audit handler
    signal_event_bus.subscribe(SignalEventType.TRANSITIONED, handle_signal_transitioned_audit)

    # SSE handlers
    signal_event_bus.subscribe(SignalEventType.TRANSITIONED, handle_signal_transitioned_sse)
    signal_event_bus.subscribe(SignalEventType.BREAKEVEN_ACTIVATED, handle_breakeven_activated_sse)

    # Telegram handler
    signal_event_bus.subscribe(SignalEventType.REGISTERED, handle_signal_registered_telegram)

    _REGISTERED = True


# Auto-register on import so handlers are always active
register_default_handlers()

__all__ = [
    "register_default_handlers",
    "handle_signal_registered",
    "handle_signal_transitioned",
    "handle_signal_breakeven_activated",
    "handle_signal_expired",
    "handle_signal_deleted",
    "handle_signal_transitioned_audit",
    "handle_signal_transitioned_sse",
    "handle_breakeven_activated_sse",
    "handle_signal_registered_telegram",
]
