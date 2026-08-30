from datetime import datetime, timezone
from app.services.event_buffer import MarketEventBuffer
from app.models.contracts import TickEvent, EventPriority


class TestMarketEventBuffer:
    def setup_method(self):
        self.buf = MarketEventBuffer(max_capacity=100, high_watermark=0.8, critical_watermark=0.9)

    def test_priority_ordering(self):
        # Enqueue in reverse priority
        low_tick = TickEvent(
            timestamp=datetime.now(timezone.utc),
            symbol="NIFTY 50",
            ltp=25000.0,
            priority=EventPriority.LOW,
        )
        med_tick = TickEvent(
            timestamp=datetime.now(timezone.utc),
            symbol="NIFTY 50",
            ltp=25001.0,
            priority=EventPriority.MEDIUM,
        )
        high_tick = TickEvent(
            timestamp=datetime.now(timezone.utc),
            symbol="NIFTY 50",
            ltp=25002.0,
            priority=EventPriority.HIGH,
        )

        self.buf.publish(low_tick)
        self.buf.publish(med_tick)
        self.buf.publish(high_tick)

        # Consumes in strict priority order: HIGH -> MEDIUM -> LOW
        c1 = self.buf.consume()
        c2 = self.buf.consume()
        c3 = self.buf.consume()

        assert c1 is not None and c1.priority == EventPriority.HIGH
        assert c2 is not None and c2.priority == EventPriority.MEDIUM
        assert c3 is not None and c3.priority == EventPriority.LOW

    def test_load_shedding_at_high_watermark(self):
        # Fill up to 80 items (high watermark)
        for i in range(80):
            self.buf.publish(TickEvent(
                timestamp=datetime.now(timezone.utc),
                symbol="NIFTY 50",
                ltp=25000.0 + i,
                priority=EventPriority.HIGH,
            ))

        assert self.buf.depth == 80
        assert self.buf.is_overloaded is True

        # Next LOW priority tick should be shed
        low_tick = TickEvent(
            timestamp=datetime.now(timezone.utc),
            symbol="NIFTY 50",
            ltp=25100.0,
            priority=EventPriority.LOW,
        )
        accepted = self.buf.publish(low_tick)
        assert accepted is False
        assert self.buf.dropped_low == 1

        # HIGH priority tick should still be accepted
        high_tick = TickEvent(
            timestamp=datetime.now(timezone.utc),
            symbol="NIFTY 50",
            ltp=25101.0,
            priority=EventPriority.HIGH,
        )
        accepted_high = self.buf.publish(high_tick)
        assert accepted_high is True
        assert self.buf.depth == 81
