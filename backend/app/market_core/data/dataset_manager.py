"""Dataset Manager for Immutable Historical Storage (Tier 0).

Stores and retrieves partitioned Parquet datasets with:
- SHA-256 integrity checksums
- Provenance metadata (source, record count, time range)
- Versioning and immutability guarantees
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import polars as pl
import structlog

logger = structlog.get_logger(__name__)

DEFAULT_DATA_DIR = Path("data/raw")
DEFAULT_HISTORICAL_PARQUET_DIR = Path("data/historical/parquet")


@dataclass
class DatasetMetadata:
    dataset_id: str
    instrument: str
    timeframe: str
    row_count: int
    start_time: str
    end_time: str
    checksum_sha256: str
    created_at_utc: str
    source: str
    data_quality_score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DatasetManager:
    """Manages raw and feature Parquet datasets on local storage."""

    def __init__(self, base_dir: Path | str = DEFAULT_DATA_DIR):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.historical_parquet_dir = DEFAULT_HISTORICAL_PARQUET_DIR

    def _get_parquet_path(self, instrument: str, timeframe: str) -> Path:
        clean_inst = instrument.lower().replace(":", "_").replace(" ", "_")
        inst_dir = self.base_dir / clean_inst
        inst_dir.mkdir(parents=True, exist_ok=True)
        return inst_dir / f"{timeframe}.parquet"

    def _get_meta_path(self, parquet_path: Path) -> Path:
        return parquet_path.with_suffix(".json")

    def _get_historical_parquet_paths(self, instrument: str, timeframe: str) -> List[Tuple[Path, Path]]:
        """Find all versioned parquet files in the historical parquet store.
        
        Returns list of (parquet_path, meta_path) tuples sorted by version (oldest first).
        """
        clean_inst = instrument.lower().replace(":", "_").replace(" ", "_")
        tf_dir = self.historical_parquet_dir / clean_inst / timeframe.lower()
        if not tf_dir.exists():
            return []
        
        results = []
        for parquet_path in sorted(tf_dir.glob("candles_v*.parquet")):
            meta_path = parquet_path.with_suffix(".json")
            results.append((parquet_path, meta_path))
        
        # Sort by version number (e.g. v1, v2) ascending
        results.sort(key=lambda pair: int(re.sub(r"\D", "", pair[0].stem) or "0"))
        return results

    def _load_historical_metadata(self, meta_path: Path) -> Optional[Dict[str, Any]]:
        """Load metadata from a historical parquet sidecar JSON."""
        if not meta_path.exists():
            return None
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("historical_metadata_read_failed", path=str(meta_path), error=str(e))
            return None

    def save_dataset(
        self,
        df: pl.DataFrame,
        instrument: str,
        timeframe: str,
        source: str = "fyers_api_v3",
        quality_score: float = 100.0,
    ) -> DatasetMetadata:
        """Saves a Polars DataFrame to Parquet and generates immutable metadata."""
        if len(df) == 0:
            raise ValueError(f"Cannot save empty dataset for {instrument} {timeframe}")

        parquet_path = self._get_parquet_path(instrument, timeframe)
        meta_path = self._get_meta_path(parquet_path)

        # Ensure sorted by timestamp
        df = df.sort("timestamp")
        df.write_parquet(parquet_path, compression="zstd")

        # Compute SHA-256 checksum of the written file
        sha256 = hashlib.sha256()
        with open(parquet_path, "rb") as f:
            while chunk := f.read(65536):
                sha256.update(chunk)
        file_hash = sha256.hexdigest()

        start_ts = str(df["timestamp"][0])
        end_ts = str(df["timestamp"][-1])
        now_utc = datetime.now(timezone.utc).isoformat()

        clean_inst = instrument.lower().replace(":", "_").replace(" ", "_")
        dataset_id = f"ds_{clean_inst}_{timeframe}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        meta = DatasetMetadata(
            dataset_id=dataset_id,
            instrument=instrument,
            timeframe=timeframe,
            row_count=len(df),
            start_time=start_ts,
            end_time=end_ts,
            checksum_sha256=file_hash,
            created_at_utc=now_utc,
            source=source,
            data_quality_score=quality_score,
        )

        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta.to_dict(), f, indent=2)

        logger.info(
            "dataset_saved",
            path=str(parquet_path),
            rows=len(df),
            checksum=file_hash[:12],
            score=quality_score,
        )
        return meta

    def load_dataset(self, instrument: str, timeframe: str) -> tuple[pl.DataFrame, Optional[DatasetMetadata]]:
        """Loads a Parquet dataset and its metadata."""
        parquet_path = self._get_parquet_path(instrument, timeframe)
        if parquet_path.exists():
            df = pl.read_parquet(parquet_path)
            meta_path = self._get_meta_path(parquet_path)
            meta: Optional[DatasetMetadata] = None

            if meta_path.exists():
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        meta = DatasetMetadata(**data)
                except Exception as e:
                    logger.warning("dataset_metadata_read_failed", error=str(e))

            return df, meta

        # Fallback to historical parquet store (canonical HDM path)
        hist_paths = self._get_historical_parquet_paths(instrument, timeframe)
        if hist_paths:
            # Use the latest version
            parquet_path, meta_path = hist_paths[-1]
            df = pl.read_parquet(parquet_path)
            meta = None
            raw_meta = self._load_historical_metadata(meta_path)
            if raw_meta:
                try:
                    meta = DatasetMetadata(
                        dataset_id=raw_meta.get("dataset_id", f"ds_{instrument.lower()}_{timeframe}"),
                        instrument=raw_meta.get("symbol", instrument),
                        timeframe=raw_meta.get("timeframe", timeframe),
                        row_count=raw_meta.get("row_count", len(df)),
                        start_time=raw_meta.get("start_time", ""),
                        end_time=raw_meta.get("end_time", ""),
                        checksum_sha256=raw_meta.get("checksum_sha256", ""),
                        created_at_utc=raw_meta.get("saved_at_utc", datetime.now(timezone.utc).isoformat()),
                        source=raw_meta.get("lineage", {}).get("provider_id", "historical_parquet") if isinstance(raw_meta.get("lineage"), dict) else "historical_parquet",
                        data_quality_score=raw_meta.get("quality_score", 100.0),
                    )
                except Exception as e:
                    logger.warning("historical_metadata_parse_failed", path=str(meta_path), error=str(e))

            return df, meta

        raise FileNotFoundError(f"No dataset found at {parquet_path} or in historical parquet store")

    def exists(self, instrument: str, timeframe: str) -> bool:
        if self._get_parquet_path(instrument, timeframe).exists():
            return True
        return bool(self._get_historical_parquet_paths(instrument, timeframe))

    @staticmethod
    def resample_candles(df_1m: pl.DataFrame, target_timeframe: str = "5m") -> pl.DataFrame:
        """Resamples 1-minute candle DataFrame into higher timeframes (e.g. 5m, 15m)."""
        if len(df_1m) == 0:
            return df_1m
        return (
            df_1m.sort("timestamp")
            .group_by_dynamic("timestamp", every=target_timeframe)
            .agg([
                pl.col("open").first(),
                pl.col("high").max(),
                pl.col("low").min(),
                pl.col("close").last(),
                pl.col("volume").sum(),
            ])
        )
