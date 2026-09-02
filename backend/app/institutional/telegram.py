"""
Telegram Integration — §§55,56,57,58,59,60,61,62,63
Webhook with secret_token verification, non-blocking enqueue, async httpx, rate-limited queue,
account linking deep-link token, authorization, commands, confirmation, alerts.
Uses httpx.AsyncClient (not requests), Telegram Queue with rate limiter.
"""
from __future__ import annotations

import time
import hmac
import hashlib
import secrets
import asyncio
import string
from dataclasses import dataclass, field
from collections import deque, defaultdict
from typing import Literal, Any
import structlog

logger = structlog.get_logger()

# ── Rate Limiter — §58 ───────────────────────────────────────────────

class TelegramRateLimiter:
    """
    Global + per-chat rate limiting + 429 handling.
    Architecture: Signal A/B/C/D + AI Event → Telegram Queue → Rate Limiter → Telegram API
    """
    def __init__(self, global_per_second: float = 20.0, per_chat_per_second: float = 1.0, burst: int = 10):
        self.global_per_second = global_per_second
        self.per_chat_per_second = per_chat_per_second
        self.burst = burst
        self._global_tokens: float = burst
        self._global_last: float = time.time()
        self._per_chat_tokens: dict[str, float] = defaultdict(lambda: burst)
        self._per_chat_last: dict[str, float] = {}
        self._queue: deque = deque()
        self._queue_lock = asyncio.Lock()

    def _refill(self, chat_id: str) -> None:
        now = time.time()
        # Global
        elapsed = now - self._global_last
        self._global_tokens = min(self.burst, self._global_tokens + elapsed * self.global_per_second)
        self._global_last = now
        # Per-chat
        last = self._per_chat_last.get(chat_id, now)
        elapsed_c = now - last
        self._per_chat_tokens[chat_id] = min(float(self.burst), self._per_chat_tokens[chat_id] + elapsed_c * self.per_chat_per_second)
        self._per_chat_last[chat_id] = now

    async def acquire(self, chat_id: str, timeout: float = 30.0) -> bool:
        """
        Wait until tokens available for both global + per-chat.
        Handles 429 retry-after via sleeping.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            self._refill(chat_id)
            if self._global_tokens >= 1 and self._per_chat_tokens[chat_id] >= 1:
                self._global_tokens -= 1
                self._per_chat_tokens[chat_id] -= 1
                return True
            await asyncio.sleep(0.05)
        return False

    def reset(self) -> None:
        self._global_tokens = float(self.burst)
        self._global_last = time.time()
        self._per_chat_tokens.clear()
        self._per_chat_last.clear()

    async def handle_429(self, retry_after: int, chat_id: str) -> None:
        logger.warning("telegram_429", chat_id=chat_id, retry_after=retry_after)
        await asyncio.sleep(retry_after)


telegram_rate_limiter = TelegramRateLimiter()


# ── Outbound Queue ───────────────────────────────────────────────────
@dataclass
class TelegramOutbound:
    chat_id: str
    text: str
    parse_mode: str = "Markdown"  # empty string → send as plain text
    reply_markup: dict | None = None
    attempt: int = 0
    created_at: float = field(default_factory=time.time)
    # Optional delivery callback — used by the notification queue to track
    # SENT / FAILED status (§32). Never blocks the central send loop.
    on_complete: Any = None  # async callable(success: bool, error: str | None)


class TelegramOutboundQueue:
    def __init__(self, rate_limiter: TelegramRateLimiter | None = None):
        self._q: asyncio.Queue[TelegramOutbound] = asyncio.Queue()
        self._rl = rate_limiter or telegram_rate_limiter
        self._worker_task: asyncio.Task | None = None
        self._running = False

    async def enqueue(self, msg: TelegramOutbound) -> None:
        await self._q.put(msg)
        logger.debug("telegram_enqueued", chat_id=msg.chat_id)

    async def start(self) -> None:
        if self._running and self._worker_task and not self._worker_task.done():
            return
        self._q = asyncio.Queue()
        self._running = True
        self._worker_task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except (asyncio.CancelledError, Exception):
                pass
            self._worker_task = None

    async def _loop(self) -> None:
        while self._running:
            try:
                msg: TelegramOutbound = await asyncio.wait_for(self._q.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            ok = await self._rl.acquire(msg.chat_id)
            if not ok:
                logger.warning("telegram_rate_acquire_timeout", chat_id=msg.chat_id)
                # re-queue later
                await asyncio.sleep(1)
                await self._q.put(msg)
                continue
            try:
                await self._send_via_httpx(msg)
                if msg.on_complete is not None:
                    await msg.on_complete(True, None)
            except Exception as e:
                # Handle 429 if returned
                if "429" in str(e):
                    await self._rl.handle_429(2, msg.chat_id)
                    msg.attempt += 1
                    if msg.attempt < 3:
                        await self._q.put(msg)
                    elif msg.on_complete is not None:
                        await msg.on_complete(False, str(e))
                else:
                    logger.error("telegram_send_error", error=str(e), chat_id=msg.chat_id)
                    if msg.on_complete is not None:
                        await msg.on_complete(False, str(e))

    async def _send_via_httpx(self, msg: TelegramOutbound) -> None:
        """
        Use httpx.AsyncClient — never requests.post in async code (§57)
        Connection pooling, timeouts, retries handled here.
        In tests without token, this is a no-op (logs instead).
        """
        # Lazy import to avoid hard dependency if httpx not installed
        try:
            import httpx
        except Exception:
            logger.info("telegram_send_mock", chat_id=msg.chat_id, text=msg.text[:80])
            return
        # Fetch config lazily
        try:
            from app.core.config import settings
            token = getattr(settings, "telegram_bot_token", "") or ""
        except Exception:
            token = ""
        if not token:
            logger.info("telegram_send_no_token_mock", chat_id=msg.chat_id, text=msg.text[:100])
            return
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload: dict[str, Any] = {"chat_id": msg.chat_id, "text": msg.text}
        if msg.parse_mode:
            payload["parse_mode"] = msg.parse_mode
        if msg.reply_markup:
            payload["reply_markup"] = msg.reply_markup
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "2"))
                raise RuntimeError(f"429 retry_after {retry_after}")
            resp.raise_for_status()
            logger.info("telegram_sent", chat_id=msg.chat_id, message_id=resp.json().get("result", {}).get("message_id"))


telegram_outbound_queue = TelegramOutboundQueue()

# ── Webhook Verification §55 ─────────────────────────────────────────
def verify_telegram_secret(provided_token: str | None, expected_token: str) -> bool:
    if not expected_token: return False
    if not provided_token: return False
    return hmac.compare_digest(provided_token, expected_token)


# ── Deduplication for Telegram updates §56 ───────────────────────────
_seen_updates: set[str] = set()
def is_duplicate_update(update_id: str | int) -> bool:
    key = str(update_id)
    if key in _seen_updates: return True
    _seen_updates.add(key)
    if len(_seen_updates) > 10000:
        # Trim oldest half — approximate
        for k in list(_seen_updates)[:5000]:
            _seen_updates.discard(k)
    return False


# ── Account Linking — §59 deep-link token ───────────────────────────
ALLOWED_TOKEN_CHARS = string.ascii_letters + string.digits + "_-"

@dataclass
class LinkToken:
    token: str
    user_id: str
    created_at: float = field(default_factory=time.time)
    ttl_seconds: int = 600  # 5–10 min per spec
    used: bool = False

    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.ttl_seconds

    def hash(self) -> str:
        return hashlib.sha256(self.token.encode()).hexdigest()


class TelegramLinkManager:
    def __init__(self):
        self._tokens: dict[str, LinkToken] = {}  # hash -> token
        self._bindings: dict[str, dict] = {}  # user_id -> {telegram_chat_id, linked_at, status, permissions}
        self._by_chat: dict[str, str] = {}  # chat_id -> user_id

    def generate_link_token(self, user_id: str, ttl_seconds: int = 600) -> str:
        # Cryptographically random, <=64 chars, A-Z a-z 0-9 _ -
        # Generate 32 bytes -> 43 chars base64url trimmed
        raw = secrets.token_urlsafe(32)[:64]
        # Ensure only allowed chars
        filtered = "".join(c for c in raw if c in ALLOWED_TOKEN_CHARS)[:64]
        if len(filtered) < 16:
            filtered = "".join(secrets.choice(ALLOWED_TOKEN_CHARS) for _ in range(32))
        tok = LinkToken(token=filtered, user_id=user_id, ttl_seconds=ttl_seconds)
        self._tokens[tok.hash()] = tok
        return filtered

    def verify_and_bind(self, token: str, telegram_chat_id: str) -> tuple[bool, str]:
        h = hashlib.sha256(token.encode()).hexdigest()
        rec = self._tokens.get(h)
        if not rec: return False, "invalid token"
        if rec.used: return False, "token already used (one-time)"
        if rec.is_expired(): return False, "token expired"
        # Atomic binding — check not already bound elsewhere? Allow re-bind but invalidate old
        rec.used = True
        # Invalidate immediately after binding
        self._tokens.pop(h, None)
        now = time.time()
        self._bindings[rec.user_id] = {"telegram_chat_id": telegram_chat_id, "linked_at": now, "status": "ACTIVE", "permissions": ["read"]}
        self._by_chat[telegram_chat_id] = rec.user_id
        logger.info("telegram_linked", user_id=rec.user_id, chat_id=telegram_chat_id)
        return True, rec.user_id

    def is_authorized(self, telegram_chat_id: str) -> tuple[bool, str | None]:
        uid = self._by_chat.get(telegram_chat_id)
        if not uid: return False, None
        b = self._bindings.get(uid)
        if not b or b["status"] != "ACTIVE": return False, None
        return True, uid

    def get_binding(self, user_id: str) -> dict | None:
        return self._bindings.get(user_id)

    def revoke(self, user_id: str) -> None:
        b = self._bindings.pop(user_id, None)
        if b: self._by_chat.pop(b["telegram_chat_id"], None)

    def all_bindings(self) -> dict[str, dict]:
        """Snapshot of all active bindings — used by the notification fan-out (§28)."""
        return {
            uid: b for uid, b in self._bindings.items() if b.get("status") == "ACTIVE"
        }

    def chat_for_user(self, user_id: str) -> str | None:
        b = self._bindings.get(user_id)
        if b and b.get("status") == "ACTIVE":
            return b.get("telegram_chat_id")
        return None

    def check_command_permission(self, telegram_chat_id: str, command: str) -> bool:
        ok, uid = self.is_authorized(telegram_chat_id)
        if not ok: return False
        # Sensitive trading commands require explicit permission — for now only read allowed; extend as needed
        sensitive = {"/order", "/buy", "/sell", "/execute"}
        if command.lower() in sensitive:
            perms = self._bindings[uid].get("permissions", [])
            return "trade" in perms
        return True


telegram_link_manager = TelegramLinkManager()

# ── Commands §61 ─────────────────────────────────────────────────────
TELEGRAM_COMMANDS = [
    "/start",
    "/briefing",
    "/morning",
    "/auth",
    "/login",
    "/connect",
    "/status",
    "/market",
    "/signal",
    "/positions",
    "/pnl",
    "/risk",
    "/alerts",
    "/settings",
]

def handle_telegram_update(update: dict, secret_valid: bool) -> dict:
    """
    §56 webhook flow (non-blocking):
    verify secret → validate update → deduplicate → enqueue job → HTTP 200
    Do NOT do AI/broker/long analysis in webhook handler.
    """
    if not secret_valid:
        return {"status": 403, "detail": "invalid secret"}
    update_id = update.get("update_id", "")
    if is_duplicate_update(update_id):
        return {"status": 200, "detail": "duplicate ignored"}
    # Enqueue for background worker (caller should actually enqueue)
    # Minimal validation
    message = update.get("message") or update.get("edited_message") or {}
    chat_id = str((message.get("chat") or {}).get("id", ""))
    text = message.get("text", "")
    # Auth check deferred to worker — but we can quickly check for /start without auth
    return {"status": 200, "chat_id": chat_id, "text": text, "update_id": update_id}


# ── Confirmation keyboard §62 ────────────────────────────────────────
def live_order_confirmation_markup() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "✅ CONFIRM", "callback_data": "confirm_order"}, {"text": "❌ CANCEL", "callback_data": "cancel_order"}]
        ]
    }

def format_live_order_alert(instrument: str, direction: str, entry: str, quantity: str, stop: str) -> str:
    return (
        f"⚠️ LIVE ORDER\n\n"
        f"{instrument}\n"
        f"Direction: {direction}\n"
        f"Entry: {entry}\n"
        f"Quantity: {quantity}\n"
        f"Stop: {stop}"
    )


# ── setWebhook management (§6) ───────────────────────────────────────
async def set_telegram_webhook(webhook_url: str) -> dict:
    """
    Configure Telegram's webhook with the secret token (§6).
    Returns Telegram API response. Never returns the bot token.
    """
    import httpx  # local import — async HTTP only (§26)
    from app.core.config import settings
    token = settings.telegram_bot_token or ""
    if not token:
        return {"ok": False, "description": "TELEGRAM_BOT_TOKEN not configured"}
    secret = webhook_secret()
    params: dict[str, Any] = {"url": webhook_url}
    if secret:
        params["secret_token"] = secret
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        resp = await client.post(f"https://api.telegram.org/bot{token}/setWebhook", json=params)
        data = resp.json()
        # Never echo the token back
        return {"ok": bool(data.get("ok")), "description": data.get("description", "")}


def webhook_secret() -> str:
    """Effective webhook secret — supports TELEGRAM_WEBHOOK_SECRET and legacy TELEGRAM_SECRET_TOKEN."""
    from app.core.config import settings
    return (
        getattr(settings, "telegram_webhook_secret", "")
        or settings.telegram_secret_token
        or ""
    )


# ── Webhook update worker (§5/§7/§8) ────────────────────────────────
class TelegramUpdateQueue:
    """
    Webhook only: receive → authenticate → validate → deduplicate → enqueue → 200.
    This worker performs the actual (fast, non-trading) update handling:
    /start <token> account linking and read-only command replies (§27).
    AI requests, broker calls and heavy analysis are never executed here.
    """
    def __init__(self) -> None:
        self._q: asyncio.Queue[dict] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._running = False

    async def enqueue(self, update: dict) -> None:
        await self._q.put(update)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        while self._running:
            try:
                update = await asyncio.wait_for(self._q.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            try:
                await self._handle(update)
            except Exception as e:
                logger.error("telegram_update_worker_error", error=str(e))

    async def _handle(self, update: dict) -> None:
        message = update.get("message") or update.get("edited_message") or {}
        chat_id = str((message.get("chat") or {}).get("id", ""))
        text = (message.get("text") or "").strip()
        if not chat_id or not text.startswith("/"):
            return
        from app.institutional.telegram_templates import (
            format_link_success, format_link_failure, format_status_reply,
        )
        from app.core.config import settings
        bot_username = settings.telegram_bot_username or "your_bot"
        environment = settings.app_env

        parts = text.split(maxsplit=1)
        command = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        # ── /start <token> — account linking (§5) ────────────────────
        if command == "/start" and arg:
            ok, info = telegram_link_manager.verify_and_bind(arg, chat_id)
            if ok:
                reply = format_link_success(bot_username)
                logger.info("telegram_account_linked", chat_id=chat_id)
            else:
                reply = format_link_failure(info)
            await telegram_outbound_queue.enqueue(TelegramOutbound(chat_id=chat_id, text=reply, parse_mode=""))
            return
        if command == "/start":
            await telegram_outbound_queue.enqueue(TelegramOutbound(
                chat_id=chat_id, text=format_link_failure("no link token provided"), parse_mode=""))
            return

        # ── §37 — every other command requires a linked, authorized chat ──
        authorized, user_id = telegram_link_manager.is_authorized(chat_id)
        if not authorized:
            await telegram_outbound_queue.enqueue(TelegramOutbound(
                chat_id=chat_id,
                text=format_link_failure("this chat is not linked to a web-app account"),
                parse_mode=""))
            return
        if not telegram_link_manager.check_command_permission(chat_id, command):
            await telegram_outbound_queue.enqueue(TelegramOutbound(
                chat_id=chat_id, text="⛔ Not authorized for this command.", parse_mode=""))
            return

        # ── /briefing or /morning — on-demand morning briefing ──
        if command in ("/briefing", "/morning"):
            from app.services.morning_briefing_service import morning_briefing_service
            await morning_briefing_service.send_briefing_to_chat(chat_id)
            return

        # ── /auth or /login command — 1-click broker authorization ──
        if command in ("/auth", "/login", "/connect"):
            from app.core.broker_runtime import get_config
            broker_cfg = get_config()
            provider_name = broker_cfg.provider.lower()
            backend_url = getattr(settings, "backend_public_url", "") or "https://droid-backend-emeq.onrender.com"
            login_url = f"{backend_url}/api/v1/tokens/{provider_name}/login"
            
            auth_text = (
                f"🔐 *DROID Broker Authentication*\n\n"
                f"• Active Provider: *{provider_name.upper()}*\n"
                f"• Backend: Render (`{environment}`)\n\n"
                f"Tap the button below to complete today's 2FA authentication. "
                f"Your session will activate automatically."
            )
            markup = {
                "inline_keyboard": [
                    [{"text": f"🚀 1-Click Authorize {provider_name.upper()}", "url": login_url}]
                ]
            }
            await telegram_outbound_queue.enqueue(
                TelegramOutbound(chat_id=chat_id, text=auth_text, parse_mode="Markdown", reply_markup=markup)
            )
            return

        # ── Read-only commands (§27) ─────────────────────────────────
        replies: dict[str, str] = {
            "/status": format_status_reply(True, bot_username, environment),
            "/market": "📈 MARKET\n\nOpen the web dashboard for live market intelligence.",
            "/signal": "🎯 SIGNALS\n\nOpen the web dashboard → BREAKOUT SETUPS for the authoritative 1M/5M signals.",
            "/positions": "📋 POSITIONS\n\nOpen the web dashboard for live positions.",
            "/pnl": "💰 P&L\n\nOpen the web dashboard for live P&L.",
            "/risk": "🛡 RISK\n\nOpen the web dashboard for live risk status.",
            "/alerts": "🔔 ALERTS\n\nYou will receive 1M/5M breakout, AI, risk, execution and result alerts here.",
            "/settings": "⚙ SETTINGS\n\nManage notification preferences in the web app → Settings → Telegram.",
        }
        reply = replies.get(command)
        if reply:
            await telegram_outbound_queue.enqueue(TelegramOutbound(chat_id=chat_id, text=reply, parse_mode=""))


telegram_update_queue = TelegramUpdateQueue()
