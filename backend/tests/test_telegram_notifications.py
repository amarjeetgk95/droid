"""
Telegram Signal Integration — End-to-End & Unit Tests
Covers: §2 secret config, §4/§5 linking tokens, §6 webhook, §8 dedup, §9/§10
signal events, §12 policy, §13 timeframe, §14-24 templates, §25 rate limiter,
§30 test message, §33 notification dedup, §35 failure isolation, §39 audit.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from app.institutional.telegram import (
    TelegramLinkManager,
    is_duplicate_update,
    verify_telegram_secret,
    telegram_outbound_queue,
    TelegramOutbound,
)
from app.institutional.telegram_notifications import (
    SignalEvent,
    NotificationPreferences,
    telegram_notification_queue,
)
from app.institutional.telegram_templates import (
    format_possible_setup,
    format_signal_state,
    format_signal_result,
    format_test_message,
    render_event_message,
)


@pytest.fixture(autouse=True)
def _clean_state():
    from app.institutional import telegram as tg
    telegram_notification_queue.reset_for_tests()
    tg.telegram_link_manager._bindings.clear()
    tg.telegram_link_manager._by_chat.clear()
    tg.telegram_link_manager._tokens.clear()
    yield
    telegram_notification_queue.reset_for_tests()
    tg.telegram_link_manager._bindings.clear()
    tg.telegram_link_manager._by_chat.clear()
    tg.telegram_link_manager._tokens.clear()


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
    )
    base.update(overrides)
    return SignalEvent(**base)


# ── §4/§5 Linking tokens ─────────────────────────────────────────────
class TestLinkTokens:
    def test_token_charset_and_length(self):
        mgr = TelegramLinkManager()
        tok = mgr.generate_link_token("user_1")
        assert len(tok) <= 64 and len(tok) >= 16
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
        assert set(tok) <= allowed

    def test_token_one_time_use(self):
        mgr = TelegramLinkManager()
        tok = mgr.generate_link_token("user_1")
        ok1, _ = mgr.verify_and_bind(tok, "111")
        assert ok1
        ok2, reason = mgr.verify_and_bind(tok, "222")  # reuse must fail — token invalidated on use
        assert not ok2
        assert reason  # any rejection reason (invalidated/one-time/invalid)

    def test_token_expired(self):
        mgr = TelegramLinkManager()
        tok = mgr.generate_link_token("user_1", ttl_seconds=300)
        # force-expire the stored token (stored hashed)
        for h, r in mgr._tokens.items():
            r.created_at = time.time() - 400
            assert r.is_expired()
        ok, reason = mgr.verify_and_bind(tok, "111")
        assert not ok
        assert "expired" in reason

    def test_token_stored_hashed(self):
        mgr = TelegramLinkManager()
        tok = mgr.generate_link_token("user_1")
        assert tok not in mgr._tokens  # raw token never stored
        assert all(len(h) == 64 for h in mgr._tokens)  # sha256 hex

    def test_binding_maps_user_and_chat(self):
        mgr = TelegramLinkManager()
        tok = mgr.generate_link_token("user_1")
        mgr.verify_and_bind(tok, "111")
        assert mgr.chat_for_user("user_1") == "111"
        ok, uid = mgr.is_authorized("111")
        assert ok and uid == "user_1"
        assert mgr.is_authorized("999")[0] is False


# ── §6/§8 Webhook ────────────────────────────────────────────────────
class TestWebhookSecurity:
    def test_secret_verification(self):
        assert verify_telegram_secret("abc", "abc") is True
        assert verify_telegram_secret("abc", "xyz") is False
        assert verify_telegram_secret(None, "abc") is False
        assert verify_telegram_secret("abc", "") is False

    def test_update_dedup(self):
        assert is_duplicate_update(1001) is False
        assert is_duplicate_update(1001) is True  # same update → duplicate
        assert is_duplicate_update(1002) is False


# ── §12 Notification policy ──────────────────────────────────────────
class TestNotificationPolicy:
    def test_defaults_on_events(self):
        prefs = NotificationPreferences()
        ok, _ = prefs.allows(_event(event_type="SIGNAL_CONFIRMED"))
        assert ok
        ok, _ = prefs.allows(_event(event_type="SIGNAL_TRIGGERED"))
        assert ok
        ok, _ = prefs.allows(_event(event_type="EXECUTED"))
        assert ok

    def test_optional_events_off_by_default(self):
        prefs = NotificationPreferences()
        for et in ("POSSIBLE_SETUP", "SIGNAL_EXPIRED", "SIGNAL_INVALIDATED"):
            ok, _ = prefs.allows(_event(event_type=et))
            assert not ok

    def test_instrument_toggle(self):
        prefs = NotificationPreferences()
        prefs.instruments["NIFTY"] = False
        ok, reason = prefs.allows(_event(instrument="NIFTY"))
        assert not ok and "NIFTY" in reason

    def test_timeframe_toggle(self):
        prefs = NotificationPreferences()
        prefs.timeframes["1M"] = False
        ok, _ = prefs.allows(_event(candle_timeframe="1M"))
        assert not ok

    def test_breakdown_toggle(self):
        prefs = NotificationPreferences()
        prefs.breakdown = False
        ok, _ = prefs.allows(_event(setup_type="BREAKDOWN", direction="BEARISH"))
        assert not ok


# ── §13-§24 Templates ────────────────────────────────────────────────
class TestTemplates:
    def test_5m_confirmed_header(self):
        text = render_event_message(_event())
        assert text.startswith("🟢 NIFTY 5M BREAKOUT CONFIRMED")
        assert "LONG" in text
        assert "24,700" in text  # trigger
        assert "sig_123" in text

    def test_1m_visually_distinct(self):
        text = render_event_message(_event(
            event_type="SIGNAL_TRIGGERED", candle_timeframe="1M",
            status="TRIGGERED", signal_id="sig_456", ai_status="PENDING",
            risk_status=None, entry_low=None, entry_high=None,
            stop_loss=None, target_low=None, target_high=None,
        ))
        assert text.startswith("⚡ NIFTY 1M BREAKOUT")
        assert "sig_456" in text
        assert "TRIGGERED" in text
        assert "PENDING" in text

    def test_timeframe_never_mislabeled(self):
        """§13 — timeframe comes only from candle_timeframe."""
        ev1 = _event(candle_timeframe="1M")
        ev5 = _event(candle_timeframe="5M")
        assert "1M" in render_event_message(ev1)
        assert "5M" in render_event_message(ev5)
        assert "5M" not in render_event_message(ev1).split("\n")[0]
        assert "1M" not in render_event_message(ev5).split("\n")[0]

    def test_breakdown_message(self):
        text = render_event_message(_event(
            instrument="BANKNIFTY", setup_type="BREAKDOWN",
            direction="BEARISH", signal_id="sig_789",
        ))
        assert "🔴 BANKNIFTY 5M BREAKDOWN CONFIRMED" in text
        assert "SHORT" in text

    def test_missing_levels_omitted(self):
        """§15 — entry/stop/target only when present; never invented."""
        text = render_event_message(_event(
            entry_low=None, entry_high=None, stop_loss=None,
            target_low=None, target_high=None,
        ))
        assert "Entry:" not in text
        assert "Stop:" not in text
        assert "Target:" not in text

    def test_result_target_hit(self):
        text = render_event_message(_event(
            event_type="SIGNAL_RESULT", result="TARGET_HIT",
            theoretical_entry=24705.0, exit_price=24750.0,
            theoretical_pnl_points=45.0, holding_time="8m 14s",
            status=None,
        ))
        assert "✅ SIGNAL RESULT" in text
        assert "TARGET HIT" in text or "TARGET_HIT" in text
        assert "+45" in text
        assert "8m 14s" in text

    def test_result_stop_hit(self):
        text = render_event_message(_event(
            event_type="SIGNAL_RESULT", result="STOP_HIT",
            theoretical_pnl_points=-25.0, status=None,
        ))
        assert "❌ SIGNAL RESULT" in text
        assert "-25" in text

    def test_result_ambiguous(self):
        text = render_event_message(_event(
            event_type="SIGNAL_RESULT", result="AMBIGUOUS",
            result_reason="Intrabar event ordering could not be established reliably.",
            status=None,
        ))
        assert "AMBIGUOUS OUTCOME" in text
        assert "No win/loss classification assigned." in text

    def test_theoretical_vs_actual_pnl_separate(self):
        """§24 — two distinct labelled lines, never one number."""
        text = render_event_message(_event(
            event_type="SIGNAL_RESULT", result="TARGET_HIT",
            theoretical_pnl_amount=1250.0, actual_pnl_amount=830.0, status=None,
        ))
        assert "Signal P&L:\n+₹1,250" in text
        assert "Actual Trade P&L:\n+₹830" in text

    def test_possible_setup_informational(self):
        text = format_possible_setup(_event(
            event_type="POSSIBLE_SETUP", status="POSSIBLE",
            breakout_pressure=82, false_breakout_risk=18,
        ))
        assert "🟡" in text
        assert "DEVELOPING" in text
        assert "WAITING FOR TRIGGER" in text

    def test_execution_template(self):
        ev = _event(event_type="EXECUTED", requested_qty=100, filled_qty=100,
                    average_fill_price=24705.0, broker_order_id="ORD_123", status=None)
        text = render_event_message(ev)
        assert "✅ ORDER EXECUTED" in text
        assert "ORD_123" in text

    def test_partial_fill_template(self):
        ev = _event(event_type="PARTIALLY_FILLED", requested_qty=100, filled_qty=40,
                    remaining_qty=60, average_fill_price=24705.0,
                    remaining_action="CANCEL / REVALIDATE", status=None)
        text = render_event_message(ev)
        assert "⚠ PARTIAL FILL" in text
        assert "PARTIALLY_FILLED" in text
        assert "CANCEL / REVALIDATE" in text

    def test_test_message_labeled(self):
        """§38 — tests are explicitly labeled."""
        text = format_test_message("live")
        assert "TEST MESSAGE" in text
        assert "LIVE" in text
        assert "not a trading signal" in text.lower()


# ── §25 Rate limiter ─────────────────────────────────────────────────
class TestRateLimiter:
    def test_acquire_respects_tokens(self):
        from app.institutional.telegram import TelegramRateLimiter
        rl = TelegramRateLimiter(global_per_second=100.0, per_chat_per_second=100.0, burst=2)

        async def run():
            a = await rl.acquire("c1", timeout=1.0)
            b = await rl.acquire("c1", timeout=1.0)
            # burst exhausted → next acquire within window fails
            c = await rl.acquire("c1", timeout=0.05)
            return a, b, c

        a, b, c = asyncio.run(run())
        assert a and b and not c

    def test_all_sends_via_central_limiter(self):
        """§25 — the notification worker sends only via telegram_outbound_queue."""
        import inspect
        src = inspect.getsource(telegram_notification_queue._process)
        assert "telegram_outbound_queue.enqueue" in src
        assert "requests.post" not in src


# ── §10/§11/§32/§33/§35/§41 End-to-end ───────────────────────────────
class TestEndToEnd:
    @staticmethod
    def _link_user(user_id="user_e2e", chat_id="555001"):
        from app.institutional import telegram as tg
        tg.telegram_link_manager._bindings[user_id] = {
            "telegram_chat_id": chat_id, "linked_at": time.time(),
            "status": "ACTIVE", "permissions": ["read"],
        }
        tg.telegram_link_manager._by_chat[chat_id] = user_id
        return chat_id

    def test_signal_event_to_sent(self):
        """§41: signal event → queue → worker → rate limiter → SENT."""
        from app.institutional import telegram as tg

        self._link_user()
        sent: list = []

        async def fake_send(self, msg):
            sent.append(msg)

        async def run():
            orig = tg.TelegramOutboundQueue._send_via_httpx
            tg.TelegramOutboundQueue._send_via_httpx = fake_send
            try:
                await telegram_outbound_queue.start()
                await telegram_notification_queue.start()
                ids = await telegram_notification_queue.publish_signal_event(_event())
                assert len(ids) == 1
                for _ in range(100):
                    if telegram_notification_queue.stats()["statuses"].get("SENT"):
                        break
                    await asyncio.sleep(0.05)
                await telegram_notification_queue.stop()
                await telegram_outbound_queue.stop()
            finally:
                tg.TelegramOutboundQueue._send_via_httpx = orig

        asyncio.run(run())
        assert telegram_notification_queue.stats()["statuses"].get("SENT") == 1
        assert len(sent) == 1
        assert "NIFTY 5M BREAKOUT CONFIRMED" in sent[0].text
        # §39 audit record fields
        audit = telegram_notification_queue.audit_for_user("user_e2e")
        assert audit and audit[0].delivery_status == "SENT"
        assert audit[0].sent_at_utc is not None
        assert audit[0].signal_id == "sig_123"
        assert audit[0].notification_id is not None

    def test_notification_dedup_same_signal_event(self):
        """§33 — same signal_id + event_type + user_id delivered once."""
        self._link_user("user_dup", "555002")

        async def run():
            ids1 = await telegram_notification_queue.publish_signal_event(_event())
            ids2 = await telegram_notification_queue.publish_signal_event(_event())
            return ids1, ids2

        ids1, ids2 = asyncio.run(run())
        assert len(ids1) == 1
        assert ids2 == []  # duplicate suppressed

    def test_preferences_skip_records_audit(self):
        self._link_user("user_skip", "555003")
        from app.institutional.telegram_notifications import notification_policy
        prefs = notification_policy.get("user_skip")
        prefs.events["SIGNAL_CONFIRMED"] = False

        async def run():
            return await telegram_notification_queue.publish_signal_event(_event())

        ids = asyncio.run(run())
        assert ids == []
        audit = telegram_notification_queue.audit_for_user("user_skip")
        assert audit and audit[0].delivery_status == "SKIPPED"

    def test_publish_never_raises(self):
        """§35 — Telegram failure must not propagate to the Signal Engine."""
        from app.institutional import telegram as tg
        orig = tg.telegram_link_manager.all_bindings

        def boom():
            raise RuntimeError("boom")

        tg.telegram_link_manager.all_bindings = boom
        try:
            async def run():
                return await telegram_notification_queue.publish_signal_event(_event())
            ids = asyncio.run(run())
        finally:
            tg.telegram_link_manager.all_bindings = orig
        assert ids == []  # swallowed, not raised

    def test_unlinked_user_gets_nothing(self):
        async def run():
            return await telegram_notification_queue.publish_signal_event(_event())

        assert asyncio.run(run()) == []


# ── §3/§6/§29/§30 API endpoints ──────────────────────────────────────
def settings_token_not_leaked(raw: str) -> bool:
    """§29 — the configured bot token value must never appear in API responses."""
    from app.core.config import settings as s
    tok = getattr(s, "telegram_bot_token", "")
    return not tok or tok not in raw


class TestTelegramAPI:
    def test_status_endpoint(self, client):
        r = client.get("/api/v1/telegram/status")
        assert r.status_code == 200
        body = r.json()
        assert "bot_configured" in body
        assert "binding" in body
        assert settings_token_not_leaked(r.text)

    def test_webhook_rejects_without_secret(self, client):
        """§6 — no secret configured (or wrong header) → HTTP 403, unprocessed."""
        r = client.post("/api/v1/telegram/webhook", json={"update_id": 1})
        assert r.status_code == 403

    def test_webhook_rejects_wrong_secret(self, client, monkeypatch):
        from app.core.config import settings as s
        monkeypatch.setattr(s, "telegram_webhook_secret", "topsecret")
        r = client.post(
            "/api/v1/telegram/webhook",
            json={"update_id": 2},
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
        )
        assert r.status_code == 403
        r2 = client.post(
            "/api/v1/telegram/webhook",
            json={"update_id": 3},
            headers={"X-Telegram-Bot-Api-Secret-Token": "topsecret"},
        )
        assert r2.status_code == 200

    def test_test_message_requires_link(self, client):
        r = client.post("/api/v1/telegram/test")
        assert r.status_code == 400  # not linked

    def test_preferences_roundtrip(self, client):
        r = client.get("/api/v1/telegram/preferences")
        assert r.status_code == 200
        prefs = r.json()
        assert prefs["events"]["SIGNAL_CONFIRMED"] is True
        prefs["events"]["SIGNAL_CONFIRMED"] = False
        r2 = client.put("/api/v1/telegram/preferences", json=prefs)
        assert r2.status_code == 200
        assert r2.json()["events"]["SIGNAL_CONFIRMED"] is False
        # restore
        prefs["events"]["SIGNAL_CONFIRMED"] = True
        client.put("/api/v1/telegram/preferences", json=prefs)

    def test_commands_endpoint(self, client):
        r = client.get("/api/v1/telegram/commands")
        assert r.status_code == 200
        assert "/start" in r.json()["commands"]

    def test_audit_endpoint(self, client):
        r = client.get("/api/v1/telegram/audit")
        assert r.status_code == 200
        assert "records" in r.json()
