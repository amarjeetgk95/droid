import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from app.models.timeseries import SnapshotPayload
from app.core.config import settings
import structlog

logger = structlog.get_logger()


class SnapshotService:
    """Snapshot Persistence and Cold-Start Recovery Service.
    
    Adheres strictly to Section 25 (Snapshot Persistence).
    Periodically serializes market state to disk and restores state
    instantly on server cold restart.
    """

    def __init__(self, snapshot_path: str | None = None, interval_seconds: int = 60):
        self.snapshot_path = Path(snapshot_path or settings.snapshot_file_path)
        self.interval_seconds = interval_seconds
        self._running: bool = False
        self._worker_task: asyncio.Task | None = None

        # Telemetry
        self.total_saved: int = 0
        self.last_saved_at: datetime | None = None
        self.is_warm_started: bool = False

    async def start(self) -> None:
        """Start the periodic snapshot background loop."""
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._snapshot_loop())
        logger.info("snapshot_service_started", path=str(self.snapshot_path))

    async def stop(self) -> None:
        """Gracefully stop and persist final shutdown snapshot."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        # Final persistence snapshot on shutdown
        await self.save_snapshot()
        logger.info("snapshot_service_stopped")

    async def save_snapshot(self) -> bool:
        """Capture current market state and persist to disk."""
        try:
            from app.providers.registry import get_provider
            from app.services.central_feed import central_feed

            provider = get_provider()
            quotes = await provider.get_quotes()
            cards = await provider.get_index_cards()
            status = await provider.get_market_status()
            breadth = await provider.get_market_breadth()

            payload = SnapshotPayload(
                timestamp=datetime.now(timezone.utc),
                quotes=[q.model_dump(mode="json") for q in quotes],
                cards=[c.model_dump(mode="json") for c in cards],
                status=status.model_dump(mode="json"),
                breadth=breadth.model_dump(mode="json"),
                subscriptions=central_feed.get_subscriptions(),
            )

            # Atomic write via temporary file
            temp_path = self.snapshot_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(payload.model_dump(mode="json"), f, indent=2)

            if os.path.exists(temp_path):
                if os.path.exists(self.snapshot_path):
                    os.replace(temp_path, self.snapshot_path)
                else:
                    os.rename(temp_path, self.snapshot_path)

            self.total_saved += 1
            self.last_saved_at = datetime.now(timezone.utc)
            return True
        except Exception as e:
            logger.error("snapshot_save_failed", error=str(e))
            return False

    def load_snapshot(self) -> SnapshotPayload | None:
        """Load latest persisted snapshot from disk."""
        if not self.snapshot_path.exists():
            return None

        try:
            with open(self.snapshot_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            snapshot = SnapshotPayload(**data)
            self.is_warm_started = True
            logger.info("snapshot_restored_successfully", timestamp=snapshot.timestamp.isoformat())
            return snapshot
        except Exception as e:
            logger.warning("snapshot_load_failed", error=str(e))
            return None

    async def _snapshot_loop(self) -> None:
        """Periodic background snapshot loop."""
        while self._running:
            try:
                await asyncio.sleep(self.interval_seconds)
                await self.save_snapshot()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("snapshot_loop_error", error=str(e))

    def get_stats(self) -> dict:
        return {
            "snapshot_file": str(self.snapshot_path),
            "file_exists": self.snapshot_path.exists(),
            "total_saved": self.total_saved,
            "last_saved_at": self.last_saved_at.isoformat() if self.last_saved_at else None,
            "is_warm_started": self.is_warm_started,
        }


snapshot_service = SnapshotService(
    snapshot_path=settings.snapshot_file_path,
    interval_seconds=settings.snapshot_interval_seconds,
)
