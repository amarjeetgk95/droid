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
