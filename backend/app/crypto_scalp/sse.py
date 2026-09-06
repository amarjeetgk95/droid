"""
Server-Sent Events (SSE) Hub for Real-Time Crypto Signals & Execution Stream
Priorities:
  P0: Signal Created, Confirmed, Stage Fills, Target/Stop Exits (instant dispatch)
  P1: Real-Time Mark-to-Market (MTM) and PnL updates
  P2: Scanner updates and telemetry heartbeats
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator
import structlog

logger = structlog.get_logger()


class CryptoSSEHub:
    """Pub/Sub SSE hub for broadcasting crypto signal lifecycle events to frontend clients."""

    def __init__(self):
        self._subscribers: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.add(q)
        logger.debug("crypto_sse_subscriber_joined", active=len(self._subscribers))
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)
        logger.debug("crypto_sse_subscriber_left", active=len(self._subscribers))

    async def broadcast(self, event_type: str, data: dict, priority: str = "P0") -> None:
        if not self._subscribers:
            return

        payload = {
            "event": event_type,
            "priority": priority,
            "data": data,
            "timestamp_ms": int(__import__("time").time() * 1000),
        }
        msg = f"event: {event_type}\ndata: {json.dumps(payload, default=str)}\n\n"

        dead = set()
        for q in list(self._subscribers):
            try:
                if q.full():
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                q.put_nowait(msg)
            except Exception:
                dead.add(q)

        for d in dead:
            self.unsubscribe(d)

    async def event_generator(self, q: asyncio.Queue) -> AsyncGenerator[str, None]:
        try:
            # Send initial connection handshake
            yield f"event: connected\ndata: {json.dumps({'status': 'connected', 'channel': 'crypto_signals'})}\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=20.0)
                    yield msg
                except asyncio.TimeoutError:
                    # Keep-alive ping
                    yield "event: ping\ndata: {}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            self.unsubscribe(q)


crypto_sse_hub = CryptoSSEHub()
