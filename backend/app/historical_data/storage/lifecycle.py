"""Storage Lifecycle Management: Atomic Writes, Orphan Pruning, and Pre-flight Checks."""

from __future__ import annotations
import hashlib
import os
import shutil
import time
from pathlib import Path
from typing import Optional
import polars as pl
import structlog
from app.historical_data.storage.paths import resolve_historical_data_dir

logger = structlog.get_logger(__name__)

DEFAULT_HISTORICAL_DATA_DIR = resolve_historical_data_dir()


def check_disk_space(required_mb: int = 1000, target_dir: Optional[Path] = None) -> bool:
    """Check if the filesystem has sufficient free space (default 1 GB)."""
    target = target_dir or DEFAULT_HISTORICAL_DATA_DIR
    target.mkdir(parents=True, exist_ok=True)
    try:
        total, used, free = shutil.disk_usage(target)
        free_mb = free / (1024 * 1024)
        if free_mb < required_mb:
            logger.error("insufficient_disk_space", free_mb=free_mb, required_mb=required_mb)
            return False
        return True
    except Exception as e:
        logger.warning("disk_space_check_failed", error=str(e))
        return True  # Fallback to allow execution if check fails


def calculate_file_sha256(file_path: Path) -> str:
    """Calculate the cryptographic SHA-256 hash of a file on disk."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def write_parquet_atomic(df: pl.DataFrame, target_path: Path) -> str:
    """Write DataFrame to Parquet atomically using a temporary file.
    
    Returns the SHA-256 checksum of the written file.
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_suffix(f".tmp.{os.getpid()}.{time.time_ns()}.parquet")

    try:
        # Write to temporary file with Snappy compression for analytical speed
        df.write_parquet(tmp_path, compression="snappy")

        # Verify readability before swapping
        verify_df = pl.read_parquet(tmp_path)
        if len(verify_df) != len(df):
            raise IOError(f"Parquet verification row mismatch: wrote {len(df)}, verified {len(verify_df)}")

        # Atomic rename
        if target_path.exists():
            # On Windows, replace handles existing destination atomically
            tmp_path.replace(target_path)
        else:
            tmp_path.rename(target_path)

        # Compute deterministic checksum
        return calculate_file_sha256(target_path)

    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass


def cleanup_orphaned_tmp_files(base_dir: Path = DEFAULT_HISTORICAL_DATA_DIR, older_than_hours: float = 2.0) -> int:
    """Remove orphaned temporary files (.tmp.*) left by interrupted processes."""
    if not base_dir.exists():
        return 0

    removed_count = 0
    cutoff_time = time.time() - (older_than_hours * 3600)

    for p in base_dir.rglob("*.tmp.*"):
        try:
            if p.is_file() and p.stat().st_mtime < cutoff_time:
                p.unlink()
                removed_count += 1
                logger.info("pruned_orphaned_tmp_file", path=str(p))
        except Exception as e:
            logger.warning("failed_to_prune_tmp_file", path=str(p), error=str(e))

    return removed_count
