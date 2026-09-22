"""Deterministic Timeframe Resampling Engine (1m -> 5m, 15m, 30m, 1h, 1D).

Adheres strictly to point-in-time rules and zero lookahead bias:
- Open  = first 1m open in interval
- High  = maximum high in interval
- Low   = minimum low in interval
- Close = last 1m close in interval
- Volume = sum of volumes
- Bar timestamp = start of interval (e.g. 09:15 for the [09:15, 09:20) 5m bar).
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import polars as pl
import structlog

from app.historical_data.storage.parquet_repository import parquet_repo
from app.historical_data.storage.db_repository import db_repo
from app.historical_data.models.dataset import HistoricalDataset, HistoricalDatasetVersion, LineageMetadata
from app.historical_data.validation.quality_engine import quality_engine

logger = structlog.get_logger(__name__)

TIMEFRAME_DELTAS = {
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "60m": "1h",
    "1h": "1h",
    "1d": "1d",
    "d": "1d",
}


def resample_1m_candles(df_1m: pl.DataFrame, target_timeframe: str) -> pl.DataFrame:
    """Resample 1-minute candle DataFrame to a target timeframe.
    
    Expects df_1m to have columns: timestamp, symbol, exchange, asset_type, open, high, low, close, volume.
    """
    if df_1m.is_empty():
        return df_1m

    tf_lower = target_timeframe.lower()
    if tf_lower in ("1m", "1", "1min"):
        return df_1m

    every_str = TIMEFRAME_DELTAS.get(tf_lower)
    if not every_str:
        raise ValueError(f"Unsupported target timeframe for resampling: {target_timeframe}")

    # Ensure sorted by timestamp
    df = df_1m.sort("timestamp")

    # Dynamic group by window
    resampled = (
        df.group_by_dynamic(
            "timestamp",
            every=every_str,
            closed="left",
            label="left",
        )
        .agg([
            pl.col("symbol").first().alias("symbol"),
            pl.col("exchange").first().alias("exchange"),
            pl.col("asset_type").first().alias("asset_type"),
            pl.lit(target_timeframe).alias("timeframe"),
            pl.col("open").first().alias("open"),
            pl.col("high").max().alias("high"),
            pl.col("low").min().alias("low"),
            pl.col("close").last().alias("close"),
            pl.col("volume").sum().alias("volume"),
            pl.col("provider").first().alias("provider"),
            pl.col("ingestion_job_id").first().alias("ingestion_job_id"),
            pl.col("data_version").first().alias("data_version"),
        ])
        .filter(pl.col("open").is_not_null())
        .sort("timestamp")
    )

    return resampled


async def derive_higher_timeframe_datasets(
    symbol: str,
    source_timeframe: str = "1m",
    target_timeframes: Optional[List[str]] = None,
) -> List[HistoricalDataset]:
    """Automatically resample an existing 1m dataset into higher timeframes and register them."""
    if target_timeframes is None:
        target_timeframes = ["5m", "15m", "30m", "1h", "1D"]

    try:
        df_1m = parquet_repo.load_candles(symbol, source_timeframe)
    except Exception as e:
        logger.error("derive_failed_source_not_found", symbol=symbol, source_tf=source_timeframe, error=str(e))
        return []

    if df_1m.is_empty():
        return []

    derived_datasets: List[HistoricalDataset] = []
    min_ts = df_1m["timestamp"].min()
    max_ts = df_1m["timestamp"].max()

    exchange = df_1m["exchange"][0] if "exchange" in df_1m.columns else "BSE"
    asset_type = df_1m["asset_type"][0] if "asset_type" in df_1m.columns else "INDEX"

    for tf in target_timeframes:
        if tf.lower() in ("1m", "1", "1min"):
            continue

        try:
            resampled_df = resample_1m_candles(df_1m, tf)
            if resampled_df.is_empty():
                continue

            dataset_id = f"{symbol.upper()}_{tf.upper()}"
            version_count = len(await db_repo.list_versions(dataset_id))
            version_tag = f"v{version_count + 1}"

            # Validate resampled dataset
            report = quality_engine.validate_dataset(
                df=resampled_df,
                symbol=symbol,
                timeframe=tf,
                asset_type=asset_type,
                start_date=min_ts.date(),
                end_date=max_ts.date(),
                dataset_id=dataset_id,
            )
            await db_repo.save_quality_report(report)

            parquet_path, checksum = parquet_repo.save_dataset_version(
                df=resampled_df,
                symbol=symbol,
                timeframe=tf,
                version_tag=version_tag,
                lineage=LineageMetadata(
                    engine_version="1.0.0",
                    provider_id=f"derived_from_{source_timeframe}",
                ),
                quality_score=report.quality_score,
            )

            version_rec = HistoricalDatasetVersion(
                version_id=f"{dataset_id}_{version_tag}",
                dataset_id=dataset_id,
                version_tag=version_tag,
                start_time=min_ts,
                end_time=max_ts,
                row_count=len(resampled_df),
                checksum_sha256=checksum,
                quality_score=report.quality_score,
                quality_status=report.status,
                parquet_path=str(parquet_path),
            )
            await db_repo.create_version(version_rec)

            dataset = HistoricalDataset(
                id=dataset_id,
                symbol=symbol.upper(),
                exchange=exchange,
                asset_type=asset_type,
                timeframe=tf,
                provider="derived",
                status="READY" if report.hard_gates_passed else "DEGRADED",
                current_version_id=version_rec.version_id,
                earliest_available_ts=min_ts,
                latest_available_ts=max_ts,
                total_candles=len(resampled_df),
                latest_quality_score=report.quality_score,
                storage_bytes=parquet_path.stat().st_size if parquet_path.exists() else 0,
                parquet_relative_path=str(parquet_path),
                metadata={"derived_from": source_timeframe, "resampled_at": datetime.now(timezone.utc).isoformat()},
            )
            await db_repo.upsert_dataset(dataset)
            derived_datasets.append(dataset)
            logger.info("derived_timeframe_dataset_created", dataset_id=dataset_id, rows=len(resampled_df))
        except Exception as err:
            logger.error("failed_to_derive_timeframe", symbol=symbol, tf=tf, error=str(err))

    return derived_datasets
