"""High-Performance Columnar Parquet Repository for Normalized Historical Candles."""

from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import polars as pl
import structlog

from app.historical_data.storage.lifecycle import write_parquet_atomic, calculate_file_sha256
from app.historical_data.models.dataset import LineageMetadata, MethodologyEvent

from app.historical_data.storage.paths import resolve_historical_data_dir

logger = structlog.get_logger(__name__)

DEFAULT_PARQUET_BASE_DIR = resolve_historical_data_dir() / "parquet"


class HistoricalParquetRepository:
    """Manages reading and writing canonical historical candles using Polars and Parquet."""

    def __init__(self, base_dir: Optional[Path | str] = None):
        self.base_dir = Path(base_dir) if base_dir is not None else DEFAULT_PARQUET_BASE_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_dataset_dir(self, symbol: str, timeframe: str) -> Path:
        clean_sym = symbol.lower().replace(":", "_").replace(" ", "_").replace("-", "_")
        clean_tf = timeframe.lower()
        d = self.base_dir / clean_sym / clean_tf
        d.mkdir(parents=True, exist_ok=True)
        return d

    def get_parquet_path(self, symbol: str, timeframe: str, version_tag: str = "v1") -> Path:
        """Construct deterministic file path for a versioned dataset."""
        d = self._get_dataset_dir(symbol, timeframe)
        return d / f"candles_{version_tag}.parquet"

    def get_meta_path(self, parquet_path: Path) -> Path:
        return parquet_path.with_suffix(".json")

    def save_dataset_version(
        self,
        df: pl.DataFrame,
        symbol: str,
        timeframe: str,
        version_tag: str,
        lineage: Optional[LineageMetadata] = None,
        methodology_events: Optional[List[MethodologyEvent]] = None,
        quality_score: float = 100.0,
    ) -> Tuple[Path, str]:
        """Save normalized historical candles to disk atomically and generate SHA-256 sidecar.
        
        Returns (parquet_file_path, sha256_checksum).
        """
        if df.is_empty():
            raise ValueError(f"Cannot save empty DataFrame for {symbol} {timeframe}")

        parquet_path = self.get_parquet_path(symbol, timeframe, version_tag)
        checksum = write_parquet_atomic(df, parquet_path)

        min_ts = df["timestamp"].min()
        max_ts = df["timestamp"].max()

        sidecar_meta = {
            "symbol": symbol,
            "timeframe": timeframe,
            "version_tag": version_tag,
            "row_count": len(df),
            "start_time": min_ts.isoformat() if min_ts else None,
            "end_time": max_ts.isoformat() if max_ts else None,
            "checksum_sha256": checksum,
            "quality_score": quality_score,
            "lineage": lineage.model_dump(mode="json") if lineage else LineageMetadata().model_dump(mode="json"),
            "methodology_events": [e.model_dump(mode="json") for e in (methodology_events or [])],
            "saved_at_utc": datetime.now(timezone.utc).isoformat(),
        }

        meta_path = self.get_meta_path(parquet_path)
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(sidecar_meta, f, indent=2)

        logger.info(
            "historical_dataset_saved",
            symbol=symbol,
            timeframe=timeframe,
            version=version_tag,
            rows=len(df),
            checksum=checksum[:12],
            path=str(parquet_path),
        )
        return parquet_path, checksum

    def load_candles(
        self,
        symbol: str,
        timeframe: str,
        version_tag: str = "v1",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> pl.DataFrame:
        """Load candles with optional point-in-time time range filtering."""
        parquet_path = self.get_parquet_path(symbol, timeframe, version_tag)
        if not parquet_path.exists():
            raise FileNotFoundError(f"Historical dataset not found on disk: {parquet_path}")

        # Use lazy scan for zero-copy memory efficiency
        lf = pl.scan_parquet(parquet_path)

        if start_time is not None:
            # Ensure UTC comparison
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=timezone.utc)
            lf = lf.filter(pl.col("timestamp") >= start_time)

        if end_time is not None:
            if end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=timezone.utc)
            # Strict point-in-time upper bound
            lf = lf.filter(pl.col("timestamp") <= end_time)

        return lf.sort("timestamp").collect()

    def get_paginated_candles(
        self,
        symbol: str,
        timeframe: str,
        version_tag: str = "v1",
        page: int = 1,
        page_size: int = 100,
        sort_desc: bool = True,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Fetch server-paginated candle list for UI Candle Inspector.
        
        Returns (rows, total_count).
        """
        parquet_path = self.get_parquet_path(symbol, timeframe, version_tag)
        if not parquet_path.exists():
            return [], 0

        lf = pl.scan_parquet(parquet_path)
        if start_time:
            lf = lf.filter(pl.col("timestamp") >= start_time)
        if end_time:
            lf = lf.filter(pl.col("timestamp") <= end_time)

        total_count = lf.select(pl.len()).collect().item()

        lf = lf.sort("timestamp", descending=sort_desc)
        offset = max(0, (page - 1) * page_size)
        rows_df = lf.slice(offset, page_size).collect()

        # Convert to dictionary format
        return rows_df.to_dicts(), total_count


# Global repository instance
parquet_repo = HistoricalParquetRepository()
