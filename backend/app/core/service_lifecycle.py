"""
Backend-owned persistent service lifecycle (FYERS + Telegram).

Lifecycle contract (4 phases — dashboard is independent of all of them):
  1. Backend startup:   start persistent services ONCE per process (lifespan).
  2. Frontend connect:  subscribe the client socket ONLY (central_feed.register_client).
  3. Frontend disconnect: remove the client socket ONLY (central_feed.unregister_client).
  4. Backend shutdown:  gracefully stop persistent services (lifespan teardown).

Rules enforced here:
  - Credentials always come from Render Environment Variables first
    (app.core.broker_runtime._env_config / settings); DB-saved settings only
    override at startup via apply_app_settings.
  - Exactly one provider stream and one Telegram stack per backend process,
    serialized through module-level asyncio locks.
  - Frontend request handlers NEVER call provider.start/stop or telegram
    start/stop directly — they call restart_provider_stream() / ensure_*()
    here, which are idempotent and never tied to any browser session.
  - Render restarts re-run lifespan → start_persistent_services() retries with
    exponential backoff until both services are up.
"""
from __future__ import annotations

import asyncio
import random

import structlog

logger = structlog.get_logger()

# Serializes ALL provider create/stop/start transitions process-wide so two
# concurrent requests (or a request racing lifespan) can never spawn a second
# upstream FYERS connection.
_provider_lock: asyncio.Lock | None = None
# Serializes Telegram stack starts for the same reason.
_telegram_lock: asyncio.Lock | None = None


def _get_provider_lock() -> asyncio.Lock:
    global _provider_lock
    if _provider_lock is None:
        _provider_lock = asyncio.Lock()
    return _provider_lock


def _get_telegram_lock() -> asyncio.Lock:
    global _telegram_lock
    if _telegram_lock is None:
        _telegram_lock = asyncio.Lock()
    return _telegram_lock


def _backoff_delay(attempt: int, initial: float = 1.0, maximum: float = 30.0) -> float:
    """Exponential backoff with jitter: min(max, init * 2^(n-1)) ±20%."""
    delay = min(maximum, initial * (2 ** max(0, attempt - 1)))
    jitter = delay * 0.2
    return round(max(0.5, delay + random.uniform(-jitter, jitter)), 2)


# ── Provider (FYERS) ─────────────────────────────────────────────

async def ensure_provider_stream() -> object:
    """Idempotent backend-owned start of the singleton provider stream.

    Safe to call from lifespan AND from control-plane endpoints (settings /
    tokens): if the stream is already running it is a no-op — it never
    restarts, duplicates, or ties the stream to the calling request.
    """
    from app.providers.registry import get_provider

    async with _get_provider_lock():
        provider = get_provider()
        try:
            if not getattr(provider, "_stream_running", False):
                await provider.start_stream()
                logger.info(
                    "lifecycle_provider_stream_started",
                    provider=getattr(provider, "provider_name", "unknown"),
                )
            return provider
        except Exception as e:
            logger.warning(
                "lifecycle_provider_stream_start_failed",
                provider=getattr(provider, "provider_name", "unknown"),
                error=str(e)[:200],
            )
            raise


async def restart_provider_stream(reason: str = "config_change") -> object:
    """Backend-owned restart of the singleton provider stream.

    Stops the previous instance BEFORE dropping it (no leaked second
    upstream), then creates and starts the new singleton — all under the
    process-wide lock. Used by settings save / token refresh / OAuth
    callbacks when broker config actually changed.
    """
    from app.providers.registry import (
        get_provider,
        reset_provider,
        stop_previous_provider_stream,
    )

    async with _get_provider_lock():
        await stop_previous_provider_stream()
        reset_provider()
        provider = get_provider()
        try:
            await provider.start_stream()
        except Exception as e:
            logger.warning(
                "lifecycle_provider_restart_start_failed",
                provider=getattr(provider, "provider_name", "unknown"),
                reason=reason,
                error=str(e)[:200],
            )
            raise
        logger.info(
            "lifecycle_provider_stream_restarted",
            provider=getattr(provider, "provider_name", "unknown"),
            reason=reason,
        )
        return provider


async def start_provider_with_retry(max_attempts: int = 8) -> object | None:
    """Start the provider stream at backend startup, retrying with backoff.

    Guarantees the FYERS connection comes up on Render (re)starts even when
    the first attempts fail (cold DB, DNS, auth propagation). Returns the
    provider, or None if all attempts fail (lifespan continues degraded —
    later control-plane calls can still trigger ensure_provider_stream).
    """
    last_error: str = ""
    for attempt in range(1, max_attempts + 1):
        try:
            return await ensure_provider_stream()
        except Exception as e:
            last_error = str(e)[:200]
            if attempt >= max_attempts:
                break
            delay = _backoff_delay(attempt)
            logger.warning(
                "lifecycle_provider_start_retry",
                attempt=attempt,
                max_attempts=max_attempts,
                delay_s=delay,
                error=last_error,
            )
            await asyncio.sleep(delay)
    logger.error(
        "lifecycle_provider_start_exhausted",
        max_attempts=max_attempts,
        error=last_error,
    )
    return None


async def stop_provider_stream() -> None:
    """Backend-shutdown stop of the provider stream (lifespan teardown only)."""
    from app.providers.registry import get_provider

    async with _get_provider_lock():
        try:
            provider = get_provider()
        except Exception:
            return
        try:
            await provider.stop_stream()
            logger.info(
                "lifecycle_provider_stream_stopped",
                provider=getattr(provider, "provider_name", "unknown"),
            )
        except Exception as e:
            logger.warning("lifecycle_provider_stop_failed", error=str(e)[:200])


# ── Telegram ─────────────────────────────────────────────────────

async def ensure_telegram_started() -> None:
    """Idempotent backend-owned start of the Telegram stack.

    Starts (or auto-recovers) the outbound, update, and notification queues
    without dropping queued messages. Safe to call from lifespan and from a
    periodic watchdog — never tied to any browser session.
    """
    async with _get_telegram_lock():
        from app.institutional.telegram import (
            telegram_outbound_queue,
            telegram_update_queue,
        )
        from app.institutional.telegram_notifications import (
            telegram_notification_queue,
        )

        await telegram_outbound_queue.ensure_started()
        await telegram_update_queue.ensure_started()
        await telegram_notification_queue.ensure_started()


async def register_telegram_webhook_with_retry(max_attempts: int = 6) -> bool:
    """Register the Telegram webhook at backend startup with backoff retries.

    No-op when TELEGRAM_BOT_TOKEN / BACKEND_PUBLIC_URL are unset (bot simply
    stays unregistered until configured — never crashes startup).
    """
    from app.core.config import settings as cfg

    if not cfg.telegram_bot_token or not cfg.backend_public_url:
        logger.info("lifecycle_telegram_webhook_skipped", hint="bot token or public URL not configured")
        return False

    from app.institutional.telegram import set_telegram_webhook

    webhook_url = f"{cfg.backend_public_url.rstrip('/')}/api/v1/telegram/webhook"
    for attempt in range(1, max_attempts + 1):
        try:
            res = await set_telegram_webhook(webhook_url)
            if res.get("ok"):
                logger.info("lifecycle_telegram_webhook_registered", webhook_url=webhook_url)
                return True
            logger.warning(
                "lifecycle_telegram_webhook_rejected",
                attempt=attempt,
                description=str(res.get("description", ""))[:200],
            )
        except Exception as e:
            logger.warning(
                "lifecycle_telegram_webhook_retry",
                attempt=attempt,
                max_attempts=max_attempts,
                error=str(e)[:200],
            )
        if attempt < max_attempts:
            await asyncio.sleep(_backoff_delay(attempt))
    logger.error("lifecycle_telegram_webhook_exhausted", webhook_url=webhook_url)
    return False


async def start_telegram_stack() -> None:
    """Backend-startup Telegram init: restore state, start queues, webhook.

    Each step is independent — one failing never prevents the others, and a
    failure here never affects the FYERS stream (separate try blocks in
    lifespan call this as one unit, but internally every step is guarded).
    """
    try:
        from app.institutional.telegram import telegram_link_manager
        from app.institutional.telegram_notifications import notification_policy

        await telegram_link_manager.restore_state()
        logger.info(
            "lifecycle_telegram_restore_complete",
            restored_bindings=len(telegram_link_manager.all_bindings()),
        )
    except Exception as e:
        logger.warning("lifecycle_telegram_restore_failed", error=str(e)[:200])

    try:
        from app.institutional.telegram_notifications import notification_policy as _np

        await _np.restore_state()
    except Exception as e:
        logger.warning("lifecycle_telegram_prefs_restore_failed", error=str(e)[:200])

    try:
        await ensure_telegram_started()
        logger.info("lifecycle_telegram_queues_started")
    except Exception as e:
        logger.warning("lifecycle_telegram_queues_start_failed", error=str(e)[:200])

    await register_telegram_webhook_with_retry()


async def stop_telegram_stack() -> None:
    """Backend-shutdown stop of the Telegram stack (lifespan teardown only)."""
    async with _get_telegram_lock():
        try:
            from app.institutional.telegram import (
                telegram_outbound_queue,
                telegram_update_queue,
            )

            await telegram_update_queue.stop()
            await telegram_outbound_queue.stop()
        except Exception as e:
            logger.warning("lifecycle_telegram_queues_stop_failed", error=str(e)[:200])
        try:
            from app.institutional.telegram_notifications import (
                telegram_notification_queue,
            )

            await telegram_notification_queue.stop()
        except Exception as e:
            logger.warning("lifecycle_telegram_notifications_stop_failed", error=str(e)[:200])
