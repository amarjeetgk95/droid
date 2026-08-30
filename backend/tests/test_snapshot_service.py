import pytest
import os
from pathlib import Path
from app.services.snapshot_service import SnapshotService


class TestSnapshotService:
    @pytest.mark.asyncio
    async def test_save_and_load_snapshot(self, tmp_path: Path):
        test_file = tmp_path / "test_snapshot.json"
        service = SnapshotService(snapshot_path=str(test_file), interval_seconds=10)

        saved = await service.save_snapshot()
        assert saved is True
        assert test_file.exists()

        snapshot = service.load_snapshot()
        assert snapshot is not None
        assert len(snapshot.quotes) > 0
        assert service.is_warm_started is True
