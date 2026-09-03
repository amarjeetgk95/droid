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

    def __init__(self):
        self._subscribers: Set[WebSocket] = set()
        self._canonical_subscriptions: Set[str] = {"NIFTY 50", "BANKNIFTY", "FINNIFTY", "INDIA VIX"}
        self._running: bool = False
        self._worker_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

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

    async def register_client(self, websocket: WebSocket) -> None:
        """Register a connected frontend WebSocket client (subscribe-only).

        Adds the socket to the broadcast set. Does NOT start any upstream
        service — the FYERS stream is backend-owned (lifespan) and already
        running independently of how many clients are connected.
        """
        async with self._lock:
            self._subscribers.add(websocket)
            logger.info("ws_client_connected", total_clients=len(self._subscribers))

    async def unregister_client(self, websocket: WebSocket) -> None:
        """Unregister a disconnected frontend WebSocket client (remove-only).

        NEVER stops the upstream FYERS stream or Telegram services, even when
        zero clients remain — ingestion continues so the next browser that
        opens instantly receives live data.
        """
        async with self._lock:
            self._subscribers.discard(websocket)
            logger.info("ws_client_disconnected", total_clients=len(self._subscribers))

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

                # Broadcast to all connected clients
                disconnected = []
                for ws in list(self._subscribers):
                    try:
                        await ws.send_text(raw_message)
                    except Exception:
                        disconnected.append(ws)

                # Clean up any dead sockets
                if disconnected:
                    async with self._lock:
                        for ws in disconnected:
                            self._subscribers.discard(ws)

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
        }


central_feed = CentralMarketDataFeed()
