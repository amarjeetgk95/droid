"""
Persistence Event Handler for Droid Signal Engine (Version 6.0)

Subscribes to SignalEventBus events and manages local JSON cache and
Supabase/PostgreSQL database persistence asynchronously without blocking FSM state machine logic.
BREAKEVEN/EXPIRED persisted to DB; async local save via to_thread; version/seq guard; retry+DLQ.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any
import structlog

from app.signals.event_bus import SignalEvent, SignalEventType

logger = structlog.get_logger()

_DLQ: deque[dict[str, Any]] = deque(maxlen=200)
_seen_seq: dict[str, int] = {}


def _seq_guard(event: SignalEvent) -> bool:
    """Version/seq guard: drop stale replays (seq <= last seen for signal)."""
    try:
        seq = int(getattr(event, "seq", 0) or 0)
        if seq <= 0:
            return True
        last = _seen_seq.get(event.signal_id, 0)
        if seq <= last:
            logger.debug("persistence_stale_seq_dropped", signal_id=event.signal_id, seq=seq, last=last)
            return False
        _seen_seq[event.signal_id] = seq
        return True
    except Exception:
        return True


async def _save_local_async() -> bool:
    try:
        from app.signals.signals_persistence import save_signals_state_local
        return await asyncio.to_thread(save_signals_state_local)
    except Exception as e:
        logger.warning("persistence_local_async_err", error=str(e)[:150])
        return False


async def _persist_db_with_retry(sig: Any, attempts: int = 3) -> bool:
    from app.signals.signals_persistence import persist_executed_signal
    backoff = 0.1
    last_err: str = ""
    for i in range(attempts):
        try:
            ok = await persist_executed_signal(sig)
            if ok:
                return True
            last_err = "persist returned False"
        except Exception as e:
            last_err = str(e)[:150]
        await asyncio.sleep(backoff)
        backoff *= 2
    try:
        _DLQ.append({"signal_id": getattr(sig, "signal_id", "?"), "error": last_err,
                     "ts": int(time.time() * 1000)})
    except Exception:
        pass
    logger.warning("persistence_db_dlq", signal_id=getattr(sig, "signal_id", "?"), error=last_err)
    return False


async def handle_signal_registered(event: SignalEvent) -> None:
    """Persists newly registered signal locally and to PostgreSQL."""
    try:
        if not _seq_guard(event):
            return
        await _save_local_async()
        from app.signals.fsm import signal_fsm
        sig = signal_fsm.get(event.signal_id)
        if sig:
            await _persist_db_with_retry(sig)
    except Exception as e:
        logger.warning("persistence_handler_registered_err", signal_id=event.signal_id, error=str(e)[:200])


async def handle_signal_transitioned(event: SignalEvent) -> None:
    """Persists state transition updates locally and to PostgreSQL."""
    try:
        if not _seq_guard(event):
            return
        await _save_local_async()
        from app.signals.fsm import signal_fsm
        sig = signal_fsm.get(event.signal_id)
        if sig:
            await _persist_db_with_retry(sig)
    except Exception as e:
        logger.warning("persistence_handler_transitioned_err", signal_id=event.signal_id, error=str(e)[:200])


async def handle_signal_breakeven_activated(event: SignalEvent) -> None:
    """Persists breakeven ratchet to local cache AND DB (economics changed)."""
    try:
        if not _seq_guard(event):
            return
        await _save_local_async()
        try:
            from app.signals.fsm import signal_fsm
            sig = signal_fsm.get(event.signal_id)
            if sig:
                await _persist_db_with_retry(sig)
        except Exception:
            pass
    except Exception as e:
        logger.warning("persistence_handler_breakeven_err", signal_id=event.signal_id, error=str(e)[:200])


async def handle_signal_expired(event: SignalEvent) -> None:
    """Persists signal expiration to local cache AND DB (terminal economics)."""
    try:
        if not _seq_guard(event):
            return
        await _save_local_async()
        try:
            from app.signals.fsm import signal_fsm
            sig = signal_fsm.get(event.signal_id)
            if sig:
                await _persist_db_with_retry(sig)
        except Exception:
            pass
    except Exception as e:
        logger.warning("persistence_handler_expired_err", signal_id=event.signal_id, error=str(e)[:200])


async def handle_signal_deleted(event: SignalEvent) -> None:
    """Purges deleted signal from local cache and PostgreSQL."""
    try:
        await _save_local_async()
        from app.signals.signals_persistence import (
            delete_persisted_signal,
        )
        await delete_persisted_signal(event.signal_id)
    except Exception as e:
        logger.warning("persistence_handler_deleted_err", signal_id=event.signal_id, error=str(e)[:200])


def get_dlq() -> list[dict[str, Any]]:
    return list(_DLQ)
