"""P1-3/P1-4/P1-5 contract tests for the unified app stream.

Covers the ticket lifecycle, version-gated section emission (no per-poll
frames for unchanged sections), per-section coalescing, priority-aware
backpressure, slow-consumer eviction, fan-out at N subscribers, the hop
between the SignalSSEHub and `signal.event` frames, and the HTTP surface
(`POST /api/v1/stream/ticket`, `GET /api/v1/stream`).

The hub is exercised directly with injected clocks/intervals so no test sleeps
for real coalescing windows. Endpoint streaming uses httpx ASGITransport (the
TestClient buffers whole responses and would hang on an open SSE stream).
"""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.services.app_stream import (
    MAX_CONSECUTIVE_DROPS,
    QUEUE_MAXSIZE,
    AppStreamHub,
    StreamTicketStore,
    app_stream_hub,
)

FIXED_TS = "2026-09-18T07:22:01+00:00"


# ── Helpers ──────────────────────────────────────────────────────────────

def _section(value, version=1, degraded=False):
    return {
        "value": value,
        "updated_at": FIXED_TS,
        "freshness_s": 0,
        "degraded": degraded,
        "version": version,
    }


def _frames(queue: asyncio.Queue) -> list[dict]:
    """Drain a subscriber queue into parsed frame payloads."""
    frames: list[dict] = []
    while True:
        try:
            item = queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        if isinstance(item, tuple) and len(item) == 3:
            frames.append(json.loads(item[2]))
    return frames


def _raw(queue: asyncio.Queue) -> list:
    items = []
    while True:
        try:
            items.append(queue.get_nowait())
        except asyncio.QueueEmpty:
            break
    return items


@pytest.fixture
def make_hub(monkeypatch):
    """Fresh hub with the (heavy) CommandView composition stubbed out."""

    def _make(**kwargs) -> AppStreamHub:
        hub = AppStreamHub(attach_signals=False, **kwargs)

        async def _noop_compose():
            return {}

        monkeypatch.setattr(hub, "_compose_sections", _noop_compose)
        return hub

    return _make


# ── Ticket store (P1-4) ──────────────────────────────────────────────────

def test_ticket_round_trip_is_single_use():
    store = StreamTicketStore()
    ticket, expires_in = store.issue_ticket("user-1")
    assert isinstance(ticket, str) and ticket
    assert expires_in == 60

    assert store.redeem_ticket(ticket) == "user-1"
    # Single-use: the second redeem of the same ticket fails.
    assert store.redeem_ticket(ticket) is None
    # Unknown/None tickets never resolve.
    assert store.redeem_ticket("not-a-ticket") is None
    assert store.redeem_ticket(None) is None


@pytest.mark.asyncio
async def test_ticket_expiry():
    store = StreamTicketStore(ttl_seconds=0.05)
    ticket, _ = store.issue_ticket("user-2")
    await asyncio.sleep(0.06)
    assert store.redeem_ticket(ticket) is None


# ── Version gating + coalescing (P1-5) ───────────────────────────────────

@pytest.mark.asyncio
async def test_sections_emit_only_on_version_or_content_change(make_hub):
    hub = make_hub()
    queue = hub.subscribe()
    try:
        # First observation only seeds the broadcaster — never per-poll frames.
        await hub.broadcast_section_changes(
            {"market": _section({"ltp": 100}, version=1)}, now=1000.0
        )
        assert _frames(queue) == []

        # Identical payload/version: still nothing.
        await hub.broadcast_section_changes(
            {"market": _section({"ltp": 100}, version=1)}, now=1000.5
        )
        assert _frames(queue) == []

        # A real change emits exactly one frame.
        assert await hub.broadcast_section_changes(
            {"market": _section({"ltp": 101}, version=2)}, now=1001.0
        ) == ["market"]
        frames = _frames(queue)
        assert len(frames) == 1
        assert frames[0]["event"] == "view.section.changed"
        assert frames[0]["priority"] == "P1"
        assert frames[0]["data"]["section"] == "market"
        assert frames[0]["data"]["version"] == 2
        assert frames[0]["data"]["value"] == {"ltp": 101}

        # Same payload repeated after the change does not re-emit.
        await hub.broadcast_section_changes(
            {"market": _section({"ltp": 101}, version=2)}, now=1002.0
        )
        assert _frames(queue) == []
    finally:
        await hub.stop()


@pytest.mark.asyncio
async def test_coalescing_caps_one_frame_per_window(make_hub):
    hub = make_hub(section_coalesce_s=1.0)
    queue = hub.subscribe()
    try:
        await hub.broadcast_section_changes(
            {"signals": _section({"count": 0}, version=1)}, now=1000.0
        )
        await hub.broadcast_section_changes(
            {"signals": _section({"count": 1}, version=2)}, now=1001.0
        )
        assert len(_frames(queue)) == 1

        # Three changes inside the 1 s window collapse into a single frame.
        await hub.broadcast_section_changes(
            {"signals": _section({"count": 2}, version=3)}, now=1001.1
        )
        await hub.broadcast_section_changes(
            {"signals": _section({"count": 3}, version=4)}, now=1001.3
        )
        await hub.broadcast_section_changes(
            {"signals": _section({"count": 4}, version=5)}, now=1001.5
        )
        assert _frames(queue) == []

        # Once the window elapses, one coalesced frame carries the newest value.
        await hub.broadcast_section_changes(
            {"signals": _section({"count": 4}, version=5)}, now=1002.0
        )
        frames = _frames(queue)
        assert len(frames) == 1
        assert frames[0]["data"]["version"] == 5
        assert frames[0]["data"]["value"] == {"count": 4}

        # And the next immediate change waits for a fresh window.
        await hub.broadcast_section_changes(
            {"signals": _section({"count": 5}, version=6)}, now=1002.2
        )
        assert _frames(queue) == []
    finally:
        await hub.stop()


# ── Backpressure / drop policy ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_backpressure_drops_p1_p2_before_p0(make_hub):
    hub = make_hub()
    queue = hub.subscribe()
    try:
        for i in range(QUEUE_MAXSIZE):
            queue.put_nowait((0, "view.section.changed", json.dumps({"seed": i})))

        # A queue full of P0 frames must not be displaced for P1/P2 traffic.
        await hub.publish("heartbeat", {"beat": 1}, priority="P2")
        await hub.publish("view.section.changed", {"section": "market"}, priority="P1")
        assert queue.qsize() == QUEUE_MAXSIZE
        assert hub.stats()["dropped"] == 2
        assert {item[0] for item in _raw(queue)} == {0}

        # P0 is accepted again the moment the consumer drains the queue.
        await hub.publish(
            "view.section.changed", {"section": "market"}, priority="P0"
        )
        delivered = _raw(queue)
        assert len(delivered) == 1
        assert delivered[0][1] == "view.section.changed"
        payload = json.loads(delivered[0][2])
        assert payload["priority"] == "P0"
        assert payload["data"] == {"section": "market"}
    finally:
        await hub.stop()


@pytest.mark.asyncio
async def test_slow_consumer_evicted_after_sustained_drops(make_hub):
    hub = make_hub()
    queue = hub.subscribe()
    try:
        for _ in range(QUEUE_MAXSIZE):
            queue.put_nowait((0, "view.section.changed", "{}"))
        for _ in range(MAX_CONSECUTIVE_DROPS):
            await hub.publish("heartbeat", {}, priority="P2")
        assert hub.stats()["evicted"] == 1
        assert queue not in hub._subscribers
    finally:
        await hub.stop()


# ── Fan-out ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fanout_25_subscribers_receive_one_changed_section(make_hub):
    hub = make_hub()
    queues = [hub.subscribe() for _ in range(25)]
    try:
        await hub.broadcast_section_changes(
            {"signals": _section({"count": 0}, version=1)}, now=1000.0
        )
        await hub.broadcast_section_changes(
            {"signals": _section({"count": 1}, version=2)}, now=1001.0
        )
        for queue in queues:
            frames = _frames(queue)
            assert len(frames) == 1, "each subscriber must get exactly one delta"
            assert frames[0]["event"] == "view.section.changed"
            assert frames[0]["data"]["section"] == "signals"
            assert frames[0]["data"]["version"] == 2
    finally:
        await hub.stop()


# ── Signal bridge + hints ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_signal_broadcast_reeemitted_as_signal_event(make_hub):
    from app.signals.sse import signal_sse_hub

    hub = make_hub()
    queue = hub.subscribe()
    hub.attach_to_signal_hub()
    try:
        await signal_sse_hub.broadcast(
            "fsm_transition", {"signal_id": "sig-1", "to_state": "CONFIRMED"}, priority="P0"
        )
        frames = _frames(queue)
        assert len(frames) == 1
        assert frames[0]["event"] == "signal.event"
        # signal.event is P1 in the unified stream (P0 reservation is
        # action-required hints); the source priority is kept
        # inside the payload for the UI.
        assert frames[0]["priority"] == "P1"
        assert frames[0]["data"]["event"] == "fsm_transition"
        assert frames[0]["data"]["priority"] == "P0"
        assert frames[0]["data"]["data"]["signal_id"] == "sig-1"
    finally:
        hub.detach_from_signal_hub()
        await hub.stop()


@pytest.mark.asyncio
async def test_hint_frames_and_priority(make_hub):
    hub = make_hub()
    queue = hub.subscribe()
    try:
        await hub.raise_hint({"id": "feed:stale:SENSEX", "action_required": True})
        await hub.raise_hint({"id": "info:lunch", "action_required": False})
        await hub.clear_hint("feed:stale:SENSEX")

        frames = _frames(queue)
        assert [f["event"] for f in frames] == [
            "hint.raised",
            "hint.raised",
            "hint.cleared",
        ]
        assert [f["priority"] for f in frames] == ["P0", "P1", "P1"]
        assert frames[0]["data"]["hint"]["id"] == "feed:stale:SENSEX"
        assert frames[2]["data"]["id"] == "feed:stale:SENSEX"
    finally:
        await hub.stop()


@pytest.mark.asyncio
async def test_heartbeat_after_idle(make_hub):
    hub = make_hub(heartbeat_s=0.05)
    queue = hub.subscribe()
    generator = hub.event_generator(queue)
    try:
        connected = await asyncio.wait_for(anext(generator), timeout=1.0)
        assert connected.startswith("event: connected")
        frame = await asyncio.wait_for(anext(generator), timeout=1.0)
        assert frame.startswith("event: heartbeat")
        payload = json.loads(frame.split("data: ", 1)[1])
        assert payload["event"] == "heartbeat"
        assert payload["priority"] == "P2"
        assert payload["seq"] >= 1
    finally:
        await generator.aclose()
        await hub.stop()


# ── HTTP surface ─────────────────────────────────────────────────────────

def test_stream_ticket_endpoint():
    client = TestClient(app)
    response = client.post("/api/v1/stream/ticket")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["ticket"], str) and body["ticket"]
    assert body["expires_in"] == 60


async def _drive_get(path: str, *, timeout: float = 5.0) -> list[dict]:
    """Drive one GET through the raw ASGI app and return its messages.

    httpx's ASGITransport buffers the entire response, which never completes
    for an infinite SSE stream, so this minimal driver stops after the first
    body frame and then disconnects (the endpoint's generator unsubscribes).
    """
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"testserver")],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }
    messages: list[dict] = []
    first_body = asyncio.Event()
    disconnected = asyncio.Event()

    async def receive():
        await disconnected.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)
        if message["type"] == "http.response.body" and message.get("body"):
            first_body.set()

    task = asyncio.create_task(app(scope, receive, send))
    try:
        await asyncio.wait_for(first_body.wait(), timeout=timeout)
    finally:
        disconnected.set()
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    return messages


@pytest.mark.asyncio
async def test_stream_endpoint_smoke_first_frame(monkeypatch):
    async def _noop_compose():
        return {}

    monkeypatch.setattr(app_stream_hub, "_compose_sections", _noop_compose)
    try:
        messages = await _drive_get("/api/v1/stream")
    finally:
        await app_stream_hub.stop()

    start = next(m for m in messages if m["type"] == "http.response.start")
    assert start["status"] == 200
    headers = {k.decode().lower(): v.decode() for k, v in start["headers"]}
    assert headers["content-type"].startswith("text/event-stream")
    assert headers["cache-control"] == "no-cache"
    assert headers["x-accel-buffering"] == "no"

    first_body = next(m for m in messages if m["type"] == "http.response.body")
    assert first_body["body"].decode().startswith("event: connected")


# ── WS ticket enforcement (P1-4) ─────────────────────────────────────────

def test_ws_accepts_valid_single_use_ticket():
    client = TestClient(app)
    ticket = client.post("/api/v1/stream/ticket").json()["ticket"]

    with client.websocket_connect(f"/api/v1/ws/market-feed?ticket={ticket}") as websocket:
        message = json.loads(websocket.receive_text())
        assert message["type"] == "CONNECTION_ESTABLISHED"

    # The ticket was consumed: the same one cannot be replayed.
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/api/v1/ws/market-feed?ticket={ticket}") as websocket:
            websocket.receive_text()
    assert exc.value.code == 4401


def test_ws_rejects_invalid_ticket():
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/api/v1/ws/market-feed?ticket=bogus") as websocket:
            websocket.receive_text()
    assert exc.value.code == 4401


def test_ws_without_ticket_preserves_legacy_behavior():
    # AUTH_REQUIRED defaults to false in dev: no ticket must behave exactly as
    # before P1-4 (see tests/test_websocket_feed.py for the full contract).
    client = TestClient(app)
    with client.websocket_connect("/api/v1/ws/market-feed") as websocket:
        message = json.loads(websocket.receive_text())
        assert message["type"] == "CONNECTION_ESTABLISHED"
