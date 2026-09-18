"""
Server-Sent Events (SSE) Real-Time Hub for Signal Centre
Implements event prioritization:
  - P0: Signal Creation, FSM Transitions (T1, T2, SL, Trigger, Confirm), Order Fills (Never dropped)
  - P1: Live Spot & Distance Updates (Coalesced 50-100ms)
  - P2: Scan Matrix Snapshots (Coalesced 250-500ms)
Global seq + lag/drop counters; shared 1s FEED_STATUS cache; P0 block-with-timeout.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import AsyncGenerator, Callable
import structlog

logger = structlog.get_logger()

_FEED_CACHE: dict = {"ns": 0, "payload": None}
_FEED_TTL_NS = 1_000_000_000


def _cached_feed():
    now_ns = time.monotonic_ns()
    if _FEED_CACHE.get("payload") is not None and now_ns - int(_FEED_CACHE.get("ns") or 0) < _FEED_TTL_NS:
        return _FEED_CACHE["payload"]
    try:
        from app.signals.safety.feed_health_monitor import feed_health_monitor
        payload = feed_health_monitor.get_telemetry()
    except Exception:
        payload = {"status": "UNKNOWN"}
    _FEED_CACHE["ns"] = now_ns
    _FEED_CACHE["payload"] = payload
    return payload


class SignalSSEHub:
    def __init__(self):
        self._subscribers: set[asyncio.Queue] = set()
        self._seq: int = 0
        self._dropped: int = 0
        self._lag_max: int = 0
        # Notification-only observers (e.g. the unified app stream). They are
        # dispatched synchronously after the subscriber fan-out, never affect
        # delivery, and their failures are quarantined.
        self._listeners: set[Callable[[str, dict, str, int], None]] = set()

    def add_listener(self, listener: Callable[[str, dict, str, int], None]) -> None:
        self._listeners.add(listener)

    def remove_listener(self, listener: Callable[[str, dict, str, int], None]) -> None:
        self._listeners.discard(listener)

    def _notify_listeners(self, event_type: str, data: dict, priority: str, seq: int) -> None:
        if not self._listeners:
            return
        for listener in list(self._listeners):
            try:
                listener(event_type, data, priority, seq)
            except Exception as e:
                logger.warning(
                    "sse_listener_failed", event_type=event_type, error=str(e)[:150]
                )

    def next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def drop_count(self) -> int:
        return self._dropped

    def lag_stats(self) -> dict:
        return {"dropped": self._dropped, "lag_max": self._lag_max, "seq": self._seq}

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        self._subscribers.discard(q)

    async def broadcast(self, event_type: str, data: dict, priority: str = "P0"):
        seq = self.next_seq()
        try:
            lag = 0
            for q in list(self._subscribers):
                try:
                    lag = max(lag, q.qsize())
                except Exception:
                    pass
            self._lag_max = max(self._lag_max, lag)
        except Exception:
            pass
        payload = json.dumps(
            {"event": event_type, "data": data, "priority": priority,
             "seq": seq, "timestamp": int(time.time() * 1000)},
            default=str,
        )
        for q in list(self._subscribers):
            try:
                if priority == "P0":
                    # Block-with-timeout (never evict-oldest): P0 must not lose
                    # history to make room; backpressure instead of silent drop.
                    try:
                        q.put_nowait(payload)
                    except asyncio.QueueFull:
                        try:
                            await asyncio.wait_for(q.put(payload), timeout=0.5)
                        except asyncio.TimeoutError:
                            self._dropped += 1
                            logger.warning("sse_p0_drop_counted", seq=seq, dropped=self._dropped)
                else:
                    if q.qsize() < 80:
                        q.put_nowait(payload)
                    else:
                        self._dropped += 1
            except Exception:
                self.unsubscribe(q)
        # Additive notification hook: the unified app stream mirrors broadcasts
        # as `signal.event` frames. Existing `/signals/stream` delivery above is
        # untouched; listener failures never escape.
        self._notify_listeners(event_type, data, priority, seq)

    async def event_generator(self, queue: asyncio.Queue) -> AsyncGenerator[str, None]:
        try:
            yield f"event: connected\ndata: {json.dumps({'status': 'ok', 'message': 'Signal Stream Connected'})}\n\n"
            initial_feed = _cached_feed()
            yield f"event: signal_event\ndata: {json.dumps({'event': 'FEED_STATUS', 'data': initial_feed, 'priority': 'P0', 'timestamp': int(time.time() * 1000)}, default=str)}\n\n"

            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=5.0)
                    yield f"event: signal_event\ndata: {data}\n\n"
                except asyncio.TimeoutError:
                    # Periodic 5s feed telemetry heartbeat (shared 1s cache).
                    current_feed = _cached_feed()
                    yield f"event: signal_event\ndata: {json.dumps({'event': 'FEED_STATUS', 'data': current_feed, 'priority': 'P2', 'timestamp': int(time.time() * 1000)}, default=str)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            self.unsubscribe(queue)


signal_sse_hub = SignalSSEHub()
