"""
Server-Sent Events (SSE) Handler for Droid Signal Engine (Version 6.0)

Subscribes to SignalEventBus events and broadcasts real-time signal state changes
and breakeven ratchets to connected frontend clients via signal_sse_hub.
Attaches monotonic seq + canonical_ts, validates to_state, warns + counts failures.
Covers REGISTERED/EXPIRED/DELETED + transitions.
"""
from __future__ import annotations

import time
import structlog
from app.signals.event_bus import SignalEvent

logger = structlog.get_logger()

_VALID_STATES = {
    "DETECTED", "VALIDATED", "ARMED", "TRIGGERED", "CONFIRMED",
    "TARGET_1_HIT", "TARGET_2_HIT", "STOP_LOSS_HIT", "TIME_STOP_HIT",
    "RUNNER_TIME_STOP_HIT", "INVALIDATED", "EXPIRED", "CLOSED",
}

_sse_fail_count: int = 0


def _kill_skip(event: SignalEvent) -> bool:
    try:
        p = event.payload or {}
        if p.get("kind") == "KILL" or p.get("kill"):
            return False
        from app.signals.safety.kill_switch import kill_switch
        return bool(kill_switch.is_active())
    except Exception:
        return False


def _envelope(event: SignalEvent, extra: dict) -> dict:
    try:
        seq = int(getattr(event, "seq", 0) or 0)
    except Exception:
        seq = 0
    try:
        cts = int(getattr(event, "canonical_ts", 0) or event.occurred_at_utc)
    except Exception:
        cts = int(time.time() * 1000)
    if not seq:
        try:
            from app.signals.sse import signal_sse_hub
            seq = int(signal_sse_hub.next_seq())
        except Exception:
            seq = 0
    base = {"signal_id": event.signal_id, "seq": seq, "canonical_ts": cts,
            "timestamp_ms": event.occurred_at_utc}
    base.update(extra or {})
    return base


async def handle_signal_transitioned_sse(event: SignalEvent) -> None:
    """Broadcasts signal state transition to SSE subscribers."""
    global _sse_fail_count
    try:
        if _kill_skip(event):
            return
        from app.signals.sse import signal_sse_hub

        payload = event.payload or {}
        to_state = payload.get("to_state")
        if to_state is not None and str(to_state) not in _VALID_STATES:
            logger.warning("sse_invalid_to_state", signal_id=event.signal_id, to_state=to_state)
            _sse_fail_count += 1
            return
        priority = "P0" if to_state in ("TRIGGERED", "CONFIRMED", "TARGET_1_HIT", "TARGET_2_HIT", "STOP_LOSS_HIT") else "P1"

        await signal_sse_hub.broadcast(
            "signal_transition",
            _envelope(event, {
                "from_state": payload.get("from_state"),
                "to_state": to_state,
                "market_price": payload.get("market_price"),
                "reason": payload.get("reason"),
            }),
            priority=priority,
        )
    except Exception as e:
        _sse_fail_count += 1
        logger.warning("sse_handler_transition_err", signal_id=event.signal_id,
                       error=str(e)[:200], fail_count=_sse_fail_count)


async def handle_breakeven_activated_sse(event: SignalEvent) -> None:
    """Broadcasts breakeven ratchet to SSE subscribers."""
    global _sse_fail_count
    try:
        if _kill_skip(event):
            return
        from app.signals.sse import signal_sse_hub

        payload = event.payload or {}
        await signal_sse_hub.broadcast(
            "signal_breakeven",
            _envelope(event, {
                "new_stop_loss": payload.get("new_sl"),
                "market_price": payload.get("market_price"),
            }),
            priority="P1",
        )
    except Exception as e:
        _sse_fail_count += 1
        logger.warning("sse_handler_breakeven_err", signal_id=event.signal_id,
                       error=str(e)[:200], fail_count=_sse_fail_count)


async def handle_signal_registered_sse(event: SignalEvent) -> None:
    global _sse_fail_count
    try:
        if _kill_skip(event):
            return
        from app.signals.sse import signal_sse_hub
        await signal_sse_hub.broadcast(
            "signal_registered", _envelope(event, dict(event.payload or {})), priority="P1")
    except Exception as e:
        _sse_fail_count += 1
        logger.warning("sse_handler_registered_err", signal_id=event.signal_id, error=str(e)[:200])


async def handle_signal_expired_sse(event: SignalEvent) -> None:
    global _sse_fail_count
    try:
        if _kill_skip(event):
            return
        from app.signals.sse import signal_sse_hub
        await signal_sse_hub.broadcast(
            "signal_expired", _envelope(event, dict(event.payload or {})), priority="P1")
    except Exception as e:
        _sse_fail_count += 1
        logger.warning("sse_handler_expired_err", signal_id=event.signal_id, error=str(e)[:200])


async def handle_signal_deleted_sse(event: SignalEvent) -> None:
    global _sse_fail_count
    try:
        # DELETED (tombstone) is delivered even when kill active? No — kill
        # skips notify except KILL; DELETED is not KILL, so skip when active.
        if _kill_skip(event):
            return
        from app.signals.sse import signal_sse_hub
        await signal_sse_hub.broadcast(
            "signal_deleted", _envelope(event, {"signal_id": event.signal_id}), priority="P1")
    except Exception as e:
        _sse_fail_count += 1
        logger.warning("sse_handler_deleted_err", signal_id=event.signal_id, error=str(e)[:200])
