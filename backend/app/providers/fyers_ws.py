"""FYERS HSM v1-5 market-data socket client — tick-by-tick index feed.

Primary market-data source for the backend (the 1 Hz REST quote poller in
``app.providers.fyers`` remains as fallback/health probe). The socket delivers
sub-second ticks for subscriptions instead of a batch snapshot per poll:

  * wire protocol: binary frames over ``wss://socket.fyers.in/hsm/v1-5/prod``
    (same protocol the official ``fyers-apiv3`` SDK speaks; field-by-field
    verified against live frames)
  * auth: the FYERS access token is a JWT whose payload carries ``hsm_key``
    and ``exp`` — no separate handshake credential
  * topic resolution: ``POST /data/symbol-token`` maps exchange symbols to
    fytokens; index topics become ``if|<segment>|<index_name>``
  * snapshot (type ``53``/``'S'``) records seed per-topic state; update frames
    (``55``/``'U'`` — full mode) carry only changed int fields
  * liveness: application ping ``bytes([0, 1, 11])`` every 10 s and an ack
    every ``ack_interval`` data frames (interval from the auth response)

The client is fail-closed: it never fabricates a quote, it reconnects with
jittered exponential backoff, and an expired/missing token parks the loop
(no broker hammering) until the caller's token provider yields a fresh one.
"""
from __future__ import annotations

import asyncio
import base64
import json
import random
import struct
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

SYMBOL_TOKEN_URL = "https://api-t1.fyers.in/data/symbol-token"
INDEX_HSM_MAPPING_URL = "https://public.fyers.in/sym_details/index_hsm_mapping.json"

#: Mimicked SDK source string — the server logs/expects a client identity.
SOURCE = "PythonSDK-3.0.9"
CHANNEL = 11

#: Exchange-segment prefix (first 4 chars of a fytoken) -> HSM segment name.
EXCH_SEG: dict[str, str] = {
    "1010": "nse_cm",
    "1011": "nse_fo",
    "1012": "cde_fo",
    "1020": "nse_com",
    "1120": "mcx_fo",
    "1210": "bse_cm",
    "1211": "bse_fo",
    "1212": "bcs_fo",
}

#: Offline fallback for the public index HSM mapping (symbol -> index name).
#: The live mapping is fetched once per process and merged over this table.
INDEX_HSM_FALLBACK: dict[str, str] = {
    "NSE:NIFTY50-INDEX": "Nifty 50",
    "NSE:NIFTYBANK-INDEX": "Nifty Bank",
    "NSE:FINNIFTY-INDEX": "Nifty Fin Service",
    "BSE:SENSEX-INDEX": "SENSEX",
    "NSE:INDIAVIX-INDEX": "India VIX",
    "NSE:NIFTYIT-INDEX": "Nifty IT",
    "NSE:NIFTYNXT50-INDEX": "Nifty Next 50",
    "NSE:NIFTYMIDCAP150-INDEX": "NIFTY MIDCAP 150",
    "NSE:NIFTYPVTBANK-INDEX": "Nifty Pvt Bank",
    "NSE:NIFTYSMLCAP250-INDEX": "NIFTY SMLCAP 250",
}

#: Index int-field order in full-mode frames (old SDK layout = new schema's
#: i102..i107 for the first six). Position 2 is a feed timestamp, never scaled.
INDEX_FIELDS: tuple[str, ...] = (
    "ltp",
    "previous_close",
    "exch_feed_time",
    "high",
    "low",
    "open",
    "yearly_high",
    "yearly_low",
)
#: Positions that carry prices (scaled by 10**precision * multiplier).
_INDEX_PRICE_POSITIONS = (0, 1, 3, 4, 5, 6, 7)

#: Re-connect backoff bounds (seconds).
BACKOFF_INITIAL = 1.0
BACKOFF_MAX = 60.0
#: Park interval when the broker token is expired/missing (re-auth required).
AUTH_PARK_SECONDS = 30.0
#: App-level ping cadence (protocol requires the custom binary ping).
PING_SECONDS = 10.0
#: Consider the socket dead when no frame arrived for this long while the
#: market is open (transport half-open protection).
IDLE_FRAME_TIMEOUT_S = 45.0


class ReauthRequired(RuntimeError):
    """Raised when the stored token is missing/expired — park, never retry-hammer."""


def jwt_payload(access_token: str) -> dict[str, Any]:
    """Decode the (unverified) JWT payload carrying ``hsm_key`` and ``exp``."""
    raw = access_token.split(":")[-1].strip()
    parts = raw.split(".")
    if len(parts) < 2:
        raise ReauthRequired("FYERS token is not a JWT — re-auth required")
    payload_b64 = parts[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception as exc:
        raise ReauthRequired(f"FYERS token payload undecodable: {exc}") from exc


def hsm_key_and_expiry(access_token: str) -> tuple[str, float]:
    """Return ``(hsm_key, exp_epoch)`` or raise :class:`ReauthRequired`."""
    payload = jwt_payload(access_token)
    key = payload.get("hsm_key")
    exp = payload.get("exp")
    if not key or not isinstance(exp, (int, float)):
        raise ReauthRequired("FYERS token carries no hsm_key/exp — re-auth required")
    return str(key), float(exp)


def build_auth_message(hsm_key: str) -> bytes:
    """ReqType 1 — handshake with the decoded ``hsm_key`` (SDK byte layout)."""
    size = 18 + len(hsm_key) + len(SOURCE)
    buf = bytearray()
    buf += struct.pack("!H", size - 2)
    buf.append(1)
    buf.append(4)
    buf.append(1)
    buf += struct.pack("!H", len(hsm_key))
    buf += hsm_key.encode()
    buf.append(2)
    buf += struct.pack("!H", 1)
    buf += b"P"
    buf.append(3)
    buf += struct.pack("!H", 1)
    buf += bytes([1])
    buf.append(4)
    buf += struct.pack("!H", len(SOURCE))
    buf += SOURCE.encode()
    return bytes(buf)


def build_mode_message(*, full: bool = True, channel: int = CHANNEL) -> bytes:
    """ReqType 12 — select full (70) or lite (76) payload mode on ``channel``."""
    buf = bytearray()
    buf += struct.pack(">H", 0)
    buf.append(12)
    buf.append(2)
    buf.append(1)
    buf += struct.pack(">H", 8)
    buf += struct.pack(">Q", 1 << channel)
    buf.append(2)
    buf += struct.pack(">H", 1)
    buf.append(70 if full else 76)
    return bytes(buf)


def build_subscribe_message(
    topics: list[str], *, access_token: str = "", channel: int = CHANNEL
) -> bytes:
    """ReqType 4 — subscribe to HSM topics (SDK's declared-length quirk kept)."""
    scrips = bytearray()
    scrips.append(len(topics) >> 8 & 0xFF)
    scrips.append(len(topics) & 0xFF)
    for topic in topics:
        encoded = str(topic).encode("ascii")
        scrips.append(len(encoded))
        scrips += encoded
    data_len = 18 + len(scrips) + len(access_token) + len(SOURCE)
    buf = bytearray()
    buf += struct.pack(">H", data_len)
    buf.append(4)
    buf.append(2)
    buf.append(1)
    buf += struct.pack(">H", len(scrips))
    buf += scrips
    buf.append(2)
    buf += struct.pack(">H", 1)
    buf.append(channel)
    return bytes(buf)


def build_unsubscribe_message(
    topics: list[str], *, access_token: str = "", channel: int = CHANNEL
) -> bytes:
    """ReqType 5 — drop subscriptions (same layout family as subscribe)."""
    scrips = bytearray()
    scrips.append(len(topics) >> 8 & 0xFF)
    scrips.append(len(topics) & 0xFF)
    for topic in topics:
        encoded = str(topic).encode("ascii")
        scrips.append(len(encoded))
        scrips += encoded
    data_len = 18 + len(scrips) + len(access_token) + len(SOURCE)
    buf = bytearray()
    buf += struct.pack(">H", data_len)
    buf.append(5)
    buf.append(2)
    buf.append(1)
    buf += struct.pack(">H", len(scrips))
    buf += scrips
    buf.append(2)
    buf += struct.pack(">H", 1)
    buf.append(channel)
    return bytes(buf)


def build_ack_message(message_number: int) -> bytes:
    """ReqType 3 — acknowledge the last data frame (flow control)."""
    buf = bytearray()
    buf += struct.pack(">H", 9)
    buf.append(3)
    buf.append(1)
    buf.append(1)
    buf += struct.pack(">H", 4)
    buf += struct.pack(">I", message_number)
    return bytes(buf)


def build_ping_message() -> bytes:
    """Application-level keepalive (the server does not require WS pings)."""
    return bytes([0, 1, 11])


def parse_frame_fields(data: bytes) -> dict[int, bytes]:
    """Parse ``[len:2][type:1][field_count:1][id:1,len:2,value]*`` control frames."""
    if len(data) < 4:
        return {}
    count = data[3]
    offset = 4
    fields: dict[int, bytes] = {}
    for _ in range(count):
        if offset + 3 > len(data):
            break
        field_id = data[offset]
        field_len = struct.unpack("!H", data[offset + 1 : offset + 3])[0]
        offset += 3
        fields[field_id] = bytes(data[offset : offset + field_len])
        offset += field_len
    return fields


def parse_control_frame(data: bytes) -> dict[str, Any]:
    """Parse a control frame (types 1/4/5/12) into ``{ok, ack_interval, error}``."""
    frame_type = data[2] if len(data) > 2 else -1
    fields = parse_frame_fields(data)
    status = fields.get(1, b"").decode("utf-8", "ignore")
    ack_interval = 0
    raw_ack = fields.get(2, b"")
    if len(raw_ack) >= 2:
        ack_interval = struct.unpack("!H", raw_ack[:2])[0]
    return {
        "type": frame_type,
        "ok": status == "K",
        "status": status,
        "ack_interval": ack_interval,
    }


def parse_datafeed_frame(data: bytes) -> tuple[int, list[dict[str, Any]]]:
    """Parse a type-6 data frame.

    Returns ``(message_number, records)`` where each record is
    ``{kind, topic, topic_id, fields, multiplier, precision, values}``.
    ``kind`` is ``"snapshot"`` (83) or ``"update"`` (85).
    """
    if len(data) < 9:
        return 0, []
    message_number = struct.unpack(">I", data[3:7])[0]
    scrip_count = struct.unpack("!H", data[7:9])[0]
    offset = 9
    records: list[dict[str, Any]] = []
    for _ in range(scrip_count):
        if offset >= len(data):
            break
        data_type = data[offset]
        offset += 1
        if offset + 2 > len(data):
            break
        topic_id = struct.unpack("H", data[offset : offset + 2])[0]
        offset += 2
        if data_type not in (83, 85):
            # Unknown scrip encoding — cannot skip safely, stop this frame.
            logger.debug("fyers_ws_unknown_scrip_type", data_type=data_type)
            break
        topic: str | None = None
        if data_type == 83:
            if offset >= len(data):
                break
            topic_len = data[offset]
            offset += 1
            topic = bytes(data[offset : offset + topic_len]).decode("utf-8", "ignore")
            offset += topic_len
        if offset >= len(data):
            break
        field_count = data[offset]
        offset += 1
        values: list[int] = []
        for _ in range(field_count):
            if offset + 4 > len(data):
                break
            values.append(struct.unpack(">i", data[offset : offset + 4])[0])
            offset += 4
        record: dict[str, Any] = {
            "kind": "snapshot" if data_type == 83 else "update",
            "topic": topic,
            "topic_id": topic_id,
            "values": values,
            "multiplier": None,
            "precision": None,
        }
        if data_type == 83:
            # Snapshot trailer: 2 reserved bytes, multiplier (2), precision (1),
            # then exchange / exchange_token / symbol strings.
            offset += 2
            if offset + 2 <= len(data):
                record["multiplier"] = struct.unpack(">H", data[offset : offset + 2])[0]
                offset += 2
            if offset < len(data):
                record["precision"] = data[offset]
                offset += 1
            meta: list[str] = []
            for _ in range(3):
                if offset >= len(data):
                    break
                str_len = data[offset]
                offset += 1
                meta.append(bytes(data[offset : offset + str_len]).decode("utf-8", "ignore"))
                offset += str_len
            record["exchange"] = meta[0] if len(meta) > 0 else ""
            record["exchange_token"] = meta[1] if len(meta) > 1 else ""
            record["symbol"] = meta[2] if len(meta) > 2 else ""
        records.append(record)
    return message_number, records


def decode_index_values(
    values: list[int], precision: int | None, multiplier: int | None
) -> dict[str, Any]:
    """Map positional index fields to scaled quote values (snake_case keys)."""
    scale = float((10 ** (precision or 0)) * (multiplier or 1))
    quote: dict[str, Any] = {}
    for position, raw in enumerate(values):
        if position >= len(INDEX_FIELDS):
            break
        if raw == -2147483648:
            continue
        name = INDEX_FIELDS[position]
        if position in _INDEX_PRICE_POSITIONS and scale > 0:
            quote[name] = round(raw / scale, 4)
        else:
            quote[name] = raw
    return quote


class FyersHsmSocket:
    """Reconnecting FYERS HSM data socket.

    ``on_quote`` is awaited for every decoded index quote:
    ``await on_quote(app_symbol, {"ltp": float, "previous_close": float, ...})``.
    ``token_provider`` supplies the current access token on every connect so a
    re-auth is picked up without restarting the provider.
    """

    def __init__(
        self,
        *,
        url: str,
        token_provider: Callable[[], Awaitable[str]],
        symbol_map: dict[str, str],
        on_quote: Callable[[str, dict[str, Any]], Awaitable[None]],
        channel: int = CHANNEL,
    ) -> None:
        self._url = url
        self._token_provider = token_provider
        self._symbol_map = dict(symbol_map)
        self._on_quote = on_quote
        self._channel = channel

        self._task: asyncio.Task | None = None
        self._stopped = False
        self._connected = False
        self._authed = False
        self._backoff = BACKOFF_INITIAL
        self._topic_by_symbol: dict[str, str] = {}
        self._symbol_by_topic: dict[str, str] = {}
        self._topic_id_symbol: dict[int, str] = {}
        self._topic_state: dict[str, dict[str, Any]] = {}
        self._index_hsm: dict[str, str] | None = None

        self.stats: dict[str, Any] = {
            "connected": False,
            "authed": False,
            "reconnects": 0,
            "frames": 0,
            "ticks": 0,
            "connect_errors": 0,
            "last_error": None,
            "last_frame_at": None,
            "last_tick_at": None,
            "connected_since": None,
            "subscriptions": [],
            "mode": "ws_primary",
        }

    # ── lifecycle ────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stopped = False
        self._task = asyncio.create_task(self._run_forever(), name="fyers-hsm-socket")

    async def stop(self) -> None:
        self._stopped = True
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001 - stop is best-effort
            pass
        self._connected = self._authed = False
        self.stats["connected"] = self.stats["authed"] = False

    def is_healthy(self) -> bool:
        """Transport connected and authenticated (tick flow is market-gated)."""
        return self._connected and self._authed

    def is_ready(self) -> bool:
        return self._task is not None and not self._task.done()

    # ── reconnect loop ───────────────────────────────────────────────────

    async def _run_forever(self) -> None:
        while not self._stopped:
            try:
                await self._run_once()
            except asyncio.CancelledError:
                raise
            except ReauthRequired as exc:
                self._mark_disconnected(str(exc))
                logger.warning("fyers_ws_reauth_parked", error=str(exc)[:200], park_s=AUTH_PARK_SECONDS)
                await asyncio.sleep(AUTH_PARK_SECONDS)
                continue
            except Exception as exc:  # noqa: BLE001 - any connect/protocol fault retries
                self._mark_disconnected(str(exc))
                logger.warning("fyers_ws_cycle_failed", error=str(exc)[:200])
            if self._stopped:
                break
            delay = min(BACKOFF_MAX, self._backoff)
            delay *= 0.8 + random.random() * 0.4
            self._backoff = min(BACKOFF_MAX, self._backoff * 2)
            self.stats["reconnects"] += 1
            await asyncio.sleep(delay)

    async def _run_once(self) -> None:
        from websockets.asyncio.client import connect
        from websockets.exceptions import ConnectionClosed

        token = await self._token_provider()
        if not token:
            raise ReauthRequired("no FYERS access token available")
        hsm_key, exp = hsm_key_and_expiry(token)
        if exp - time.time() <= 0:
            raise ReauthRequired("FYERS access token expired — re-auth required")

        topics = await self._resolve_topics(token)
        if not topics:
            raise RuntimeError("no subscribable FYERS topics resolved")
        topic_list = list(topics.values())

        async with connect(
            self._url,
            max_size=None,
            ping_interval=None,
            open_timeout=15,
            close_timeout=5,
        ) as ws:
            self._connected = True
            self.stats.update(
                connected=True,
                connected_since=datetime.now(timezone.utc).isoformat(),
                subscriptions=sorted(topic_list),
            )
            await ws.send(build_auth_message(hsm_key))
            await ws.send(build_mode_message(full=True, channel=self._channel))
            await ws.send(
                build_subscribe_message(topic_list, access_token=token, channel=self._channel)
            )

            ack_interval = 0
            update_count = 0
            last_frame = time.monotonic()
            ping_task = asyncio.create_task(self._ping_loop(ws))
            try:
                while not self._stopped:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=PING_SECONDS)
                    except TimeoutError:
                        if await self._idle_too_long(last_frame):
                            raise RuntimeError("no FYERS frames while market open — reconnect")
                        continue
                    except ConnectionClosed:
                        raise RuntimeError("FYERS socket closed")
                    data = bytes(raw)
                    last_frame = time.monotonic()
                    self.stats["frames"] += 1
                    self.stats["last_frame_at"] = datetime.now(timezone.utc).isoformat()
                    frame_type = data[2] if len(data) > 2 else -1
                    logger.debug("fyers_ws_frame", frame_type=frame_type, bytes=len(data))

                    if frame_type in (1, 4, 5, 12):
                        info = parse_control_frame(data)
                        if frame_type == 1:
                            if not info["ok"]:
                                raise ReauthRequired(
                                    f"FYERS socket auth rejected ({info['status'] or 'no status'})"
                                )
                            ack_interval = info["ack_interval"] or 1
                            self._authed = True
                            self.stats["authed"] = True
                            self._backoff = BACKOFF_INITIAL
                            logger.info(
                                "fyers_ws_authenticated",
                                ack_interval=ack_interval,
                                topics=len(topics),
                            )
                        elif not info["ok"]:
                            logger.warning(
                                "fyers_ws_control_rejected", frame_type=frame_type, status=info["status"]
                            )
                        continue

                    if frame_type == 6:
                        message_number, records = parse_datafeed_frame(data)
                        await self._apply_records(records)
                        if ack_interval:
                            update_count += 1
                            if update_count >= ack_interval:
                                await ws.send(build_ack_message(message_number))
                                update_count = 0
                        continue
            finally:
                ping_task.cancel()
                try:
                    await ping_task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
                self._mark_disconnected(None)

    async def _ping_loop(self, ws: Any) -> None:
        while True:
            await asyncio.sleep(PING_SECONDS)
            await ws.send(build_ping_message())

    async def _idle_too_long(self, last_frame: float) -> bool:
        """True only while the market is open — after hours silence is normal."""
        if time.monotonic() - last_frame < IDLE_FRAME_TIMEOUT_S:
            return False
        try:
            from app.services.calendar_service import calendar_service

            return bool(calendar_service.is_market_open_now())
        except Exception:  # noqa: BLE001 - calendar unavailable -> do not force reconnect
            return False

    def _mark_disconnected(self, error: str | None) -> None:
        self._connected = False
        self._authed = False
        self._topic_id_symbol.clear()
        self._topic_state.clear()
        self.stats.update(connected=False, authed=False)
        if error:
            self.stats["last_error"] = error[:300]
            self.stats["connect_errors"] += 1

    # ── topics ───────────────────────────────────────────────────────────

    async def _resolve_topics(self, token: str) -> dict[str, str]:
        """Resolve app symbols to HSM topics via the symbol-token API."""
        symbols = list(self._symbol_map.values())
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                SYMBOL_TOKEN_URL,
                json={"symbols": symbols},
                headers={"Authorization": token.split(":")[-1], "Content-Type": "application/json"},
            )
            data = resp.json()
        if data.get("s") != "ok":
            raise RuntimeError(f"symbol-token API failed: {str(data.get('message') or data)[:150]}")
        valid = data.get("validSymbol") or {}
        index_hsm = await self._index_hsm_mapping()

        topic_by_symbol: dict[str, str] = {}
        for app_symbol, fyers_symbol in self._symbol_map.items():
            fytoken = valid.get(fyers_symbol)
            if not fytoken:
                logger.warning("fyers_ws_symbol_unmapped", symbol=fyers_symbol)
                continue
            segment = EXCH_SEG.get(str(fytoken)[:4])
            if not segment:
                logger.warning("fyers_ws_segment_unknown", symbol=fyers_symbol, fytoken=fytoken)
                continue
            if str(fyers_symbol).upper().endswith("-INDEX"):
                index_name = index_hsm.get(fyers_symbol) or INDEX_HSM_FALLBACK.get(fyers_symbol)
                if not index_name:
                    logger.warning("fyers_ws_index_hsm_missing", symbol=fyers_symbol)
                    continue
                topic = f"if|{segment}|{index_name}"
            else:
                topic = f"sf|{segment}|{str(fytoken)[10:]}"
            topic_by_symbol[app_symbol] = topic

        self._topic_by_symbol = topic_by_symbol
        self._symbol_by_topic = {t: s for s, t in topic_by_symbol.items()}
        return topic_by_symbol

    async def _index_hsm_mapping(self) -> dict[str, str]:
        if self._index_hsm is not None:
            return self._index_hsm
        mapping = dict(INDEX_HSM_FALLBACK)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(INDEX_HSM_MAPPING_URL)
                if resp.status_code == 200:
                    live = resp.json()
                    if isinstance(live, dict):
                        mapping.update({k: v for k, v in live.items() if isinstance(v, str)})
        except Exception as exc:  # noqa: BLE001 - fallback table is sufficient
            logger.debug("fyers_ws_index_mapping_fetch_failed", error=str(exc)[:150])
        self._index_hsm = mapping
        return mapping

    # ── data ─────────────────────────────────────────────────────────────

    async def _apply_records(self, records: list[dict[str, Any]]) -> None:
        for record in records:
            topic = record.get("topic")
            if topic:
                self._topic_id_symbol[int(record["topic_id"])] = topic
                if record["kind"] == "snapshot":
                    self._topic_state[topic] = {
                        "multiplier": record.get("multiplier") or 1,
                        "precision": record.get("precision") or 0,
                    }
            else:
                topic = self._topic_id_symbol.get(int(record["topic_id"]))
            if not topic or not topic.startswith("if|"):
                continue

            # Updates only carry raw ints — they are unscalable until the
            # snapshot seeded the topic's multiplier/precision. Fail closed:
            # a missing seed drops the frame instead of emitting a wild value.
            state = self._topic_state.get(topic)
            if state is None:
                logger.debug("fyers_ws_update_before_snapshot", topic=topic)
                continue
            quote = decode_index_values(record["values"], state["precision"], state["multiplier"])
            symbol = self._symbol_by_topic.get(topic)
            if not symbol or "ltp" not in quote:
                continue
            quote["source"] = "ws"
            quote["exch_feed_time"] = quote.get("exch_feed_time")
            self.stats["ticks"] += 1
            self.stats["last_tick_at"] = datetime.now(timezone.utc).isoformat()
            try:
                await self._on_quote(symbol, quote)
            except Exception as exc:  # noqa: BLE001 - a consumer bug must not kill the socket
                logger.warning("fyers_ws_quote_consumer_failed", symbol=symbol, error=str(exc)[:150])
