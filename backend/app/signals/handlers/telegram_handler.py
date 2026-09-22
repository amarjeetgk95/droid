"""
Telegram Notification Event Handler for Droid Signal Engine (Version 6.0)

Subscribes to SignalEventBus events and queues Telegram alerts for confirmed signals
and terminal outcomes when configured.
Validates Price/Decimal (reject missing, never 0.0 default), skips when
monitor != LIVE, handles terminals, no float().
"""
from __future__ import annotations

from decimal import Decimal
import structlog
from app.signals.event_bus import SignalEvent

logger = structlog.get_logger()

_TERMINAL_NOTIFY = {"TARGET_1_HIT", "TARGET_2_HIT", "STOP_LOSS_HIT", "TIME_STOP_HIT",
                    "RUNNER_TIME_STOP_HIT", "EXPIRED", "CLOSED", "INVALIDATED"}
_TRANSITION_NOTIFY = {"TRIGGERED", "CONFIRMED", "STOP_LOSS_HIT", "TARGET_1_HIT",
                      "TARGET_2_HIT", "EXPIRED"} | _TERMINAL_NOTIFY


def _feed_allows() -> bool:
    try:
        from app.signals.safety.feed_health_monitor import feed_health_monitor
        tel = feed_health_monitor.get_telemetry()
        return str(tel.get("status")) == "LIVE"
    except Exception:
        return False


def _dec(v, field: str, signal_id: str) -> Decimal | None:
    if v is None or (isinstance(v, str) and not v.strip()):
        logger.warning("telegram_missing_price_rejected", signal_id=signal_id, field=field)
        return None
    try:
        if isinstance(v, float):
            logger.warning("telegram_float_price_rejected", signal_id=signal_id, field=field)
            return None
        d = v if isinstance(v, Decimal) else Decimal(str(v))
        if d <= 0:
            logger.warning("telegram_nonpositive_price_rejected", signal_id=signal_id, field=field)
            return None
        return d
    except Exception:
        logger.warning("telegram_invalid_price_rejected", signal_id=signal_id, field=field)
        return None


async def handle_signal_registered_telegram(event: SignalEvent) -> None:
    """Dispatches Telegram alert on new signal registration if requested."""
    try:
        payload = event.payload or {}
        if not payload.get("notify_telegram"):
            return
        if not _feed_allows():
            logger.debug("telegram_skipped_feed_not_live", signal_id=event.signal_id)
            return

        trig = _dec(payload.get("trigger"), "trigger", event.signal_id)
        sl = _dec(payload.get("stop_loss"), "stop_loss", event.signal_id)
        t1 = _dec(payload.get("target_1"), "target_1", event.signal_id)
        if trig is None or sl is None or t1 is None:
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
            entry_price=str(trig),
            stop_loss=str(sl),
            target_1=str(t1),
            confidence=float(payload.get("confidence", 0.0) or 0.0),
            timeframe=str(payload.get("timeframe", "")),
            lots=int(payload.get("lots", 1)) if payload.get("lots") else 1,
            max_rupee_loss=float(payload.get("max_rupee_loss", 0.0)) if payload.get("max_rupee_loss") else None,
            institutional_bias=str(payload.get("institutional_bias", "NEUTRAL")),
        )
        await telegram_notification_queue.publish_signal_event(ev)
    except Exception as e:
        logger.warning("telegram_handler_registered_err", signal_id=event.signal_id, error=str(e)[:200])


async def handle_signal_transitioned_telegram(event: SignalEvent) -> None:
    """Telegram for TRANSITIONED: TRIGGERED/CONFIRMED/SL/T1/T2/EXPIRED + terminals."""
    try:
        payload = event.payload or {}
        to_state = str(payload.get("to_state", ""))
        if to_state not in _TRANSITION_NOTIFY:
            return
        if not _feed_allows() and to_state not in ("EXPIRED", "CLOSED"):
            logger.debug("telegram_transition_skipped_feed", signal_id=event.signal_id, to_state=to_state)
            return

        mp = payload.get("market_price")
        # Validate price when present; terminals may carry None (settled flat).
        if mp is not None:
            d = _dec(mp, "market_price", event.signal_id)
            if d is None and to_state not in ("EXPIRED", "CLOSED", "INVALIDATED"):
                return
            mp_str = format(d, "f") if d is not None else None
        else:
            mp_str = None

        from app.institutional.telegram_notifications import (
            SignalEvent as TelegramSignalEvent,
            telegram_notification_queue,
        )
        et = "TARGET_HIT" if "TARGET" in to_state else ("STOP_HIT" if "STOP" in to_state else ("EXPIRED" if to_state == "EXPIRED" else "SIGNAL_UPDATE"))
        ev = TelegramSignalEvent(
            event_type=et,
            signal_id=event.signal_id,
            instrument=str(payload.get("underlying", "")),
            status=to_state,
            result=to_state,
            exit_price=mp_str,
            current_price=mp_str,
        )
        await telegram_notification_queue.publish_signal_event(ev)
    except Exception as e:
        logger.warning("telegram_handler_transition_err", signal_id=event.signal_id, error=str(e)[:200])
