"""
Server-Sent Events (SSE) Handler for Droid Signal Engine (Version 6.0)

Subscribes to SignalEventBus events and broadcasts real-time signal state changes
and breakeven ratchets to connected frontend clients via signal_sse_hub.
"""
from __future__ import annotations

import structlog
from app.signals.event_bus import SignalEvent

logger = structlog.get_logger()


async def handle_signal_transitioned_sse(event: SignalEvent) -> None:
    """Broadcasts signal state transition to SSE subscribers."""
    try:
        from app.signals.sse import signal_sse_hub

        payload = event.payload
        to_state = payload.get("to_state")
        priority = "P0" if to_state in ("TRIGGERED", "CONFIRMED", "TARGET_1_HIT", "TARGET_2_HIT", "STOP_LOSS_HIT") else "P1"

        await signal_sse_hub.broadcast(
            "signal_transition",
            {
                "signal_id": event.signal_id,
                "from_state": payload.get("from_state"),
                "to_state": to_state,
                "market_price": payload.get("market_price"),
                "reason": payload.get("reason"),
                "timestamp_ms": event.occurred_at_utc,
            },
            priority=priority,
        )
    except Exception as e:
        logger.debug("sse_handler_transition_err", signal_id=event.signal_id, error=str(e)[:200])


async def handle_breakeven_activated_sse(event: SignalEvent) -> None:
    """Broadcasts breakeven ratchet to SSE subscribers."""
    try:
        from app.signals.sse import signal_sse_hub

        payload = event.payload
        await signal_sse_hub.broadcast(
            "signal_breakeven",
            {
                "signal_id": event.signal_id,
                "new_stop_loss": payload.get("new_sl"),
                "market_price": payload.get("market_price"),
                "timestamp_ms": event.occurred_at_utc,
            },
            priority="P1",
        )
    except Exception as e:
        logger.debug("sse_handler_breakeven_err", signal_id=event.signal_id, error=str(e)[:200])
