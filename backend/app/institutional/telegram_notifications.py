"""
Telegram Notification Queue — §§9,10,11,12,28,31,32,33,34,35,39
Consumes authoritative Signal Events (published by the Signal Engine after the
signal is persisted) and delivers Telegram notifications via the central
rate-limited outbound queue. Telegram is strictly downstream: nothing here
queries the market, re-derives signals, or blocks the Signal Engine.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Literal
from pydantic import BaseModel, Field

import structlog

logger = structlog.get_logger()

NotificationStatus = Literal["PENDING", "SENT", "FAILED", "RETRYING", "DEDUPED", "SKIPPED"]


class SignalEvent(BaseModel):
    """
    Structured signal event emitted by the authoritative Signal Engine (§9).
    Telegram consumes this event — it must NEVER query the market to
    independently determine whether a signal exists.
    """
    event_type: str
    signal_id: str
    instrument: str
    candle_timeframe: str = "5M"  # 1M / 5M — stored by the Signal Engine (§13)
    setup_type: str = "BREAKOUT"  # BREAKOUT / BREAKDOWN
    direction: str = "NEUTRAL"    # BULLISH / BEARISH
    status: str | None = None

    # Optional authoritative payload — only included when the engine provides it
    trigger_level: float | None = None
    current_price: float | None = None
    entry_low: float | None = None
    entry_high: float | None = None
    stop_loss: float | None = None
    target_low: float | None = None
    target_high: float | None = None
    confidence: float | None = None
    breakout_pressure: int | None = None
    false_breakout_risk: float | None = None
    options_status: str | None = None
    major_call_resistance: float | None = None
    major_put_support: float | None = None
    oi_pcr: float | None = None
    futures_status: str | None = None
    ai_status: str | None = None
    ai_decision: str | None = None
    ai_confidence: float | None = None
    ai_supporting: list[str] = Field(default_factory=list)
    ai_conflicts: list[str] = Field(default_factory=list)
    risk_status: str | None = None
    risk_reason: str | None = None
    risk_portfolio: str | None = None
    risk_exposure: str | None = None
    risk_margin: str | None = None
    risk_correlation: str | None = None
    requested_qty: float | None = None
    filled_qty: float | None = None
    remaining_qty: float | None = None
    average_fill_price: float | None = None
    broker_order_id: str | None = None
    remaining_action: str | None = None
    # §23 result fields
    result: str | None = None
    result_reason: str | None = None
    theoretical_entry: float | None = None
    exit_price: float | None = None
    theoretical_pnl_points: float | None = None
    theoretical_pnl_amount: float | None = None
    actual_pnl_amount: float | None = None
    pnl_percent: float | None = None
    holding_time: str | None = None
    holding_time_seconds: float | None = None
    # §24 theoretical vs actual kept separate
    # Paper Trading Execution fields
    paper_order_id: str | None = None
    paper_fill_price: float | None = None
    paper_filled_qty: int | None = None
    paper_status: str | None = None
    paper_side: str | None = None

    created_at_utc: int = Field(default_factory=lambda: int(time.time() * 1000))


# ── §31/§12 Notification Policy ──────────────────────────────────────
class NotificationPreferences(BaseModel):
    """Per-user notification preferences (§31)."""
    events: dict[str, bool] = Field(default_factory=lambda: {
        "SIGNAL_TRIGGERED": True, "SIGNAL_CONFIRMED": True, "AI_CONFIRMED": True,
        "RISK_APPROVED": True, "RISK_REJECTED": True, "EXECUTED": True,
        "PARTIALLY_FILLED": True, "TARGET_HIT": True, "STOP_HIT": True,
        "SIGNAL_RESULT": True,
        "POSSIBLE_SETUP": False, "SIGNAL_EXPIRED": False, "SIGNAL_INVALIDATED": False,
    })
    instruments: dict[str, bool] = Field(default_factory=lambda: {
        "NIFTY": True, "BANKNIFTY": True, "SENSEX": True, "BTCUSD": True,
    })
    timeframes: dict[str, bool] = Field(default_factory=lambda: {"1M": True, "5M": True})
    breakout: bool = True
    breakdown: bool = True

    def allows(self, event: SignalEvent) -> tuple[bool, str]:
        et = event.event_type
        if not self.events.get(et, False):
            return False, f"event {et} disabled"
        if not self.instruments.get(event.instrument.upper(), False):
            return False, f"instrument {event.instrument} disabled"
        if not self.timeframes.get(event.candle_timeframe.upper(), False):
            return False, f"timeframe {event.candle_timeframe} disabled"
        setup = (event.setup_type or "BREAKOUT").upper()
        if setup == "BREAKDOWN" and not self.breakdown:
            return False, "breakdown alerts disabled"
        if setup == "BREAKOUT" and not self.breakout:
            return False, "breakout alerts disabled"
        return True, "ok"


class NotificationPolicy:
    """§12 — Do not send every internal signal state; honor user preferences."""
    def __init__(self) -> None:
        self._prefs: dict[str, NotificationPreferences] = {}
        self._load_local_state()

    def _load_local_state(self) -> None:
        try:
            from app.institutional.telegram_persistence import read_local_file
            _, prefs_raw = read_local_file()
            if prefs_raw:
                for uid, p in prefs_raw.items():
                    if isinstance(p, dict):
                        self._prefs[uid] = NotificationPreferences(**p)
        except Exception as e:
            logger.warning("telegram_policy_local_load_failed", error=str(e))

    async def restore_state(self) -> None:
        """Full restore from DB and local snapshot on application startup."""
        try:
            from app.institutional.telegram_persistence import restore_telegram_state_from_db
            _, prefs_raw = await restore_telegram_state_from_db()
            if prefs_raw:
                for uid, p in prefs_raw.items():
                    if isinstance(p, dict):
                        self._prefs[uid] = NotificationPreferences(**p)
                logger.info("telegram_policy_restored", total_users=len(self._prefs))
        except Exception as e:
            logger.warning("telegram_policy_restore_failed", error=str(e))

    def get(self, user_id: str) -> NotificationPreferences:
        if user_id not in self._prefs:
            self._prefs[user_id] = NotificationPreferences()
        return self._prefs[user_id]

    def set(self, user_id: str, prefs: NotificationPreferences) -> NotificationPreferences:
        self._prefs[user_id] = prefs
        try:
            from app.institutional.telegram_persistence import write_local_file, persist_user_preferences_to_db
            prefs_dict = {uid: p.model_dump() for uid, p in self._prefs.items()}
            write_local_file(bindings={}, preferences=prefs_dict)
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(persist_user_preferences_to_db(user_id, prefs.model_dump()))
            except RuntimeError:
                pass
        except Exception as e:
            logger.warning("telegram_preferences_save_failed", error=str(e))
        return prefs

    def reset(self, user_id: str) -> NotificationPreferences:
        self._prefs.pop(user_id, None)
        try:
            from app.institutional.telegram_persistence import write_local_file, persist_user_preferences_to_db
            prefs_dict = {uid: p.model_dump() for uid, p in self._prefs.items()}
            write_local_file(bindings={}, preferences=prefs_dict)
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(persist_user_preferences_to_db(user_id, None))
            except RuntimeError:
                pass
        except Exception as e:
            logger.warning("telegram_preferences_reset_save_failed", error=str(e))
        return self.get(user_id)


notification_policy = NotificationPolicy()


# ── Instrument-level event throttle (engine-side anti-spam) ──────────
_instrument_event_ts: dict[str, float] = {}


def should_publish_instrument_event(instrument: str, event_type: str, min_interval_s: float = 60.0) -> bool:
    """
    Prevents notification storms when the Signal Engine re-evaluates on each
    poll: the same (instrument, event_type) is published at most once per
    interval. Per-signal dedup (§33) still applies downstream.
    """
    key = f"{instrument}:{event_type}"
    now = time.time()
    last = _instrument_event_ts.get(key, 0.0)
    if now - last < min_interval_s:
        return False
    _instrument_event_ts[key] = now
    return True


# ── §11 Queue payload ────────────────────────────────────────────────
class NotificationJob(BaseModel):
    notification_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    signal_id: str
    event_type: str
    user_id: str
    telegram_chat_id: str
    message_type: str = "signal_alert"  # signal_alert / test / link_confirmation
    event_payload: dict[str, Any] = Field(default_factory=dict)
    created_at_utc: int = Field(default_factory=lambda: int(time.time() * 1000))
    priority: int = 5  # lower = higher priority
    attempt_count: int = 0
    status: str = "PENDING"


# ── §39 Audit record (never stores the bot token) ────────────────────
class NotificationAuditRecord(BaseModel):
    notification_id: str
    signal_id: str
    user_id: str
    telegram_chat_id: str
    event_type: str
    message_type: str
    created_at_utc: int
    sent_at_utc: int | None = None
    delivery_status: str = "PENDING"
    attempt_count: int = 0
    error: str | None = None


class TelegramNotificationQueue:
    """
    Signal Event → Notification Policy → Telegram Queue → Telegram Worker
    (worker then sends ONLY via the central rate-limited telegram_outbound_queue).
    """
    MAX_AUDIT = 2000
    MAX_DEDUP = 10000
    MAX_DEAD_LETTER = 500

    def __init__(self) -> None:
        self._q: asyncio.Queue[NotificationJob] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._running = False
        self._audit: list[NotificationAuditRecord] = []
        self._dedup_keys: dict[str, str] = {}  # dedup_key -> notification_id (§33)
        self._dead_letter: list[NotificationJob] = []

    # ── Publishing (called by the Signal Engine) ─────────────────────
    async def publish_signal_event(self, event: SignalEvent) -> list[str]:
        """
        Fan out one authoritative signal event to all linked users whose
        preferences allow it. NEVER raises — a Telegram failure must not
        affect the Signal Engine (§35). Returns created notification_ids.
        """
        created: list[str] = []
        try:
            from app.institutional.telegram import telegram_link_manager
            for user_id, binding in list(telegram_link_manager.all_bindings().items()):
                chat_id = binding.get("telegram_chat_id")
                if not chat_id or binding.get("status") != "ACTIVE":
                    continue
                prefs = notification_policy.get(user_id)
                ok, reason = prefs.allows(event)
                if not ok:
                    self._record(NotificationAuditRecord(
                        notification_id=str(uuid.uuid4()), signal_id=event.signal_id,
                        user_id=user_id, telegram_chat_id=str(chat_id),
                        event_type=event.event_type, message_type="signal_alert",
                        created_at_utc=event.created_at_utc, delivery_status="SKIPPED",
                        error=reason,
                    ))
                    continue
                # §33 deterministic dedup key: signal_id + event_type + user_id
                dedup_key = f"{event.signal_id}:{event.event_type}:{user_id}"
                if dedup_key in self._dedup_keys:
                    logger.debug("telegram_notification_deduped", dedup_key=dedup_key)
                    continue
                job = NotificationJob(
                    signal_id=event.signal_id, event_type=event.event_type,
                    user_id=user_id, telegram_chat_id=str(chat_id),
                    event_payload=event.model_dump(), priority=1,
                )
                if len(self._dedup_keys) >= self.MAX_DEDUP:
                    self._dedup_keys.clear()
                self._dedup_keys[dedup_key] = job.notification_id
                self._record(NotificationAuditRecord(
                    notification_id=job.notification_id, signal_id=job.signal_id,
                    user_id=job.user_id, telegram_chat_id=job.telegram_chat_id,
                    event_type=job.event_type, message_type=job.message_type,
                    created_at_utc=job.created_at_utc, delivery_status="PENDING",
                ))
                await self._q.put(job)
                created.append(job.notification_id)
            if created:
                logger.info("telegram_notifications_queued", event_type=event.event_type,
                            signal_id=event.signal_id, count=len(created))
        except Exception as e:  # §34 — never propagate to the Signal Engine
            logger.warning("telegram_publish_failed_non_fatal", error=str(e))
        return created

    async def enqueue_test_message(self, user_id: str, chat_id: str) -> str | None:
        """§30 — the test message passes through the queue + rate limiter."""
        try:
            job = NotificationJob(
                signal_id="test-message", event_type="TEST_MESSAGE",
                user_id=user_id, telegram_chat_id=str(chat_id), message_type="test",
            )
            self._record(NotificationAuditRecord(
                notification_id=job.notification_id, signal_id=job.signal_id,
                user_id=job.user_id, telegram_chat_id=job.telegram_chat_id,
                event_type=job.event_type, message_type=job.message_type,
                created_at_utc=job.created_at_utc, delivery_status="PENDING",
            ))
            await self._q.put(job)
            return job.notification_id
        except Exception as e:
            logger.warning("telegram_test_enqueue_failed", error=str(e))
            return None


    # ── Worker ───────────────────────────────────────────────────────
    async def start(self) -> None:
        # Backend-lifecycle start: preserve queued jobs across restarts
        # (never drop), single worker per process.
        if self._running and self._worker_task and not self._worker_task.done():
            return
        if self._q is None:
            self._q = asyncio.Queue()
        self._running = True
        self._worker_task = asyncio.create_task(self._loop())

    async def ensure_started(self) -> None:
        """Auto-recovery: restart the worker if it died, keep queued jobs."""
        if self._running and self._worker_task and not self._worker_task.done():
            return
        if self._q is None:
            self._q = asyncio.Queue()
        self._running = True
        self._worker_task = asyncio.create_task(self._loop())
        logger.info("telegram_notification_worker_running")

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
                job = await asyncio.wait_for(self._q.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            try:
                await self._process(job)
            except Exception as e:
                logger.error("telegram_notification_worker_error", error=str(e))

    async def _process(self, job: NotificationJob) -> None:
        from app.institutional.telegram import telegram_outbound_queue, TelegramOutbound
        from app.institutional.telegram_templates import render_event_message, format_test_message

        job.attempt_count += 1
        self._update_audit(job.notification_id,
                           delivery_status="RETRYING" if job.attempt_count > 1 else "PENDING",
                           attempt_count=job.attempt_count)
        try:
            from app.core.config import settings
            environment = settings.app_env
        except Exception:
            environment = "development"

        if job.message_type == "test":
            text = format_test_message(environment)
        else:
            event = SignalEvent(**job.event_payload)
            text = render_event_message(event)

        done = asyncio.Event()
        result: dict[str, Any] = {}

        async def on_complete(success: bool, error: str | None) -> None:
            result["success"] = success
            result["error"] = error
            done.set()

        msg = TelegramOutbound(
            chat_id=job.telegram_chat_id, text=text, parse_mode="",
            on_complete=on_complete,
        )
        await telegram_outbound_queue.enqueue(msg)
        try:
            await asyncio.wait_for(done.wait(), timeout=60.0)
        except asyncio.TimeoutError:
            result["success"] = False
            result["error"] = "delivery timeout"

        if result.get("success"):
            self._update_audit(job.notification_id, delivery_status="SENT",
                               sent_at_utc=int(time.time() * 1000))
            logger.info("telegram_notification_sent", notification_id=job.notification_id,
                        chat_id=job.telegram_chat_id, event_type=job.event_type)
        else:
            error = result.get("error") or "unknown error"
            if job.attempt_count < 3:
                self._update_audit(job.notification_id, delivery_status="RETRYING", error=error)
                await asyncio.sleep(2 * job.attempt_count)
                await self._q.put(job)
            else:
                self._update_audit(job.notification_id, delivery_status="FAILED", error=error)
                if len(self._dead_letter) >= self.MAX_DEAD_LETTER:
                    self._dead_letter.pop(0)
                self._dead_letter.append(job)
                logger.warning("telegram_notification_dead_letter",
                               notification_id=job.notification_id, error=error)

    # ── Audit (§39) ──────────────────────────────────────────────────
    def _record(self, rec: NotificationAuditRecord) -> None:
        self._audit.append(rec)
        if len(self._audit) > self.MAX_AUDIT:
            self._audit = self._audit[-self.MAX_AUDIT:]

    def _update_audit(self, notification_id: str, **fields: Any) -> None:
        for rec in reversed(self._audit):
            if rec.notification_id == notification_id:
                for k, v in fields.items():
                    setattr(rec, k, v)
                return

    def audit_for_user(self, user_id: str, limit: int = 100) -> list[NotificationAuditRecord]:
        return [r for r in reversed(self._audit) if r.user_id == user_id][:limit]

    def stats(self) -> dict[str, Any]:
        statuses: dict[str, int] = {}
        for r in self._audit:
            statuses[r.delivery_status] = statuses.get(r.delivery_status, 0) + 1
        return {"total": len(self._audit), "statuses": statuses,
                "dead_letter": len(self._dead_letter), "queued": self._q.qsize()}

    # ── Test introspection ───────────────────────────────────────────
    def reset_for_tests(self) -> None:
        self._audit.clear()
        self._dedup_keys.clear()
        self._dead_letter.clear()
        self._q = asyncio.Queue()


telegram_notification_queue = TelegramNotificationQueue()
