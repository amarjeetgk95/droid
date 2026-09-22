"""Tests for Storage Lifecycle, Atomic Writes, Checksums and Resampling."""

from datetime import datetime, timezone, timedelta
from pathlib import Path
import polars as pl
from app.historical_data.storage.lifecycle import write_parquet_atomic, calculate_file_sha256, cleanup_orphaned_tmp_files
from app.historical_data.storage.parquet_repository import HistoricalParquetRepository
from app.historical_data.services.aggregator_service import resample_1m_candles


def _sample_df(n: int = 15) -> pl.DataFrame:
    base_ts = datetime(2024, 6, 5, 3, 45, tzinfo=timezone.utc)
    ts_list = [base_ts + timedelta(minutes=i) for i in range(n)]

    return pl.DataFrame({
        "timestamp": pl.Series("timestamp", ts_list, dtype=pl.Datetime("ms", "UTC")),
        "symbol": ["SENSEX"] * n,
        "exchange": ["BSE"] * n,
        "asset_type": ["INDEX"] * n,
        "timeframe": ["1m"] * n,
        "open": [80000.0 + i for i in range(n)],
        "high": [80005.0 + i for i in range(n)],
        "low": [79995.0 + i for i in range(n)],
        "close": [80002.0 + i for i in range(n)],
        "volume": [0.0] * n,
        "provider": ["fyers"] * n,
        "ingestion_job_id": ["job_1"] * n,
        "data_version": ["v1"] * n,
    })


def test_atomic_write_and_sha256(tmp_path: Path):
    target_parquet = tmp_path / "test_candles.parquet"
    df = _sample_df(20)

    checksum = write_parquet_atomic(df, target_parquet)
    assert target_parquet.exists()
    assert len(checksum) == 64  # SHA-256 is 64 hex chars

    # Recompute check
    verified_hash = calculate_file_sha256(target_parquet)
    assert verified_hash == checksum


def test_orphan_tmp_cleanup(tmp_path: Path):
    # Create fake orphaned .tmp.parquet file
    fake_orphan = tmp_path / "candles.tmp.123.456.parquet"
    fake_orphan.write_bytes(b"dummy")

    # Run cleanup with older_than_hours=0 to prune immediately
    pruned = cleanup_orphaned_tmp_files(tmp_path, older_than_hours=0.0)
    assert pruned == 1
    assert not fake_orphan.exists()


def test_resampling_1m_to_5m():
    """Verify 15 1m candles resample to exactly three 5m candles."""
    df_1m = _sample_df(15)
    df_5m = resample_1m_candles(df_1m, "5m")

    assert len(df_5m) == 3
    # Check first 5m candle
    first_bar = df_5m.row(0, named=True)
    assert first_bar["timeframe"] == "5m"
    assert first_bar["open"] == 80000.0  # First 1m open
    assert first_bar["high"] == 80009.0  # Max of first five 1m highs
    assert first_bar["low"] == 79995.0   # Min of first five 1m lows
    assert first_bar["close"] == 80006.0 # Fifth 1m close


import pytest
from app.historical_data.storage.parquet_repository import parquet_repo
from app.historical_data.services.aggregator_service import derive_higher_timeframe_datasets

@pytest.mark.asyncio
async def test_derive_higher_timeframe_datasets(tmp_path: Path, monkeypatch):
    test_repo = HistoricalParquetRepository(base_dir=tmp_path)
    monkeypatch.setattr("app.historical_data.services.aggregator_service.parquet_repo", test_repo)

    # Save initial 1m dataset
    df_1m = _sample_df(30)
    test_repo.save_dataset_version(df_1m, "SENSEX", "1m", "v1")

    # Derive 5m and 15m
    derived = await derive_higher_timeframe_datasets("SENSEX", source_timeframe="1m", target_timeframes=["5m", "15m"])
    assert len(derived) == 2
    assert {d.timeframe for d in derived} == {"5m", "15m"}


@pytest.mark.asyncio
async def test_cold_start_disk_hydration(tmp_path: Path, monkeypatch):
    """Test that a completely new HistoricalDBRepository recovers datasets from disk on cold start."""
    from app.historical_data.storage.db_repository import HistoricalDBRepository

    monkeypatch.setattr("app.historical_data.storage.db_repository.get_async_session_factory", lambda: None)

    # 1. Create a parquet dataset on disk
    p_base = tmp_path / "parquet"
    repo = HistoricalParquetRepository(base_dir=p_base)
    df = _sample_df(25)
    repo.save_dataset_version(df, "SENSEX", "1m", "v1", quality_score=99.5)

    # 2. Instantiate a fresh DB repository pointing at tmp_path (simulating backend reboot)
    fresh_db = HistoricalDBRepository(base_dir=tmp_path)

    # 3. Verify datasets were discovered and hydrated
    datasets = await fresh_db.list_datasets()
    assert len(datasets) == 1
    ds = datasets[0]
    assert ds.symbol == "SENSEX"
    assert ds.timeframe == "1m"
    assert ds.total_candles == 25
    assert ds.latest_quality_score == 99.5
    assert ds.status == "READY"
    assert ds.storage_bytes > 0

    # 4. Verify catalog_manifest.json was created
    manifest = tmp_path / "catalog_manifest.json"
    assert manifest.exists()

    # 5. Verify versions list
    versions = await fresh_db.list_versions("SENSEX_1M")
    assert len(versions) == 1
    assert versions[0].version_tag == "v1"
