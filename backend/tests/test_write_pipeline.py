import pytest
import asyncio
from datetime import datetime, timezone
from app.services.write_pipeline import TickDeduplicator, BatchWritePipeline
from app.models.contracts import TickEvent, EventPriority


class TestWritePipeline:
    def test_tick_deduplication(self):
        dedup = TickDeduplicator(max_history=100, window_seconds=10.0)
        now = datetime.now(timezone.utc)

        t1 = TickEvent(
            timestamp=now,
            symbol="NIFTY 50",
            ltp=25000.0,
            volume=1000,
            sequence_number=101,
        )
        # Duplicate tick with exact same attributes
        t2 = TickEvent(
            timestamp=now,
            symbol="NIFTY 50",
            ltp=25000.0,
            volume=1000,
            sequence_number=101,
        )

        assert dedup.is_duplicate(t1) is False
        assert dedup.is_duplicate(t2) is True
        assert dedup.duplicates_dropped == 1

    @pytest.mark.asyncio
    async def test_batch_write_pipeline_flush(self):
        pipeline = BatchWritePipeline(batch_size=5, flush_interval_ms=50)
        await pipeline.start()

        now = datetime.now(timezone.utc)
        for i in range(10):
            await pipeline.enqueue_tick(TickEvent(
                timestamp=now,
                symbol="NIFTY 50",
                ltp=25000.0 + i,
                volume=100 + i,
                sequence_number=i,
            ))

        # Allow micro-batch worker to flush
        await asyncio.sleep(0.12)
        await pipeline.stop()

        stats = pipeline.get_stats()
        assert stats["total_enqueued"] == 10
        assert stats["total_flushed"] == 10
        assert stats["total_batches"] >= 2
