import asyncio
import time
from collections import OrderedDict
from typing import NamedTuple
from app.models.contracts import TickEvent
from app.models.timeseries import CandleRecord
from app.services.timeseries_store import timeseries_store
from app.core.config import settings
import structlog

logger = structlog.get_logger()


class DeduplicationKey(NamedTuple):
    symbol: str
    timestamp_sec: int
    ltp: float
    volume: int
    seq_no: int | None


class TickDeduplicator:
    """Sliding-window LRU Deduplicator for high-frequency market tick streams.
    
    Adheres strictly to Section 24 (Tick Deduplication).
    """

    def __init__(self, max_history: int = 20000, window_seconds: float = 10.0):
        self.max_history = max_history
        self.window_seconds = window_seconds
        self._seen: OrderedDict[DeduplicationKey, float] = OrderedDict()
        self.duplicates_dropped: int = 0
        self.unique_passed: int = 0

    def is_duplicate(self, tick: TickEvent) -> bool:
        """Check if a tick has already been observed within the deduplication window."""
        now = time.monotonic()
        key = DeduplicationKey(
            symbol=tick.symbol,
            timestamp_sec=int(tick.timestamp.timestamp()),
            ltp=tick.ltp,
            volume=tick.volume,
            seq_no=tick.sequence_number,
        )

        # Evict old entries if past window or over capacity
        if key in self._seen:
            seen_time = self._seen[key]
            if now - seen_time <= self.window_seconds:
                self.duplicates_dropped += 1
                return True
            else:
                self._seen.pop(key, None)

        if len(self._seen) >= self.max_history:
            self._seen.popitem(last=False)

        self._seen[key] = now
        self.unique_passed += 1
        return False


class BatchWritePipeline:
    """Asynchronous Micro-Batch Write Pipeline for time-series persistence.
    
    Adheres strictly to Section 23 (Batch Write Pipeline).
    Eliminates database write thrashing by buffering ticks/candles and
    flushing in high-performance micro-batches.
    """

    def __init__(
        self,
        batch_size: int = 200,
        flush_interval_ms: int = 500,
    ):
        self.batch_size = batch_size
        self.flush_interval_seconds = flush_interval_ms / 1000.0
        self.deduplicator = TickDeduplicator()

        self._tick_queue: asyncio.Queue[TickEvent] = asyncio.Queue()
        self._candle_queue: asyncio.Queue[CandleRecord] = asyncio.Queue()
        self._running: bool = False
        self._worker_task: asyncio.Task | None = None

        # Telemetry
        self.total_enqueued: int = 0
        self.total_flushed: int = 0
        self.total_batches: int = 0

    async def start(self) -> None:
        """Start the background micro-batch flush worker."""
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._flush_loop())
        logger.info("batch_write_pipeline_started")

    async def stop(self) -> None:
        """Gracefully stop and flush remaining items."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        # Final flush
        await self._flush_all_pending()
        logger.info("batch_write_pipeline_stopped")

    async def enqueue_tick(self, tick: TickEvent) -> bool:
        """Enqueue tick after deduplication check."""
        if self.deduplicator.is_duplicate(tick):
            return False

        await self._tick_queue.put(tick)
        self.total_enqueued += 1
        return True

    async def enqueue_candle(self, candle: CandleRecord) -> None:
        """Enqueue a completed candle bar."""
        await self._candle_queue.put(candle)
        self.total_enqueued += 1

    async def _flush_loop(self) -> None:
        """Continuous micro-batch flushing loop."""
        while self._running:
            try:
                await asyncio.sleep(self.flush_interval_seconds)
                await self._flush_all_pending()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("batch_flush_error", error=str(e))

    async def _flush_all_pending(self) -> None:
        """Drain queues and insert batches into time-series store."""
        # Drain ticks
        ticks: list[TickEvent] = []
        while not self._tick_queue.empty() and len(ticks) < self.batch_size:
            ticks.append(self._tick_queue.get_nowait())

        if ticks:
            for t in ticks:
                await timeseries_store.insert_tick(t)
            self.total_flushed += len(ticks)
            self.total_batches += 1

        # Drain candles
        candles: list[CandleRecord] = []
        while not self._candle_queue.empty() and len(candles) < self.batch_size:
            candles.append(self._candle_queue.get_nowait())

        if candles:
            await timeseries_store.insert_candles_batch(candles)
            self.total_flushed += len(candles)
            self.total_batches += 1

    def get_stats(self) -> dict:
        return {
            "queue_depth": self._tick_queue.qsize() + self._candle_queue.qsize(),
            "total_enqueued": self.total_enqueued,
            "total_flushed": self.total_flushed,
            "total_batches": self.total_batches,
            "duplicates_dropped": self.deduplicator.duplicates_dropped,
            "unique_ticks_passed": self.deduplicator.unique_passed,
        }


write_pipeline = BatchWritePipeline(
    batch_size=settings.batch_write_max_size,
    flush_interval_ms=settings.batch_write_flush_interval_ms,
)
