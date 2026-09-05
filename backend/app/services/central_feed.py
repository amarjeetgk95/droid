import asyncio
import json
from datetime import datetime, timezone
from typing import Set, Any
from fastapi import WebSocket
from app.models.contracts import TickEvent
from app.services.event_buffer import event_buffer
from app.services.data_quality import data_quality_engine
import structlog

logger = structlog.get_logger()


class CentralMarketDataFeed:
    """Centralized Market-Data Ingestion & Broadcast Hub.
    
    Adheres strictly to:
    - Section 5 (Centralized Ingestion: 1 connection serving all users)
    - Section 10 (Canonical Subscription Restoration)
    - Section 12 (Morning Market-Open Staged Warmup)
    """

    # Backpressure tuning — bounded 50-item buffer + drop-oldest + eviction.
    CLIENT_QUEUE_MAXSIZE = 50
    # Evict a client after this many consecutive broadcast drops (slow consumer).
    SLOW_CONSUMER_MAX_CONSECUTIVE_DROPS = 50
    # Hard cap: evict clients whose queue stays full beyond this many broadcasts.
    SLOW_CONSUMER_MAX_TOTAL_DROPS = 500

    def __init__(self):
        self._subscribers: dict[WebSocket, asyncio.Queue] = {}
        self._canonical_subscriptions: Set[str] = {"NIFTY 50", "BANKNIFTY", "FINNIFTY", "INDIA VIX"}
        self._running: bool = False
        self._worker_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        # Slow-consumer tracking: id(ws) -> consecutive + total drop counts.
        self._drop_counts: dict[int, dict[str, int]] = {}
        self._evicted_clients: int = 0
        self._dropped_messages: int = 0

        # Latest tick cache per symbol — used so REST get_quote can return LIVE even when Groww REST fails for indices
        # Frontend merges WS ticks, but REST status must also be LIVE when WS has recent tick (fixes offline statue with HEALTHY LIVE)
        self._latest_ticks: dict[str, TickEvent] = {}

        # Telemetry
        self.broadcast_count: int = 0
        self.started_at: datetime | None = None
        self.last_broadcast_at: datetime | None = None

    async def start(self) -> None:
        """Start the background broadcast worker."""
        if self._running:
            return

        self._running = True
        self.started_at = datetime.now(timezone.utc)
        self._worker_task = asyncio.create_task(self._broadcast_loop())
        logger.info("central_market_data_feed_started")

    async def stop(self) -> None:
        """Gracefully stop the background worker."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("central_market_data_feed_stopped")

    async def register_client(self, websocket: WebSocket) -> asyncio.Queue:
        """Register a connected frontend WebSocket client with a bounded queue (max 50)."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=self.CLIENT_QUEUE_MAXSIZE)
        async with self._lock:
            self._subscribers[websocket] = queue
            self._drop_counts.pop(id(websocket), None)
            logger.info("ws_client_connected", total_clients=len(self._subscribers))
        return queue

    async def unregister_client(self, websocket: WebSocket) -> None:
        """Unregister a disconnected frontend WebSocket client."""
        async with self._lock:
            self._subscribers.pop(websocket, None)
            self._drop_counts.pop(id(websocket), None)
            logger.info("ws_client_disconnected", total_clients=len(self._subscribers))

    async def broadcast_message(self, message: dict | str) -> int:
        """Broadcast an arbitrary control/data message (e.g. BROKER_AUTHENTICATED) to all connected clients."""
        raw_message = json.dumps(message) if isinstance(message, dict) else message
        async with self._lock:
            subscribers = list(self._subscribers.items())
        sent = 0
        for ws, q in subscribers:
            try:
                if q.full():
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                q.put_nowait(raw_message)
                sent += 1
            except Exception:
                pass
        return sent

    async def get_snapshot(self) -> dict[str, Any]:
        """Latest cached market snapshot for catch-up on connect/reconnect.

        Prefers coordinator-cached index cards (single-flight, O(1) upstream);
        falls back to latest ingested ticks when the coordinator has no data.
        """
        ticks: list[dict[str, Any]] = []
        try:
            from app.services.market_service import MarketService

            cards = await MarketService().get_index_cards()
            if cards:
                for c in cards:
                    if c.ltp is not None and c.ltp > 0:
                        ticks.append(
                            {
                                "symbol": c.symbol,
                                "instrument_token": c.symbol,
                                "ltp": float(c.ltp),
                                "open": float(c.open) if c.open else float(c.ltp),
                                "high": float(c.high) if c.high else float(c.ltp),
                                "low": float(c.low) if c.low else float(c.ltp),
                                "close": float(c.previous_close) if c.previous_close else float(c.ltp),
                                "volume": int(c.volume) if c.volume else 0,
                                "open_interest": c.open_interest,
                                "provider": c.provider,
                            }
                        )
                if ticks:
                    return {"ticks": ticks, "source": "coordinator"}
        except Exception as e:
            logger.debug("central_feed_snapshot_coordinator_failed", error=str(e)[:150])
        # Fallback: latest ingested ticks (up to 60s old, see get_latest_tick).
        try:
            for tick in list(self._latest_ticks.values()):
                fresh = self.get_latest_tick(tick.symbol)
                if fresh is not None:
                    ticks.append(fresh.model_dump(mode="json"))
            if ticks:
                return {"ticks": ticks, "source": "latest_ticks"}
        except Exception:
            pass
        return {"ticks": [], "source": "empty"}

    def add_subscription(self, symbol: str) -> None:
        """Add symbol to canonical subscription registry."""
        self._canonical_subscriptions.add(symbol)

    def get_subscriptions(self) -> list[str]:
        """Return the canonical list of active market subscriptions."""
        return list(self._canonical_subscriptions)

    async def ingest_tick(self, tick: TickEvent) -> bool:
        """Ingest tick from upstream provider, validate, and enqueue into ring buffer & write pipeline."""
        validation = data_quality_engine.validate_tick(tick)
        if not validation.is_valid:
            logger.warning("tick_quarantined", symbol=tick.symbol, reason=validation.reason)
            return False

        # Cache latest tick per symbol for REST fallback (so get_quote returns LIVE even when Groww REST 404 for indices)
        self._latest_ticks[tick.symbol] = tick

        # Asynchronously forward to batch write pipeline (non-blocking)
        from app.services.write_pipeline import write_pipeline
        await write_pipeline.enqueue_tick(tick)

        # Publish to event buffer with priority-based load shedding
        return event_buffer.publish(tick)

    def get_latest_tick(self, symbol: str) -> TickEvent | None:
        """Return latest tick for symbol if ingested within last 60s."""
        tick = self._latest_ticks.get(symbol)
        if not tick:
            return None
        # Consider stale after 60s (market closed or feed down) — then REST should show OFFLINE
        try:
            age = (datetime.now(timezone.utc) - tick.timestamp).total_seconds()
            if age > 60:
                return None
        except Exception:
            pass
        return tick

    async def _broadcast_loop(self) -> None:
        """Continuous background worker draining buffer and broadcasting to subscribers."""
        while self._running:
            try:
                # Consume batch of ticks
                batch = event_buffer.consume_batch(max_batch_size=50)
                if not batch:
                    await asyncio.sleep(0.05)  # 50ms idle sleep
                    continue

                if not self._subscribers:
                    continue

                payload = {
                    "type": "MARKET_TICKS",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "ticks": [t.model_dump(mode="json") for t in batch],
                }
                raw_message = json.dumps(payload)

                # Broadcast to all connected clients via bounded queues (drop-oldest backpressure)
                async with self._lock:
                    subscribers = list(self._subscribers.items())

                disconnected: list = []
                for ws, q in subscribers:
                    ws_id = id(ws)
                    try:
                        if q.full():
                            try:
                                q.get_nowait()  # Drop oldest superseded tick batch
                            except asyncio.QueueEmpty:
                                pass
                            # Track backpressure per slow client.
                            counts = self._drop_counts.get(ws_id)
                            if counts is None:
                                counts = {"consecutive": 0, "total": 0}
                                self._drop_counts[ws_id] = counts
                            counts["consecutive"] += 1
                            counts["total"] += 1
                            self._dropped_messages += 1
                            if (
                                counts["consecutive"] >= self.SLOW_CONSUMER_MAX_CONSECUTIVE_DROPS
                                or counts["total"] >= self.SLOW_CONSUMER_MAX_TOTAL_DROPS
                            ):
                                logger.warning(
                                    "ws_slow_consumer_evicted",
                                    consecutive=counts["consecutive"],
                                    total=counts["total"],
                                )
                                disconnected.append(ws)
                                try:
                                    await ws.close(code=1013, reason="slow consumer")
                                except Exception:
                                    pass
                                continue
                        else:
                            # Healthy drain resets the consecutive counter.
                            counts = self._drop_counts.get(ws_id)
                            if counts:
                                counts["consecutive"] = 0
                        q.put_nowait(raw_message)
                    except Exception:
                        disconnected.append(ws)

                # Clean up any dead sockets
                if disconnected:
                    async with self._lock:
                        for ws in disconnected:
                            self._subscribers.pop(ws, None)
                            self._drop_counts.pop(id(ws), None)
                            self._evicted_clients += 1

                self.broadcast_count += len(batch)
                self.last_broadcast_at = datetime.now(timezone.utc)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("broadcast_loop_error", error=str(e))
                await asyncio.sleep(0.1)

    def get_telemetry(self) -> dict:
        """Return central feed metrics."""
        return {
            "is_running": self._running,
            "connected_clients": len(self._subscribers),
            "canonical_subscriptions": len(self._canonical_subscriptions),
            "total_broadcast_ticks": self.broadcast_count,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_broadcast_at": self.last_broadcast_at.isoformat() if self.last_broadcast_at else None,
            "buffer_metrics": event_buffer.health(),
            "quality_metrics": data_quality_engine.get_metrics(),
            "client_queue_maxsize": self.CLIENT_QUEUE_MAXSIZE,
            "dropped_messages": self._dropped_messages,
            "evicted_clients": self._evicted_clients,
            "slow_consumer_threshold": self.SLOW_CONSUMER_MAX_CONSECUTIVE_DROPS,
        }


central_feed = CentralMarketDataFeed()
