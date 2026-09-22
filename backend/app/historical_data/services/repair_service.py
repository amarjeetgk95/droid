"""Gap Repair Service: Targeted Re-query with Upstream Omission Escalation."""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import polars as pl
import structlog

from app.historical_data.models.gap import DataGap
from app.historical_data.storage.db_repository import db_repo
from app.historical_data.storage.parquet_repository import parquet_repo
from app.historical_data.providers.fyers import FYERSHistoricalProvider
from app.historical_data.validation.quality_engine import quality_engine

logger = structlog.get_logger(__name__)


class HistoricalRepairService:
    """Repairs detected data gaps by targeting specific missing trading sessions."""

    def __init__(self, provider: Optional[FYERSHistoricalProvider] = None):
        self.provider = provider or FYERSHistoricalProvider()

    async def repair_gap(self, gap_id: str) -> DataGap:
        """Attempt to repair an individual session gap."""
        # Search across all dataset gaps
        target_gap: Optional[DataGap] = None
        target_dataset_id: Optional[str] = None

        datasets = await db_repo.list_datasets()
        for d in datasets:
            gaps = await db_repo.list_gaps(d.id)
            for g in gaps:
                if g.gap_id == gap_id:
                    target_gap = g
                    target_dataset_id = d.id
                    break
            if target_gap:
                break

        if not target_gap or not target_dataset_id:
            raise ValueError(f"Gap not found: {gap_id}")

        target_gap.status = "REPAIRING"
        target_gap.repair_attempts += 1
        target_gap.last_repair_attempt = datetime.now(timezone.utc)
        await db_repo.save_gap(target_gap)

        dataset = await db_repo.get_dataset(target_dataset_id)
        if not dataset:
            target_gap.status = "OPEN"
            await db_repo.save_gap(target_gap)
            raise ValueError(f"Dataset not found: {target_dataset_id}")

        logger.info(
            "attempting_gap_repair",
            gap_id=gap_id,
            symbol=dataset.symbol,
            trading_date=target_gap.trading_date.isoformat(),
            attempt=target_gap.repair_attempts,
        )

        # Call provider specifically for the missing date
        try:
            repaired_df = await self.provider.fetch_candles(
                symbol=dataset.symbol,
                timeframe=dataset.timeframe,
                start_date=target_gap.trading_date,
                end_date=target_gap.trading_date,
            )

            if repaired_df.is_empty():
                # Provider has no data either
                if target_gap.repair_attempts >= 2:
                    target_gap.status = "UNREPAIRABLE_UPSTREAM_OMISSION"
                    target_gap.notes = "Upstream provider confirmed 0 candles available for this session date."
                    logger.warning("gap_unrepairable_upstream", gap_id=gap_id, date=target_gap.trading_date.isoformat())
                else:
                    target_gap.status = "OPEN"
                    target_gap.notes = "Provider returned empty response on repair attempt."
                await db_repo.save_gap(target_gap)
                return target_gap

            # Data returned! Merge into existing dataset
            existing_df = parquet_repo.load_candles(dataset.symbol, dataset.timeframe)
            merged_df = pl.concat([existing_df, repaired_df]).unique(subset=["symbol", "timeframe", "timestamp"]).sort("timestamp")

            # Validate merged dataset
            report = quality_engine.validate_dataset(
                df=merged_df,
                symbol=dataset.symbol,
                timeframe=dataset.timeframe,
                asset_type=dataset.asset_type,
                start_date=merged_df["timestamp"].min().date(),
                end_date=merged_df["timestamp"].max().date(),
                dataset_id=dataset.id,
            )
            await db_repo.save_quality_report(report)

            # Save new version
            version_count = len(await db_repo.list_versions(dataset.id))
            version_tag = f"v{version_count + 1}"

            parquet_path, checksum = parquet_repo.save_dataset_version(
                df=merged_df,
                symbol=dataset.symbol,
                timeframe=dataset.timeframe,
                version_tag=version_tag,
                quality_score=report.quality_score,
            )

            target_gap.status = "RESOLVED"
            target_gap.notes = f"Repaired with {len(repaired_df)} candles from provider."
            await db_repo.save_gap(target_gap)

            dataset.current_version_id = f"{dataset.id}_{version_tag}"
            dataset.total_candles = len(merged_df)
            dataset.latest_quality_score = report.quality_score
            await db_repo.upsert_dataset(dataset)

            logger.info("gap_repaired_successfully", gap_id=gap_id, new_rows=len(repaired_df))
            return target_gap

        except Exception as e:
            logger.error("gap_repair_failed", gap_id=gap_id, error=str(e))
            target_gap.status = "OPEN"
            target_gap.notes = f"Repair error: {str(e)}"
            await db_repo.save_gap(target_gap)
            return target_gap


# Global repair service instance
repair_service = HistoricalRepairService()
