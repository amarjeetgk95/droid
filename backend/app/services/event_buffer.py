from collections import deque
from typing import Deque
from app.models.contracts import TickEvent, EventPriority
import structlog

logger = structlog.get_logger()


class MarketEventBuffer:
    """High-frequency in-memory ring buffer with priority-aware load shedding.
    
    Adheres strictly to Section 6 (High-Frequency Buffer), Section 7 (Priority),
    and Section 69 (Load Shedding).
    """

    def __init__(
        self,
        max_capacity: int = 10000,
        high_watermark: float = 0.8,
        critical_watermark: float = 0.95,
    ):
        self.max_capacity = max_capacity
        self.high_watermark = int(max_capacity * high_watermark)
        self.critical_watermark = int(max_capacity * critical_watermark)

        self._high_queue: Deque[TickEvent] = deque()
        self._medium_queue: Deque[TickEvent] = deque()
        self._low_queue: Deque[TickEvent] = deque()

        # Telemetry
        self.total_published: int = 0
        self.total_consumed: int = 0
        self.dropped_low: int = 0
        self.dropped_medium: int = 0
        self.dropped_high: int = 0

    @property
    def depth(self) -> int:
        """Total number of queued events across all priority levels."""
        return len(self._high_queue) + len(self._medium_queue) + len(self._low_queue)

    @property
    def is_overloaded(self) -> bool:
        """Check if buffer is operating above the high watermark."""
        return self.depth >= self.high_watermark

    def publish(self, event: TickEvent) -> bool:
        """Enqueue an event according to its priority level with load-shedding."""
        self.total_published += 1
        current_depth = self.depth

        # Load Shedding Tier 1: Shed LOW priority events if above high watermark
        if current_depth >= self.high_watermark and event.priority == EventPriority.LOW:
            self.dropped_low += 1
            return False

        # Load Shedding Tier 2: Shed MEDIUM priority events if above critical watermark
        if current_depth >= self.critical_watermark and event.priority == EventPriority.MEDIUM:
            self.dropped_medium += 1
            return False

        # Load Shedding Tier 3: Emergency buffer overflow for HIGH priority
        if current_depth >= self.max_capacity:
            # Shed from lowest available queue first
            if self._low_queue:
                self._low_queue.popleft()
                self.dropped_low += 1
            elif self._medium_queue:
                self._medium_queue.popleft()
                self.dropped_medium += 1
            else:
                # Emergency overflow
                self.dropped_high += 1
                logger.error("emergency_buffer_overflow_dropped_high", symbol=event.symbol)
                return False

        # Enqueue to the appropriate priority queue
        if event.priority == EventPriority.HIGH:
            self._high_queue.append(event)
        elif event.priority == EventPriority.MEDIUM:
            self._medium_queue.append(event)
        else:
            self._low_queue.append(event)

        return True

    def consume(self) -> TickEvent | None:
        """Dequeue the next event in strict priority order (HIGH -> MEDIUM -> LOW)."""
        if self._high_queue:
            self.total_consumed += 1
            return self._high_queue.popleft()
        if self._medium_queue:
            self.total_consumed += 1
            return self._medium_queue.popleft()
        if self._low_queue:
            self.total_consumed += 1
            return self._low_queue.popleft()
        return None

    def consume_batch(self, max_batch_size: int = 100) -> list[TickEvent]:
        """Consume a batch of events up to max_batch_size."""
        batch = []
        while len(batch) < max_batch_size:
            event = self.consume()
            if not event:
                break
            batch.append(event)
        return batch

    def health(self) -> dict:
        """Return real-time buffer diagnostics."""
        current_depth = self.depth
        return {
            "capacity": self.max_capacity,
            "depth": current_depth,
            "utilization_percent": round((current_depth / self.max_capacity) * 100, 1),
            "is_overloaded": self.is_overloaded,
            "total_published": self.total_published,
            "total_consumed": self.total_consumed,
            "dropped_low": self.dropped_low,
            "dropped_medium": self.dropped_medium,
            "dropped_high": self.dropped_high,
            "total_dropped": self.dropped_low + self.dropped_medium + self.dropped_high,
        }


event_buffer = MarketEventBuffer()
