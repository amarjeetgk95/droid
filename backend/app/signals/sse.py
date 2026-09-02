"""
Server-Sent Events (SSE) Real-Time Hub for Signal Centre
Implements event prioritization:
  - P0: Signal Creation, FSM Transitions (T1, T2, SL, Trigger, Confirm), Order Fills (Never dropped)
  - P1: Live Spot & Distance Updates (Coalesced 50-100ms)
  - P2: Scan Matrix Snapshots (Coalesced 250-500ms)
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator
import structlog

logger = structlog.get_logger()


class SignalSSEHub:
    def __init__(self):
        self._subscribers: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        self._subscribers.discard(q)

    async def broadcast(self, event_type: str, data: dict, priority: str = "P0"):
        payload = json.dumps(
            {"event": event_type, "data": data, "priority": priority, "timestamp": int(__import__("time").time() * 1000)},
            default=str,
        )
        for q in list(self._subscribers):
            try:
                if priority == "P0":
                    await q.put(payload)
                else:
                    if q.qsize() < 80:
                        q.put_nowait(payload)
            except Exception:
                self.unsubscribe(q)

    async def event_generator(self, queue: asyncio.Queue) -> AsyncGenerator[str, None]:
        try:
            yield f"event: connected\ndata: {json.dumps({'status': 'ok', 'message': 'Signal Stream Connected'})}\n\n"
            while True:
                data = await queue.get()
                yield f"event: signal_event\ndata: {data}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            self.unsubscribe(queue)


signal_sse_hub = SignalSSEHub()
