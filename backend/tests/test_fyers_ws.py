"""FYERS HSM v1-5 data-socket tests.

Covers the pure wire helpers (message builders, JWT decode, frame parsers,
value scaling) against the byte layouts verified with live frames, plus a
fake-socket end-to-end pass through ``FyersHsmSocket._apply_records``.
"""
from __future__ import annotations

import base64
import json
import struct

import pytest

from app.providers.fyers_ws import (
    CHANNEL,
    INDEX_FIELDS,
    ReauthRequired,
    build_ack_message,
    build_auth_message,
    build_mode_message,
    build_ping_message,
    build_subscribe_message,
    decode_index_values,
    hsm_key_and_expiry,
    jwt_payload,
    parse_control_frame,
    parse_datafeed_frame,
)


def _jwt(payload: dict) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{header}.{body}.signature"


class TestJwt:
    def test_payload_roundtrip_with_appid_prefix(self):
        token = "APP-100:" + _jwt({"hsm_key": "abc123", "exp": 9999999999})
        assert jwt_payload(token)["hsm_key"] == "abc123"
        key, exp = hsm_key_and_expiry(token)
        assert key == "abc123" and exp == 9999999999

    def test_non_jwt_token_requires_reauth(self):
        with pytest.raises(ReauthRequired):
            hsm_key_and_expiry("not-a-jwt")

    def test_missing_hsm_key_requires_reauth(self):
        with pytest.raises(ReauthRequired):
            hsm_key_and_expiry(_jwt({"exp": 9999999999}))


class TestMessageBuilders:
    def test_auth_message_layout(self):
        key = "k" * 40
        msg = build_auth_message(key)
        total = 18 + len(key) + len("PythonSDK-3.0.9")
        assert struct.unpack("!H", msg[:2])[0] == total - 2
        assert msg[2] == 1 and msg[3] == 4
        assert msg[4] == 1
        assert struct.unpack("!H", msg[5:7])[0] == len(key)
        assert msg[7 : 7 + len(key)].decode() == key

    def test_mode_message_is_full_mode_channel(self):
        msg = build_mode_message(full=True)
        assert msg[0:2] == b"\x00\x00"
        assert msg[2] == 12 and msg[3] == 2
        assert struct.unpack(">Q", msg[7:15])[0] == 1 << CHANNEL
        assert msg[-1] == 70

    def test_subscribe_message_scrip_encoding(self):
        topics = ["if|nse_cm|Nifty 50", "if|bse_cm|SENSEX"]
        msg = build_subscribe_message(topics, access_token="tok")
        assert msg[2] == 4 and msg[3] == 2
        scrips_len = struct.unpack(">H", msg[5:7])[0]
        scrips = msg[7 : 7 + scrips_len]
        assert struct.unpack(">H", scrips[:2])[0] == 2
        offset = 2
        decoded = []
        for _ in range(2):
            n = scrips[offset]
            offset += 1
            decoded.append(scrips[offset : offset + n].decode())
            offset += n
        assert decoded == topics

    def test_ack_and_ping(self):
        ack = build_ack_message(0x01020304)
        assert struct.unpack(">H", ack[:2])[0] == 9
        assert ack[2] == 3 and ack[3] == 1
        assert struct.unpack(">I", ack[-4:])[0] == 0x01020304
        assert build_ping_message() == bytes([0, 1, 11])


class TestControlFrames:
    def test_auth_ok_frame_with_schema_blob(self):
        # [len][type=1][fieldcount=3][1:len1:"K"][2:len2:0x0002][3:lenN:json]
        schema = json.dumps({"version": "1.0.0"}).encode()
        body = bytearray()
        body += bytes([1]) + struct.pack("!H", 1) + b"K"
        body += bytes([2]) + struct.pack("!H", 2) + struct.pack("!H", 2)
        body += bytes([3]) + struct.pack("!H", len(schema)) + schema
        frame = bytes(struct.pack(">H", 4 + len(body)) + bytes([1, 3]) + body)
        parsed = parse_control_frame(frame)
        assert parsed["ok"] is True
        assert parsed["ack_interval"] == 2

    def test_subscribe_ack_frame(self):
        frame = bytes.fromhex("000604010100014b")
        parsed = parse_control_frame(frame)
        assert parsed["type"] == 4 and parsed["ok"] is True

    def test_error_status_is_not_ok(self):
        body = bytes([1]) + struct.pack("!H", 1) + b"N"
        frame = bytes(struct.pack(">H", 4 + len(body)) + bytes([1, 1]) + body)
        assert parse_control_frame(frame)["ok"] is False


def _snapshot_frame(topic: str, topic_id: int, values: list[int], *, precision=2, multiplier=1) -> bytes:
    body = bytearray()
    body += bytes([83])
    body += struct.pack("H", topic_id)
    encoded = topic.encode()
    body += bytes([len(encoded)]) + encoded
    body += bytes([len(values)])
    for value in values:
        body += struct.pack(">i", value)
    body += b"\x00\x00"
    body += struct.pack(">H", multiplier)
    body += bytes([precision])
    for text in ("nse_cm", topic.split("|")[-1], topic.split("|")[-1]):
        raw = text.encode()
        body += bytes([len(raw)]) + raw
    return bytes(struct.pack(">H", 9 + len(body)) + bytes([6]) + struct.pack(">I", 1) + struct.pack("!H", 1) + body)


def _update_frame(topic_id: int, values: list[int], message_number: int = 2) -> bytes:
    body = bytearray()
    body += bytes([85])
    body += struct.pack("H", topic_id)
    body += bytes([len(values)])
    for value in values:
        body += struct.pack(">i", value)
    return bytes(
        struct.pack(">H", 9 + len(body)) + bytes([6]) + struct.pack(">I", message_number) + struct.pack("!H", 1) + body
    )


class TestDatafeedFrames:
    def test_snapshot_roundtrip(self):
        frame = _snapshot_frame("if|nse_cm|Nifty 50", 2, [2334640, 2327060, 1789727407, 2338915, 2328660, 2333470])
        message_number, records = parse_datafeed_frame(frame)
        assert message_number == 1 and len(records) == 1
        record = records[0]
        assert record["kind"] == "snapshot"
        assert record["topic"] == "if|nse_cm|Nifty 50"
        assert record["precision"] == 2 and record["multiplier"] == 1
        quote = decode_index_values(record["values"], record["precision"], record["multiplier"])
        assert quote["ltp"] == 23346.4
        assert quote["previous_close"] == 23270.6
        assert quote["exch_feed_time"] == 1789727407  # timestamp never scaled
        assert quote["high"] == 23389.15 and quote["low"] == 23286.6 and quote["open"] == 23334.7

    def test_update_frame_carries_no_topic_name(self):
        frame = _update_frame(2, [2335000, 2327060, 1789727500, 2339000, 2328660, 2333470])
        message_number, records = parse_datafeed_frame(frame)
        assert message_number == 2
        assert records[0]["kind"] == "update" and records[0]["topic"] is None
        assert records[0]["multiplier"] is None

    def test_missing_values_sentinel_is_skipped(self):
        quote = decode_index_values([-2147483648, 100, -2147483648, 200, 300, 400], 0, 1)
        assert "ltp" not in quote
        assert quote["previous_close"] == 100

    def test_index_fields_cover_full_layout(self):
        assert INDEX_FIELDS[0] == "ltp" and INDEX_FIELDS[2] == "exch_feed_time"
        assert len(INDEX_FIELDS) >= 6


class _FakeSocket:
    """Minimal stand-in that exposes only what _apply_records touches."""

    def __init__(self):
        from app.providers.fyers_ws import FyersHsmSocket

        self.sock = FyersHsmSocket.__new__(FyersHsmSocket)
        self.sock._url = "wss://unused"
        self.sock._token_provider = None
        self.sock._symbol_map = {"NIFTY 50": "NSE:NIFTY50-INDEX"}
        self.sock._on_quote = self._capture
        self.sock._channel = CHANNEL
        self.sock._task = None
        self.sock._stopped = False
        self.sock._connected = False
        self.sock._authed = False
        self.sock._backoff = 1.0
        self.sock._topic_by_symbol = {"NIFTY 50": "if|nse_cm|Nifty 50"}
        self.sock._symbol_by_topic = {"if|nse_cm|Nifty 50": "NIFTY 50"}
        self.sock._topic_id_symbol = {}
        self.sock._topic_state = {}
        self.sock._index_hsm = None
        self.sock.stats = {"ticks": 0, "last_tick_at": None}
        self.quotes: list[tuple[str, dict]] = []

    async def _capture(self, symbol, quote):
        self.quotes.append((symbol, quote))


class TestApplyRecords:
    @pytest.mark.asyncio
    async def test_snapshot_then_update_emits_scaled_quotes(self):
        fake = _FakeSocket()
        _, snap = parse_datafeed_frame(
            _snapshot_frame("if|nse_cm|Nifty 50", 2, [2334640, 2327060, 1789727407, 2338915, 2328660, 2333470])
        )
        await fake.sock._apply_records(snap)
        _, upd = parse_datafeed_frame(_update_frame(2, [2335000, 2327060, 1789727500, 2339000, 2328660, 2333470]))
        await fake.sock._apply_records(upd)
        assert len(fake.quotes) == 2
        symbol, quote = fake.quotes[-1]
        assert symbol == "NIFTY 50"
        assert quote["ltp"] == 23350.0
        assert quote["source"] == "ws"

    @pytest.mark.asyncio
    async def test_update_before_snapshot_is_dropped(self):
        fake = _FakeSocket()
        _, upd = parse_datafeed_frame(_update_frame(2, [2335000, 2327060, 1789727500, 2339000, 2328660, 2333470]))
        await fake.sock._apply_records(upd)
        assert fake.quotes == []

    @pytest.mark.asyncio
    async def test_unknown_topic_id_is_dropped(self):
        fake = _FakeSocket()
        _, upd = parse_datafeed_frame(_update_frame(99, [1, 2, 3, 4, 5, 6]))
        await fake.sock._apply_records(upd)
        assert fake.quotes == []
