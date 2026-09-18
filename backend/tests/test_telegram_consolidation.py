"""
Telegram consolidation tests.

Pins the phase-2 consolidation contract:
- exactly ONE raw `sendMessage` transport definition in the backend,
- every sender (command replies, plain text, signal notifications) enters the
  canonical notification queue and is delivered by that single transport,
- the queue worker lifecycle (start / ensure_started / stop) exists once and
  is idempotent for all three Telegram queues,
- local state persistence round-trips through app/core/atomic_json.py,
- rendered template output is byte-for-byte unchanged.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import time
from pathlib import Path

import pytest

from app.institutional import telegram as tg
from app.institutional.telegram_notifications import (
    SignalEvent,
    TelegramNotificationQueue,
    telegram_notification_queue,
)
from app.institutional.telegram_templates import (
    format_link_failure,
    format_link_success,
    format_status_reply,
    format_test_message,
    render_event_message,
)


@pytest.fixture(autouse=True)
def _clean_telegram_state():
    tg.telegram_link_manager._bindings.clear()
    tg.telegram_link_manager._by_chat.clear()
    tg.telegram_link_manager._tokens.clear()
    tg.telegram_rate_limiter.reset()
    telegram_notification_queue.reset_for_tests()
    yield
    tg.telegram_link_manager._bindings.clear()
    tg.telegram_link_manager._by_chat.clear()
    tg.telegram_link_manager._tokens.clear()
    tg.telegram_rate_limiter.reset()
    telegram_notification_queue.reset_for_tests()


def _link(user_id: str, chat_id: str) -> None:
    tg.telegram_link_manager._bindings[user_id] = {
        "telegram_chat_id": chat_id,
        "linked_at": time.time(),
        "status": "ACTIVE",
        "permissions": ["read"],
    }
    tg.telegram_link_manager._by_chat[chat_id] = user_id


def _event(**overrides) -> SignalEvent:
    base = dict(
        event_type="SIGNAL_CONFIRMED",
        signal_id="sig_123",
        instrument="NIFTY",
        candle_timeframe="5M",
        setup_type="BREAKOUT",
        direction="BULLISH",
        status="CONFIRMED",
        trigger_level=24700.0,
        current_price=24705.0,
        entry_low=24700.0,
        entry_high=24708.0,
        stop_loss=24680.0,
        target_low=24745.0,
        target_high=24765.0,
        confidence=88,
        options_status="SUPPORTIVE",
        ai_status="CONFIRMED",
        risk_status="APPROVED",
        created_at_utc=1_700_000_000_000,
    )
    base.update(overrides)
    return SignalEvent(**base)


async def _wait_for(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.02)
    return predicate()


# ── One transport ────────────────────────────────────────────────────
class TestSingleTransport:
    def test_single_sendmessage_definition(self):
        """All modules: exactly one raw sendMessage call site (telegram.py)."""
        app_dir = Path(tg.__file__).resolve().parents[1]
        hits: list[str] = []
        for py in app_dir.rglob("*.py"):
            source = py.read_text(encoding="utf-8", errors="ignore")
            hits.extend([py.name] * source.count("/sendMessage"))
        assert hits == ["telegram.py"], f"raw sendMessage definitions: {hits}"

    def test_telegram_module_has_no_direct_transport_sends(self):
        """telegram.py call sites go through the canonical pipeline, not the wire."""
        source = inspect.getsource(tg)
        assert "telegram_outbound_queue.enqueue(" not in source

    def test_worker_lifecycle_defined_once(self):
        queues = (tg.TelegramOutboundQueue, tg.TelegramUpdateQueue, TelegramNotificationQueue)
        for cls in queues:
            assert issubclass(cls, tg.TelegramWorkerBase)
            for name in ("_ensure_queue", "start", "ensure_started", "stop"):
                assert name in vars(tg.TelegramWorkerBase), f"{name} not on base"
                assert name not in vars(cls), f"{name} duplicated on {cls.__name__}"


# ── One sender pipeline ──────────────────────────────────────────────
class TestSenderPipeline:
    @pytest.mark.asyncio
    async def test_command_replies_use_canonical_queue(self, monkeypatch):
        _link("user_cmd", "555010")
        sent: list = []

        async def fake_send(self, msg):
            sent.append(msg)

        monkeypatch.setattr(tg.TelegramOutboundQueue, "_send_via_httpx", fake_send)
        await tg.telegram_outbound_queue.start()
        try:
            await tg.telegram_update_queue._handle(
                {"message": {"chat": {"id": "555010"}, "text": "/status"}}
            )
            # queued on the canonical notification pipeline, not the wire queue
            assert telegram_notification_queue._q.qsize() == 1
            assert tg.telegram_outbound_queue._q.qsize() == 0
            await telegram_notification_queue.start()
            assert await _wait_for(lambda: len(sent) == 1)
        finally:
            await telegram_notification_queue.stop()
            await tg.telegram_outbound_queue.stop()

        assert len(sent) == 1
        assert "STATUS" in sent[0].text
        assert sent[0].parse_mode == ""

    @pytest.mark.asyncio
    async def test_all_senders_share_one_pipeline(self, monkeypatch):
        """Text sends and signal events both surface at the single transport."""
        _link("user_sig", "555011")
        sent: list = []

        async def fake_send(self, msg):
            sent.append(msg)

        monkeypatch.setattr(tg.TelegramOutboundQueue, "_send_via_httpx", fake_send)
        await tg.telegram_outbound_queue.start()
        await telegram_notification_queue.start()
        try:
            notification_id = await telegram_notification_queue.enqueue_text(
                chat_id="555012", text="plain text"
            )
            assert notification_id is not None
            ids = await telegram_notification_queue.publish_signal_event(_event())
            assert len(ids) == 1
            assert await _wait_for(lambda: len(sent) == 2)
        finally:
            await telegram_notification_queue.stop()
            await tg.telegram_outbound_queue.stop()

        assert {m.chat_id for m in sent} == {"555011", "555012"}
        assert "NIFTY 5M BREAKOUT CONFIRMED" in next(m.text for m in sent if m.chat_id == "555011")

    @pytest.mark.asyncio
    async def test_transport_layer_does_not_retry_generic_failure(self, monkeypatch):
        """Outbound transport: non-429 failures are reported once, no retry."""
        attempts: list = []

        async def failing_send(self, msg):
            attempts.append(msg)
            raise RuntimeError("boom")

        monkeypatch.setattr(tg.TelegramOutboundQueue, "_send_via_httpx", failing_send)
        await tg.telegram_outbound_queue.start()
        results: list = []

        async def on_complete(success, error):
            results.append((success, error))

        try:
            await tg.telegram_outbound_queue.enqueue(
                tg.TelegramOutbound(chat_id="c", text="x", on_complete=on_complete)
            )
            assert await _wait_for(lambda: len(results) == 1)
        finally:
            await tg.telegram_outbound_queue.stop()

        assert len(attempts) == 1
        assert results[0][0] is False
        assert results[0][1]

    @pytest.mark.asyncio
    async def test_notification_queue_retries_then_dead_letters(self, monkeypatch):
        """Canonical queue semantics: any failure retried up to 3 attempts."""
        attempts: list = []

        async def failing_send(self, msg):
            attempts.append(msg)
            raise RuntimeError("boom")

        monkeypatch.setattr(tg.TelegramOutboundQueue, "_send_via_httpx", failing_send)

        real_sleep = asyncio.sleep

        async def fast_sleep(delay):
            await real_sleep(0)

        monkeypatch.setattr(asyncio, "sleep", fast_sleep)

        await tg.telegram_outbound_queue.start()
        try:
            notification_id = await telegram_notification_queue.enqueue_text(
                chat_id="c", text="x"
            )
            assert notification_id is not None
            for _ in range(3):
                job = await asyncio.wait_for(telegram_notification_queue._q.get(), timeout=2)
                await telegram_notification_queue._process(job)
        finally:
            await tg.telegram_outbound_queue.stop()

        assert len(attempts) == 3
        stats = telegram_notification_queue.stats()
        assert stats["dead_letter"] == 1
        audit = telegram_notification_queue._audit[0]
        assert audit.attempt_count == 3
        assert audit.delivery_status == "FAILED"


# ── Lifecycle ────────────────────────────────────────────────────────
class TestWorkerLifecycle:
    @pytest.mark.asyncio
    async def test_start_stop_idempotent_for_all_queues(self):
        queues = (
            tg.telegram_outbound_queue,
            tg.telegram_update_queue,
            telegram_notification_queue,
        )
        for queue in queues:
            await queue.start()
            await queue.start()
            first = queue._worker_task
            assert first is not None
            await queue.ensure_started()
            assert queue._worker_task is first

            await queue.stop()
            await queue.stop()
            assert queue._worker_task is None
            assert queue._running is False

            await queue.ensure_started()
            await queue.ensure_started()
            second = queue._worker_task
            assert second is not None and second is not first
            await queue.stop()
            assert queue._worker_task is None


# ── Persistence ──────────────────────────────────────────────────────
class TestPersistenceAtomicJson:
    def test_roundtrip_through_atomic_json(self, tmp_path, monkeypatch):
        import app.institutional.telegram_persistence as tp

        state_file = tmp_path / "telegram_state.json"
        monkeypatch.setattr(tp, "STATE_FILE", state_file)

        assert tp.read_local_file() == ({}, {})

        tp.write_local_file({"u1": {"telegram_chat_id": "9", "status": "ACTIVE"}})
        bindings, prefs = tp.read_local_file()
        assert bindings == {"u1": {"telegram_chat_id": "9", "status": "ACTIVE"}}
        assert prefs == {}

        tp.write_local_file(
            {"u1": {"telegram_chat_id": "9", "status": "ACTIVE"}},
            {"u1": {"breakout": False}},
        )
        _, prefs = tp.read_local_file()
        assert prefs == {"u1": {"breakout": False}}

        # preferences omitted → existing preferences preserved, payload shape kept
        tp.write_local_file({"u2": {"telegram_chat_id": "10", "status": "ACTIVE"}})
        bindings, prefs = tp.read_local_file()
        assert set(bindings) == {"u2"}
        assert prefs == {"u1": {"breakout": False}}
        raw = json.loads(state_file.read_text(encoding="utf-8"))
        assert set(raw) == {"bindings", "preferences"}
        assert raw["bindings"] == {"u2": {"telegram_chat_id": "10", "status": "ACTIVE"}}

        # atomic writer leaves no temp files behind
        assert not list(tmp_path.glob("telegram_state.*.tmp"))

        # corrupt cache → safe empty read (same fallback as before)
        state_file.write_text("{not-json", encoding="utf-8")
        assert tp.read_local_file() == ({}, {})

    def test_uses_shared_atomic_json_utility(self, tmp_path, monkeypatch):
        import app.institutional.telegram_persistence as tp

        calls: list = []

        def fake_atomic(path, payload, **kwargs):
            calls.append((path, payload, kwargs))
            return True

        state_file = tmp_path / "telegram_state.json"
        monkeypatch.setattr(tp, "STATE_FILE", state_file)
        monkeypatch.setattr(tp, "atomic_write_json", fake_atomic)

        tp.write_local_file(
            {"u1": {"telegram_chat_id": "1"}}, {"u1": {"breakout": True}}
        )
        assert len(calls) == 1
        path, payload, kwargs = calls[0]
        assert path == state_file
        assert payload == {
            "bindings": {"u1": {"telegram_chat_id": "1"}},
            "preferences": {"u1": {"breakout": True}},
        }
        assert kwargs.get("indent") == 2


# ── Templates unchanged ──────────────────────────────────────────────
class TestTemplatesUnchanged:
    def test_signal_confirmed_golden(self):
        assert render_event_message(_event()) == (
            "🟢 NIFTY 5M BREAKOUT CONFIRMED\n"
            "📅 15 Nov 2023, 03:43:20 IST\n"
            "\n"
            "Direction: LONG\n"
            "Status: CONFIRMED\n"
            "Trigger: 24,700\n"
            "Current: 24,705\n"
            "🎯 Entry: 24,700–24,708\n"
            "🛑 Stop Loss: 24,680\n"
            "🏁 Target: 24,745–24,765\n"
            "Confidence: 88.0%\n"
            "\n"
            "Options:\nSUPPORTIVE\n"
            "\n"
            "AI: CONFIRMED\n"
            "Risk: APPROVED\n"
            "\n"
            "Signal ID: sig_123"
        )

    def test_static_templates_golden(self):
        assert format_test_message("live") == (
            "✅ Telegram Connected\n\n"
            "Your trading signal notifications are working.\n\n"
            "Environment:\nLIVE\n\n"
            "TEST MESSAGE — not a trading signal."
        )
        assert format_link_success("droid_bot") == (
            "✅ Telegram Connected\n\n"
            "This chat is now linked to your trading account.\n"
            "You will receive 1M/5M breakout signal notifications here.\n\n"
            "Bot: @droid_bot\n\n"
            "Available commands:\n"
            "/briefing /auth /status /market /signal /positions /pnl /risk /alerts /settings"
        )
        assert format_link_failure("token expired") == (
            "❌ LINKING FAILED\n\n"
            "Reason: token expired\n\n"
            "Open the web app → Settings → Telegram → CONNECT TELEGRAM "
            "to generate a fresh link token, then send /start <token> here."
        )
        assert format_status_reply(True, "droid_bot", "production") == (
            "📊 STATUS\n\n"
            "Telegram: CONNECTED\n"
            "Bot: @droid_bot\n"
            "Environment: PRODUCTION\n\n"
            "Notifications: 1M/5M breakout signals, AI confirmation, risk, execution, results."
        )
