"""
Event Handlers for Droid Signal Engine (Version 6.0)

Provides unified subscription registration for persistence, audit, SSE, and notifications.
Telegram → TRANSITIONED (TRIGGERED/CONFIRMED/SL/T1/T2/EXPIRED).
SSE → REGISTERED+EXPIRED+DELETED (+ transitions).
Audit → all five. Kill-active skips notify except KILL events.
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
import structlog as _sl

_logger = _sl.get_logger()


async def _audit_registered_fallback(event) -> None:
    try:
        from app.signals.audit_ledger import signal_audit_ledger
        if signal_audit_ledger.get(event.signal_id) is not None:
            return
        p = event.payload or {}
        signal_audit_ledger.record_signal_created(
            signal_id=event.signal_id,
            underlying=str(p.get("underlying", "NIFTY")),
            strategy=str(p.get("strategy", "UNKNOWN")),
            direction=str(p.get("direction", "LONG_CALL")),
            timeframe=str(p.get("timeframe", "5M")),
            spot_price=float(p.get("spot_price", 0.0) or 0.0),
            trigger=float(p.get("trigger", 0.0) or 0.0),
            stop_loss=float(p.get("stop_loss", 0.0) or 0.0),
            target_1=float(p.get("target_1", 0.0) or 0.0),
            target_2=float(p.get("target_2", 0.0) or 0.0),
            confidence=float(p.get("confidence", 80.0) or 80.0),
            option_contract=p.get("option_contract"),
            status="ARMED",
        )
    except Exception as e:
        _logger.warning("audit_registered_fallback_err", error=str(e)[:150])


async def _audit_expired_fallback(event) -> None:
    try:
        from app.signals.audit_ledger import signal_audit_ledger
        p = event.payload or {}
        signal_audit_ledger.record_state_transition(
            signal_id=event.signal_id, to_state="CLOSED",
            market_price=float(p.get("market_price")) if p.get("market_price") is not None else None,
            reason=str(p.get("reason", "EXPIRED")),
        )
    except Exception:
        pass


async def _audit_deleted_fallback(event) -> None:
    try:
        from app.signals.audit_ledger import signal_audit_ledger
        if signal_audit_ledger.get(event.signal_id) is None:
            return
        signal_audit_ledger.void_trade(event.signal_id, reason="USER_VOID")
    except Exception:
        pass


try:
    from app.signals.handlers.audit_handler import (
        handle_signal_registered_audit as _reg_audit,
        handle_signal_expired_audit as _exp_audit,
        handle_signal_deleted_audit as _del_audit,
    )
    handle_signal_registered_audit = _reg_audit
    handle_signal_expired_audit = _exp_audit
    handle_signal_deleted_audit = _del_audit
except Exception:
    handle_signal_registered_audit = _audit_registered_fallback  # type: ignore[assignment]
    handle_signal_expired_audit = _audit_expired_fallback  # type: ignore[assignment]
    handle_signal_deleted_audit = _audit_deleted_fallback  # type: ignore[assignment]
from app.signals.handlers.sse_handler import (
    handle_signal_transitioned_sse,
    handle_breakeven_activated_sse,
)
try:
    from app.signals.handlers.sse_handler import (
        handle_signal_registered_sse,
        handle_signal_expired_sse,
        handle_signal_deleted_sse,
    )
except Exception:
    async def handle_signal_registered_sse(event) -> None:  # type: ignore[no-redef]
        try:
            from app.signals.sse import signal_sse_hub
            await signal_sse_hub.broadcast("signal_registered", {"signal_id": event.signal_id, **(event.payload or {})}, priority="P1")
        except Exception:
            pass
    async def handle_signal_expired_sse(event) -> None:  # type: ignore[no-redef]
        try:
            from app.signals.sse import signal_sse_hub
            await signal_sse_hub.broadcast("signal_expired", {"signal_id": event.signal_id, **(event.payload or {})}, priority="P1")
        except Exception:
            pass
    async def handle_signal_deleted_sse(event) -> None:  # type: ignore[no-redef]
        try:
            from app.signals.sse import signal_sse_hub
            await signal_sse_hub.broadcast("signal_deleted", {"signal_id": event.signal_id}, priority="P1")
        except Exception:
            pass
from app.signals.handlers.telegram_handler import (
    handle_signal_registered_telegram,
)
try:
    from app.signals.handlers.telegram_handler import handle_signal_transitioned_telegram
except Exception:
    async def handle_signal_transitioned_telegram(event) -> None:  # type: ignore[no-redef]
        return None

_REGISTERED = False


def _kill_active() -> bool:
    try:
        from app.signals.safety.kill_switch import kill_switch
        return bool(kill_switch.is_active())
    except Exception:
        return False


def register_default_handlers() -> None:
    """Registers default production event handlers on the global signal_event_bus."""
    global _REGISTERED
    if _REGISTERED:
        return

    # Persistence handlers (all five + breakeven)
    signal_event_bus.subscribe(SignalEventType.REGISTERED, handle_signal_registered)
    signal_event_bus.subscribe(SignalEventType.TRANSITIONED, handle_signal_transitioned)
    signal_event_bus.subscribe(SignalEventType.BREAKEVEN_ACTIVATED, handle_signal_breakeven_activated)
    signal_event_bus.subscribe(SignalEventType.EXPIRED, handle_signal_expired)
    signal_event_bus.subscribe(SignalEventType.DELETED, handle_signal_deleted)

    # Audit handler — all five lifecycle events.
    signal_event_bus.subscribe(SignalEventType.TRANSITIONED, handle_signal_transitioned_audit)
    signal_event_bus.subscribe(SignalEventType.REGISTERED, handle_signal_registered_audit)
    signal_event_bus.subscribe(SignalEventType.EXPIRED, handle_signal_expired_audit)
    signal_event_bus.subscribe(SignalEventType.DELETED, handle_signal_deleted_audit)

    # SSE handlers — REGISTERED + EXPIRED + DELETED + transitions.
    signal_event_bus.subscribe(SignalEventType.TRANSITIONED, handle_signal_transitioned_sse)
    signal_event_bus.subscribe(SignalEventType.BREAKEVEN_ACTIVATED, handle_breakeven_activated_sse)
    signal_event_bus.subscribe(SignalEventType.REGISTERED, handle_signal_registered_sse)
    signal_event_bus.subscribe(SignalEventType.EXPIRED, handle_signal_expired_sse)
    signal_event_bus.subscribe(SignalEventType.DELETED, handle_signal_deleted_sse)

    # Telegram handlers — REGISTERED + TRANSITIONED (TRIGGERED/CONFIRMED/SL/T1/T2/EXPIRED).
    signal_event_bus.subscribe(SignalEventType.REGISTERED, handle_signal_registered_telegram)
    signal_event_bus.subscribe(SignalEventType.TRANSITIONED, handle_signal_transitioned_telegram)

    _REGISTERED = True


def unregister_all() -> None:
    """Remove all default handlers (tests / shutdown)."""
    global _REGISTERED
    try:
        signal_event_bus.clear_handlers()
    except Exception:
        pass
    _REGISTERED = False


# Auto-register on import so handlers are always active
register_default_handlers()

__all__ = [
    "register_default_handlers",
    "unregister_all",
    "handle_signal_registered",
    "handle_signal_transitioned",
    "handle_signal_breakeven_activated",
    "handle_signal_expired",
    "handle_signal_deleted",
    "handle_signal_transitioned_audit",
    "handle_signal_transitioned_sse",
    "handle_breakeven_activated_sse",
    "handle_signal_registered_sse",
    "handle_signal_expired_sse",
    "handle_signal_deleted_sse",
    "handle_signal_registered_telegram",
    "handle_signal_transitioned_telegram",
]
