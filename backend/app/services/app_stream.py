"""
Unified app stream hub — P1-3 (multiplexed SSE), P1-4 (ticket auth), P1-5 (hygiene).

One SSE connection per tab carries every server-pushed concern:

  * ``view.section.changed`` — version-gated CommandView section deltas.
    A single background task composes the frozen CommandView roughly every 2 s,
    compares each section against its last version/content digest, and emits
    only genuinely changed sections, coalesced to at most one frame per section
    per second. The kill-switch section is P0; every other section is P1.
  * ``signal.event`` — re-emission of ``SignalSSEHub`` broadcasts (P1).
  * ``hint.raised`` / ``hint.cleared`` — operator hint lifecycle. Hints with
    ``action_required`` are P0; informational hints are P1.
  * ``heartbeat`` — emitted after 15 s of subscriber idle (P2).

Subscriber model mirrors ``app/signals/sse.py`` for the priority/drop contract
and ``app/services/central_feed.py`` for the bounded drop-oldest policy:

  * per-subscriber bounded queue (maxsize 50);
  * P0 frames are never dropped to make room — a queue that cannot accept a P0
    frame within 0.5 s is a slow consumer and is evicted instead;
  * P1/P2 frames only enter below a 40-frame watermark and, when the queue is
    full, evict the oldest strictly-lower-priority queued frame; if none exists
    (the queue is all P0) the incoming frame is dropped;
  * sustained drops (``MAX_CONSECUTIVE_DROPS``) evict the slow consumer.

The hub is single-process, in-memory, and touched only from the event loop
(no awaits between a read and its matching write), so it needs no locks. The
ticket store only does whole-dict operations, which are atomic under the GIL.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import time
from collections.abc import AsyncGenerator
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

#: Priority ranks — lower binds tighter. P0 frames are never dropped for room.
PRIORITY_RANK: dict[str, int] = {"P0": 0, "P1": 1, "P2": 2}

QUEUE_MAXSIZE = 50
#: P1/P2 frames only enter a queue below this size (sse.py enforces 80/100).
LOW_PRIORITY_WATERMARK = 40
#: How long a P0 frame waits for room before its subscriber is evicted.
P0_PUT_TIMEOUT = 0.5
#: Consecutive P1/P2 drops after which a slow consumer is evicted.
MAX_CONSECUTIVE_DROPS = 50
HEARTBEAT_SECONDS = 15.0
SECTION_INTERVAL_SECONDS = 2.0
SECTION_COALESCE_SECONDS = 1.0
TICKET_TTL_SECONDS = 60

_EVICT = object()
#: (priority rank, SSE event name, serialized JSON payload)
Frame = tuple[int, str, str]


def _content_digest(value: Any) -> str:
    """Stable sha256 over a section value (same recipe as view.py versions)."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


class AppStreamHub:
    """Multiplexing fan-out hub behind ``GET /api/v1/stream``."""

    def __init__(
        self,
        *,
        section_interval: float = SECTION_INTERVAL_SECONDS,
        section_coalesce_s: float = SECTION_COALESCE_SECONDS,
        heartbeat_s: float = HEARTBEAT_SECONDS,
        p0_put_timeout: float = P0_PUT_TIMEOUT,
        attach_signals: bool = True,
    ) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._drop_counts: dict[int, int] = {}
        self._seq: int = 0
        self._dropped: int = 0
        self._evicted: int = 0
        self._section_interval = section_interval
        self._section_coalesce_s = section_coalesce_s
        self._heartbeat_s = heartbeat_s
        self._p0_put_timeout = p0_put_timeout
        self._section_task: asyncio.Task | None = None
        #: section -> {"version": int|None, "digest": str} last observed.
        self._section_state: dict[str, dict[str, Any]] = {}
        self._last_emit: dict[str, float] = {}
        self._pending_sections: dict[str, dict[str, Any]] = {}
        self._section_seeded = False
        self._signal_hub: Any = None
        if attach_signals:
            self.attach_to_signal_hub()

    # ── Subscription ─────────────────────────────────────────────────────

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
        self._subscribers.add(queue)
        self._drop_counts.pop(id(queue), None)
        self._ensure_section_task()
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)
        self._drop_counts.pop(id(queue), None)

    def next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def stats(self) -> dict[str, Any]:
        return {
            "subscribers": len(self._subscribers),
            "seq": self._seq,
            "dropped": self._dropped,
            "evicted": self._evicted,
            "section_versions": {k: v.get("version") for k, v in self._section_state.items()},
        }

    async def stop(self) -> None:
        """Cancel the section task and drop every subscriber (test/shutdown aid)."""
        task = self._section_task
        self._section_task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._subscribers.clear()
        self._drop_counts.clear()

    # ── Frame publishing ─────────────────────────────────────────────────

    def _make_frame(self, event_type: str, data: Any, priority: str) -> Frame:
        payload = json.dumps(
            {
                "event": event_type,
                "data": data,
                "priority": priority,
                "seq": self.next_seq(),
                "timestamp": int(time.time() * 1000),
            },
            default=str,
        )
        return (PRIORITY_RANK.get(priority, 1), event_type, payload)

    async def publish(self, event_type: str, data: Any, priority: str = "P1") -> None:
        """Fan a frame out to every subscriber (P0 may briefly block for room)."""
        if not self._subscribers:
            return
        frame = self._make_frame(event_type, data, priority)
        rank = frame[0]
        for queue in list(self._subscribers):
            await self._deliver(queue, rank, frame)

    def publish_nowait(self, event_type: str, data: Any, priority: str = "P1") -> None:
        """Synchronous fan-out for callers that must never await (signal hook)."""
        if not self._subscribers:
            return
        frame = self._make_frame(event_type, data, priority)
        rank = frame[0]
        for queue in list(self._subscribers):
            self._deliver_nowait(queue, rank, frame)

    async def raise_hint(self, hint: dict[str, Any]) -> None:
        """Publish a ``hint.raised`` frame (P0 when the hint needs action)."""
        priority = "P0" if bool(hint.get("action_required")) else "P1"
        await self.publish("hint.raised", {"hint": hint}, priority=priority)

    async def clear_hint(self, hint_id: str) -> None:
        """Publish a ``hint.cleared`` frame for a previously raised hint."""
        await self.publish("hint.cleared", {"id": str(hint_id)}, priority="P1")

    # ── Backpressure (mirrors central_feed + sse.py priority rules) ──────

    async def _deliver(self, queue: asyncio.Queue, rank: int, frame: Frame) -> None:
        if rank != PRIORITY_RANK["P0"]:
            self._deliver_nowait(queue, rank, frame)
            return
        try:
            queue.put_nowait(frame)
            self._drop_counts.pop(id(queue), None)
            return
        except asyncio.QueueFull:
            pass
        try:
            await asyncio.wait_for(queue.put(frame), timeout=self._p0_put_timeout)
            self._drop_counts.pop(id(queue), None)
        except asyncio.TimeoutError:
            logger.warning("app_stream_p0_slow_consumer_evicted", rank=rank)
            self._evict_queue(queue, reason="p0_backpressure")

    def _deliver_nowait(self, queue: asyncio.Queue, rank: int, frame: Frame) -> None:
        if rank == PRIORITY_RANK["P0"]:
            try:
                queue.put_nowait(frame)
                self._drop_counts.pop(id(queue), None)
            except asyncio.QueueFull:
                self._note_drop(queue)
            return
        if queue.qsize() < LOW_PRIORITY_WATERMARK:
            try:
                queue.put_nowait(frame)
                self._drop_counts.pop(id(queue), None)
                return
            except asyncio.QueueFull:
                pass
        if self._drop_oldest_below(queue, rank):
            try:
                queue.put_nowait(frame)
                self._note_drop(queue)
                return
            except asyncio.QueueFull:
                pass
        self._note_drop(queue)

    def _drop_oldest_below(self, queue: asyncio.Queue, incoming_rank: int) -> bool:
        """Remove the oldest queued frame of lower priority than ``incoming_rank``.

        Rebuilds the queue in order through the public API (single-threaded
        event loop, no awaits in between). Returns True when a frame was freed.
        """
        drained: list[Any] = []
        try:
            while True:
                drained.append(queue.get_nowait())
        except asyncio.QueueEmpty:
            pass
        kept: list[Any] = []
        dropped = False
        for item in drained:
            if (
                not dropped
                and isinstance(item, tuple)
                and len(item) == 3
                and int(item[0]) > incoming_rank
            ):
                dropped = True
                continue
            kept.append(item)
        for item in kept:
            queue.put_nowait(item)
        return dropped

    def _note_drop(self, queue: asyncio.Queue) -> None:
        self._dropped += 1
        key = id(queue)
        count = self._drop_counts.get(key, 0) + 1
        if count >= MAX_CONSECUTIVE_DROPS:
            self._evict_queue(queue, reason="slow_consumer")
            return
        self._drop_counts[key] = count

    def _evict_queue(self, queue: asyncio.Queue, *, reason: str) -> None:
        if queue not in self._subscribers:
            return
        self.unsubscribe(queue)
        self._evicted += 1
        logger.warning("app_stream_slow_consumer_evicted", reason=reason, evicted=self._evicted)
        try:
            while True:
                queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        try:
            queue.put_nowait(_EVICT)
        except Exception:
            pass

    # ── SSE generation ───────────────────────────────────────────────────

    async def event_generator(self, queue: asyncio.Queue) -> AsyncGenerator[str, None]:
        try:
            yield 'event: connected\ndata: {"status": "ok", "message": "App stream connected"}\n\n'
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=self._heartbeat_s)
                except asyncio.TimeoutError:
                    if queue not in self._subscribers:
                        break
                    yield self._heartbeat_sse()
                    continue
                if item is _EVICT:
                    break
                _rank, event_type, payload = item
                yield f"event: {event_type}\ndata: {payload}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            self.unsubscribe(queue)

    def _heartbeat_sse(self) -> str:
        payload = json.dumps(
            {
                "event": "heartbeat",
                "data": {"status": "ok"},
                "priority": "P2",
                "seq": self.next_seq(),
                "timestamp": int(time.time() * 1000),
            }
        )
        return f"event: heartbeat\ndata: {payload}\n\n"

    # ── Version-gated section broadcaster (P1-5) ─────────────────────────

    def _ensure_section_task(self) -> None:
        if self._section_task is not None and not self._section_task.done():
            return
        if not self._subscribers:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._section_task = loop.create_task(self._section_loop())

    async def _section_loop(self) -> None:
        try:
            sections = await self._compose_sections()
            await self.broadcast_section_changes(sections)
            while self._subscribers:
                await asyncio.sleep(self._section_interval)
                if not self._subscribers:
                    break
                sections = await self._compose_sections()
                await self.broadcast_section_changes(sections)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("app_stream_section_loop_failed", error=str(e)[:200])

    async def _compose_sections(self) -> dict[str, Any]:
        from app.api.view import compose_command_view

        view = await compose_command_view()
        return view.get("sections") or {}

    async def broadcast_section_changes(
        self, sections: dict[str, Any], now: float | None = None
    ) -> list[str]:
        """Compare composed sections with the last version/digest and emit deltas.

        The first observation only seeds state (no frames) — clients fetch the
        full CommandView once and then live on deltas. Returns the names of the
        sections emitted by this call (test/telemetry aid).
        """
        if not sections:
            return []
        now = time.monotonic() if now is None else now
        if not self._section_seeded:
            for name, section in sections.items():
                self._record_section(name, section)
            self._section_seeded = True
            return []

        emitted: list[str] = []
        for name, section in sections.items():
            prev = self._section_state.get(name)
            version = section.get("version")
            digest = _content_digest(section.get("value"))
            if prev is not None and prev.get("version") == version and prev.get("digest") == digest:
                continue
            self._record_section(name, section)
            payload = {
                "section": name,
                "version": version,
                "value": section.get("value"),
                "updated_at": section.get("updated_at"),
                "freshness_s": section.get("freshness_s"),
                "degraded": bool(section.get("degraded", False)),
            }
            last_emit = self._last_emit.get(name)
            if last_emit is not None and (now - last_emit) < self._section_coalesce_s:
                self._pending_sections[name] = payload
                continue
            await self._emit_section(name, payload, now)
            emitted.append(name)

        for name in list(self._pending_sections):
            last_emit = self._last_emit.get(name)
            if last_emit is not None and (now - last_emit) < self._section_coalesce_s:
                continue
            payload = self._pending_sections.pop(name)
            await self._emit_section(name, payload, now)
            emitted.append(name)
        return emitted

    def _record_section(self, name: str, section: dict[str, Any]) -> None:
        self._section_state[name] = {
            "version": section.get("version"),
            "digest": _content_digest(section.get("value")),
        }

    async def _emit_section(self, name: str, payload: dict[str, Any], now: float) -> None:
        priority = "P0" if name == "kill_switch" else "P1"
        await self.publish("view.section.changed", payload, priority=priority)
        self._last_emit[name] = now

    # ── SignalSSEHub bridge ──────────────────────────────────────────────

    def attach_to_signal_hub(self) -> None:
        """Subscribe to signal broadcasts (idempotent, best-effort)."""
        if self._signal_hub is not None:
            return
        try:
            from app.signals.sse import signal_sse_hub
        except Exception as e:  # pragma: no cover - import guard
            logger.warning("app_stream_signal_hub_unavailable", error=str(e)[:150])
            return
        signal_sse_hub.add_listener(self._on_signal_event)
        self._signal_hub = signal_sse_hub

    def detach_from_signal_hub(self) -> None:
        hub = self._signal_hub
        self._signal_hub = None
        if hub is None:
            return
        try:
            hub.remove_listener(self._on_signal_event)
        except Exception:
            pass

    def _on_signal_event(
        self, event_type: str, data: dict[str, Any], priority: str = "P0", seq: int = 0
    ) -> None:
        """Re-emit a signal hub broadcast as a unified ``signal.event`` frame.

        Synchronous by contract: the hook must never delay ``/signals/stream``,
        and P1 fan-out is lock-free/no-await by construction.
        """
        self.publish_nowait(
            "signal.event",
            {
                "event": event_type,
                "data": data,
                "priority": priority,
                "seq": seq,
                "timestamp": int(time.time() * 1000),
            },
            priority="P1",
        )


class StreamTicketStore:
    """In-memory single-use stream tickets (P1-4).

    Tickets are bearer credentials with a 60 s TTL and read-only scope: they
    only unlock the market-feed WebSocket upgrade, are consumed on first
    redeem, and never carry identity beyond the owning ``user_id``. Whole-dict
    operations are atomic under the GIL, so no lock is required.
    """

    def __init__(self, ttl_seconds: float = TICKET_TTL_SECONDS) -> None:
        self._ttl_seconds = max(0.0, float(ttl_seconds))
        self._tickets: dict[str, tuple[str, float]] = {}

    def _purge(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        expired = [t for t, (_uid, exp) in self._tickets.items() if exp <= now]
        for ticket in expired:
            self._tickets.pop(ticket, None)

    def issue_ticket(self, user_id: str) -> tuple[str, int]:
        """Mint a single-use ticket; returns ``(ticket, expires_in_seconds)``."""
        self._purge()
        ticket = secrets.token_urlsafe(32)
        self._tickets[ticket] = (str(user_id or ""), time.monotonic() + self._ttl_seconds)
        return ticket, int(self._ttl_seconds)

    def redeem_ticket(self, ticket: str | None) -> str | None:
        """Consume a ticket, returning its ``user_id`` (or None when invalid)."""
        self._purge()
        if not ticket:
            return None
        entry = self._tickets.pop(str(ticket), None)
        if entry is None:
            return None
        user_id, expires_at = entry
        if time.monotonic() > expires_at:
            return None
        return user_id


app_stream_hub = AppStreamHub()
ticket_store = StreamTicketStore()
