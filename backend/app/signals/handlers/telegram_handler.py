"""
Telegram Notification Event Handler for Droid Signal Engine (Version 6.0)

Subscribes to SignalEventBus events and queues Telegram alerts for confirmed signals
and terminal outcomes when configured.
"""
from __future__ import annotations

import structlog
from app.signals.event_bus import SignalEvent

logger = structlog.get_logger()


async def handle_signal_registered_telegram(event: SignalEvent) -> None:
    """Dispatches Telegram alert on new signal registration if requested."""
    try:
        payload = event.payload
        if not payload.get("notify_telegram"):
            return

        from app.institutional.telegram_notifications import (
            SignalEvent as TelegramSignalEvent,
            telegram_notification_queue,
        )

        ev = TelegramSignalEvent(
            event_type="SIGNAL_NEW",
            signal_id=event.signal_id,
            underlying=str(payload.get("underlying", "")),
            strategy=str(payload.get("strategy", "")),
            direction=str(payload.get("direction", "")),
            entry_price=float(payload.get("trigger", 0.0)),
            stop_loss=float(payload.get("stop_loss", 0.0)),
            target_1=float(payload.get("target_1", 0.0)),
            confidence=float(payload.get("confidence", 0.0)),
            timeframe=str(payload.get("timeframe", "")),
            lots=int(payload.get("lots", 1)) if payload.get("lots") else 1,
            max_rupee_loss=float(payload.get("max_rupee_loss", 0.0)) if payload.get("max_rupee_loss") else None,
            institutional_bias=str(payload.get("institutional_bias", "NEUTRAL")),
        )
        await telegram_notification_queue.publish_signal_event(ev)
    except Exception as e:
        logger.warning("telegram_handler_registered_err", signal_id=event.signal_id, error=str(e)[:200])
