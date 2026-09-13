"""
Persistence Event Handler for Droid Signal Engine (Version 6.0)

Subscribes to SignalEventBus events and manages local JSON cache and
Supabase/PostgreSQL database persistence asynchronously without blocking FSM state machine logic.
"""
from __future__ import annotations

import asyncio
from typing import Any
import structlog

from app.signals.event_bus import SignalEvent, SignalEventType

logger = structlog.get_logger()


async def handle_signal_registered(event: SignalEvent) -> None:
    """Persists newly registered signal locally and to PostgreSQL."""
    try:
        from app.signals.signals_persistence import (
            persist_executed_signal,
            save_signals_state_local,
        )
        save_signals_state_local()

        from app.signals.fsm import signal_fsm
        sig = signal_fsm.get(event.signal_id)
        if sig:
            await persist_executed_signal(sig)
    except Exception as e:
        logger.warning("persistence_handler_registered_err", signal_id=event.signal_id, error=str(e)[:200])


async def handle_signal_transitioned(event: SignalEvent) -> None:
    """Persists state transition updates locally and to PostgreSQL."""
    try:
        from app.signals.signals_persistence import (
            persist_executed_signal,
            save_signals_state_local,
        )
        save_signals_state_local()

        from app.signals.fsm import signal_fsm
        sig = signal_fsm.get(event.signal_id)
        if sig:
            await persist_executed_signal(sig)
    except Exception as e:
        logger.warning("persistence_handler_transitioned_err", signal_id=event.signal_id, error=str(e)[:200])


async def handle_signal_breakeven_activated(event: SignalEvent) -> None:
    """Persists breakeven ratchet update to local state cache."""
    try:
        from app.signals.signals_persistence import save_signals_state_local
        save_signals_state_local()
    except Exception as e:
        logger.warning("persistence_handler_breakeven_err", signal_id=event.signal_id, error=str(e)[:200])


async def handle_signal_expired(event: SignalEvent) -> None:
    """Persists signal expiration to local state cache."""
    try:
        from app.signals.signals_persistence import save_signals_state_local
        save_signals_state_local()
    except Exception as e:
        logger.warning("persistence_handler_expired_err", signal_id=event.signal_id, error=str(e)[:200])


async def handle_signal_deleted(event: SignalEvent) -> None:
    """Purges deleted signal from local cache and PostgreSQL."""
    try:
        from app.signals.signals_persistence import (
            delete_persisted_signal,
            save_signals_state_local,
        )
        save_signals_state_local()
        await delete_persisted_signal(event.signal_id)
    except Exception as e:
        logger.warning("persistence_handler_deleted_err", signal_id=event.signal_id, error=str(e)[:200])
