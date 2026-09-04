"""
Telegram Integration API — §§2-8, 27-31, 39
Endpoints for status, account linking (authenticated), notification preferences,
test messages, webhook, webhook setup and audit.

Security:
- The bot token is NEVER returned by any endpoint (§29).
- Linking always uses the authenticated web user (§28) — user_id is never taken
  from the request for linking.
- The webhook verifies X-Telegram-Bot-Api-Secret-Token and is non-blocking (§7).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
import structlog

from app.core.config import settings
from app.core.security import AuthUser, require_auth
from app.institutional.telegram import (
    telegram_link_manager,
    telegram_update_queue,
    verify_telegram_secret,
    is_duplicate_update,
    set_telegram_webhook,
    webhook_secret,
    TELEGRAM_COMMANDS,
)
from app.institutional.telegram_notifications import (
    telegram_notification_queue,
    notification_policy,
    NotificationPreferences,
    SignalEvent,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/telegram", tags=["telegram"])


def _bot_configured() -> bool:
    return bool(settings.telegram_bot_token)


def _binding_view(binding: dict | None) -> dict:
    if not binding:
        return {"linked": False, "telegram_chat_id": None, "linked_at": None, "status": "NOT_LINKED"}
    return {
        "linked": True,
        "telegram_chat_id": str(binding.get("telegram_chat_id")),
        "linked_at": binding.get("linked_at"),
        "status": binding.get("status"),
    }


def _backend_base_url() -> str:
    # Public base URL of this backend; configurable via BACKEND_PUBLIC_URL.
    return (
        getattr(settings, "backend_public_url", "")
        or f"http://localhost:{settings.backend_port}"
    )


# ── §3/§28 Status ────────────────────────────────────────────────────
@router.get("/status")
def telegram_status(user: AuthUser = Depends(require_auth)):
    binding = telegram_link_manager.get_binding(user.user_id)
    return {
        "bot_configured": _bot_configured(),
        "bot_username": settings.telegram_bot_username or None,  # never the token
        "webhook_configured": bool(webhook_secret()),
        "binding": _binding_view(binding),
        "environment": settings.app_env,
        "queue_stats": telegram_notification_queue.stats(),
    }


# ── §4 Account linking — token for the AUTHENTICATED user only ──────
@router.post("/link/generate")
async def telegram_link_generate(user: AuthUser = Depends(require_auth)):
    if not _bot_configured() or not settings.telegram_bot_username:
        raise HTTPException(400, "Telegram bot is not configured on the server")
    token = telegram_link_manager.generate_link_token(user.user_id, ttl_seconds=600)
    url = f"https://t.me/{settings.telegram_bot_username}?start={token}"
    return {
        "url": url,
        "ttl_seconds": 600,
        "bot_username": settings.telegram_bot_username,
        # Token is one-time, stored hashed server-side; never logged.
    }


@router.post("/link/revoke")
def telegram_link_revoke(user: AuthUser = Depends(require_auth)):
    telegram_link_manager.revoke(user.user_id)
    return {"status": "revoked"}


@router.get("/link/status")
def telegram_link_status(user: AuthUser = Depends(require_auth)):
    return _binding_view(telegram_link_manager.get_binding(user.user_id))


# ── §31 Notification preferences ─────────────────────────────────────
@router.get("/preferences")
def get_preferences(user: AuthUser = Depends(require_auth)):
    return notification_policy.get(user.user_id).model_dump()


@router.put("/preferences")
def set_preferences(prefs: NotificationPreferences, user: AuthUser = Depends(require_auth)):
    saved = notification_policy.set(user.user_id, prefs)
    return saved.model_dump()


@router.post("/preferences/reset")
def reset_preferences(user: AuthUser = Depends(require_auth)):
    """Reset notification preferences to defaults — instant effect, no restart."""
    prefs = notification_policy.reset(user.user_id)
    return prefs.model_dump()


@router.post("/preferences/bulk")
def bulk_preferences(updates: dict, user: AuthUser = Depends(require_auth)):
    """
    Bulk enable/disable all events for quick adjustment in Settings.
    Body: {"enable": true/false} → sets every event flag accordingly.
    """
    enable = bool(updates.get("enable", True))
    prefs = notification_policy.get(user.user_id)
    for k in list(prefs.events.keys()):
        prefs.events[k] = enable
    return notification_policy.set(user.user_id, prefs).model_dump()


# ── §30 Test message — through the queue + rate limiter ─────────────
@router.post("/test")
async def send_test_message(user: AuthUser = Depends(require_auth)):
    chat_id = telegram_link_manager.chat_for_user(user.user_id)
    if not chat_id:
        raise HTTPException(400, "Telegram chat is not linked. Connect Telegram first.")
    if not _bot_configured():
        raise HTTPException(400, "Telegram bot is not configured on the server")
    notification_id = await telegram_notification_queue.enqueue_test_message(user.user_id, chat_id)
    if not notification_id:
        raise HTTPException(500, "Failed to enqueue test message")
    return {"status": "enqueued", "notification_id": notification_id}


# ── §39 Notification audit trail ─────────────────────────────────────
@router.get("/audit")
def get_audit(user: AuthUser = Depends(require_auth), limit: int = 50):
    records = telegram_notification_queue.audit_for_user(user.user_id, limit=min(limit, 200))
    return {"records": [r.model_dump() for r in records]}


# ── §6 Webhook — non-blocking, secret-verified, deduplicated ────────
@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
):
    expected = webhook_secret()
    if not expected or not verify_telegram_secret(x_telegram_bot_api_secret_token, expected):
        # §6 — invalid secret → HTTP 403, do not process
        raise HTTPException(status_code=403, detail="invalid secret token")
    body = await request.json()
    update_id = body.get("update_id")
    if update_id is not None and is_duplicate_update(update_id):
        # §8 — process once
        return {"status": "ok", "detail": "duplicate ignored"}
    # §7 — enqueue and return immediately; no AI/broker/heavy work here
    await telegram_update_queue.enqueue(body)
    return {"status": "ok", "enqueued": True}


# ── §6 Webhook setup (calls Telegram setWebhook) ─────────────────────
@router.post("/webhook/setup")
async def telegram_webhook_setup(user: AuthUser = Depends(require_auth)):
    if user.role != "admin":
        raise HTTPException(403, "admin role required")
    if not _bot_configured():
        raise HTTPException(400, "TELEGRAM_BOT_TOKEN not configured")
    webhook_url = f"{_backend_base_url().rstrip('/')}/api/v1/telegram/webhook"
    result = await set_telegram_webhook(webhook_url)
    return {"webhook_url": webhook_url, "result": result}


# ── §27 Commands ─────────────────────────────────────────────────────
@router.get("/commands")
def telegram_commands():
    return {"commands": TELEGRAM_COMMANDS}


# ── Test/dev helper: publish an authoritative signal event ──────────
@router.post("/dev/publish-event")
async def dev_publish_event(event: SignalEvent, user: AuthUser = Depends(require_auth)):
    """
    DEV/TEST ONLY — pushes an already-authoritative signal event through the
    notification pipeline. Never generates or modifies a signal itself.
    """
    notification_ids = await telegram_notification_queue.publish_signal_event(event)
    return {"status": "published", "notification_ids": notification_ids}


@router.post("/dev/preview")
def dev_preview(event: SignalEvent, user: AuthUser = Depends(require_auth)):  # noqa: ARG001
    """
    Preview rendered Telegram message for a SignalEvent without enqueuing.
    Used by Settings → Telegram → Testing to show exactly what will be sent.
    """
    from app.institutional.telegram_templates import render_event_message

    text = render_event_message(event)
    return {"event_type": event.event_type, "instrument": event.instrument, "preview": text}


@router.post("/dev/quick-test")
async def dev_quick_test(
    instrument: str = "NIFTY",
    event_type: str = "SIGNAL_CONFIRMED",
    candle_timeframe: str = "5M",
    direction: str = "BULLISH",
    setup_type: str = "BREAKOUT",
    user: AuthUser = Depends(require_auth),
):
    """
    One-click Signal Center test — builds a realistic SignalEvent from current
    market snapshot (or demo fallback) and fans it out via the notification queue.
    Covers: adjustment testing without crafting JSON by hand.
    Query params kept simple for Settings UI: instrument, event_type, timeframe, direction.
    """
    import time
    import uuid

    instrument = instrument.upper()
    event_type = event_type.upper()
    candle_timeframe = candle_timeframe.upper()
    direction = direction.upper()
    setup_type = setup_type.upper()
    # Validate
    allowed_events = {
        "SIGNAL_TRIGGERED", "SIGNAL_CONFIRMED", "POSSIBLE_SETUP",
        "AI_CONFIRMED", "RISK_APPROVED", "RISK_REJECTED",
        "EXECUTED", "PARTIALLY_FILLED", "TARGET_HIT", "STOP_HIT", "SIGNAL_RESULT",
        "SIGNAL_EXPIRED", "SIGNAL_INVALIDATED",
    }
    if event_type not in allowed_events:
        raise HTTPException(400, f"Unknown event_type {event_type}. Allowed: {sorted(allowed_events)}")
    if instrument not in ("NIFTY", "BANKNIFTY", "SENSEX", "BTCUSD"):
        raise HTTPException(400, "instrument must be NIFTY/BANKNIFTY/SENSEX/BTCUSD")
    if candle_timeframe not in ("1M", "5M"):
        raise HTTPException(400, "candle_timeframe must be 1M or 5M")

    # Derive demo prices from live buffer if available
    spot: float | None = None
    try:
        from app.institutional.snapshot_buffer import synchronized_buffer
        latest = synchronized_buffer.get_latest(instrument)
        if latest and latest.event.price:
            spot = float(latest.event.price)
    except Exception:
        pass
    if spot is None:
        demo = {"NIFTY": 24885.0, "BANKNIFTY": 52100.0, "SENSEX": 81500.0, "BTCUSD": 65000.0}
        spot = demo.get(instrument, 10000.0)
    trigger = spot * 1.005 if direction == "BULLISH" else spot * 0.995
    stop = spot * 0.992 if direction == "BULLISH" else spot * 1.008
    target = spot * 1.012 if direction == "BULLISH" else spot * 0.988

    now_ms = int(time.time() * 1000)
    sig_id = f"test-{uuid.uuid4().hex[:8]}"

    # Build event_type-specific payloads
    kwargs: dict = dict(
        event_type=event_type,
        signal_id=sig_id,
        instrument=instrument,
        candle_timeframe=candle_timeframe,
        setup_type=setup_type if setup_type in ("BREAKOUT", "BREAKDOWN") else ("BREAKDOWN" if direction == "BEARISH" else "BREAKOUT"),
        direction=direction,
        status=event_type.replace("SIGNAL_", "") if event_type.startswith("SIGNAL_") else event_type,
        trigger_level=trigger,
        current_price=spot,
        confidence=84,
        breakout_pressure=78,
        false_breakout_risk=22,
        created_at_utc=now_ms,
    )
    # Enrich per event family
    if event_type in ("SIGNAL_TRIGGERED", "SIGNAL_CONFIRMED", "POSSIBLE_SETUP"):
        kwargs.update(dict(entry_low=trigger - 5, entry_high=trigger + 8, stop_loss=stop, target_low=target - 10, target_high=target + 10,
                           options_status="SUPPORTIVE", oi_pcr=1.18, ai_status="CONFIRMED", risk_status="APPROVED"))
    elif event_type == "AI_CONFIRMED":
        kwargs.update(dict(ai_decision="CONFIRM", ai_confidence=82, ai_status="CONFIRMED", ai_supporting=["breakout structure confirmed", "volume expansion"], ai_conflicts=[]))
    elif event_type == "RISK_APPROVED":
        kwargs.update(dict(risk_status="APPROVED", risk_portfolio="PASS", risk_exposure="Within Limits", risk_margin="PASS", risk_correlation="PASS"))
    elif event_type == "RISK_REJECTED":
        kwargs.update(dict(risk_status="REJECTED", risk_reason="Max position size exceeded — risk engine blocked order."))
    elif event_type == "EXECUTED":
        kwargs.update(dict(requested_qty=75, filled_qty=75, average_fill_price=spot, broker_order_id=f"ORD-{uuid.uuid4().hex[:6].upper()}"))
    elif event_type == "PARTIALLY_FILLED":
        kwargs.update(dict(requested_qty=75, filled_qty=40, remaining_qty=35, average_fill_price=spot, remaining_action="CANCEL / REVALIDATE"))
    elif event_type in ("TARGET_HIT", "STOP_HIT", "SIGNAL_RESULT"):
        is_target = "TARGET" in event_type
        kwargs.update(dict(result="TARGET_HIT" if is_target else "STOP_HIT", theoretical_entry=spot, exit_price=target if is_target else stop,
                           theoretical_pnl_points=42.5 if is_target else -18.0, holding_time="11m 04s",
                           theoretical_pnl_amount=1250.0 if is_target else -540.0))
        if event_type == "SIGNAL_RESULT":
            kwargs["result"] = "TARGET_HIT" if direction == "BULLISH" else "STOP_HIT"

    event = SignalEvent(**kwargs)
    ids = await telegram_notification_queue.publish_signal_event(event)
    # Also return preview for immediate UI feedback
    from app.institutional.telegram_templates import render_event_message
    preview = render_event_message(event)
    return {"status": "published", "notification_ids": ids, "signal_id": sig_id, "preview": preview, "event": event.model_dump()}


@router.get("/stats")
def telegram_stats(user: AuthUser = Depends(require_auth)):  # noqa: ARG001
    """Queue health for Settings → Telegram → Diagnostics (no secrets)."""
    from app.institutional.telegram import telegram_outbound_queue
    return {
        "notification_queue": telegram_notification_queue.stats(),
        "outbound_queue_size": telegram_outbound_queue._q.qsize(),
        "link_count": len(telegram_link_manager.all_bindings()),
    }
