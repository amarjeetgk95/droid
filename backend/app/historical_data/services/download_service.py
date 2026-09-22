"""Historical Download Service: Asynchronous Job Execution, Chunk Pipeline & Version Creation."""

from __future__ import annotations
import asyncio
from datetime import date, datetime, timezone
from typing import Optional, Dict, Any, List
import polars as pl
import structlog

from app.historical_data.models.job import HistoricalDownloadJob, HistoricalDownloadChunk
from app.historical_data.models.dataset import HistoricalDataset, HistoricalDatasetVersion, LineageMetadata
from app.historical_data.providers.fyers import FYERSHistoricalProvider, split_date_range
from app.historical_data.storage.lifecycle import check_disk_space
from app.historical_data.storage.parquet_repository import parquet_repo
from app.historical_data.storage.db_repository import db_repo
from app.historical_data.validation.quality_engine import quality_engine
from app.historical_data.validation.gap_detector import gap_detector
from app.historical_data.services.aggregator_service import derive_higher_timeframe_datasets

logger = structlog.get_logger(__name__)


class HistoricalDownloadService:
    """Manages asynchronous download jobs, chunk execution, validation, and versioning."""

    def __init__(self, provider: Optional[FYERSHistoricalProvider] = None):
        self.provider = provider or FYERSHistoricalProvider()
        self._active_tasks: Dict[str, asyncio.Task] = {}

    async def cancel_job(self, job_id: str) -> Optional[HistoricalDownloadJob]:
        """Cancel an in-flight or queued job."""
        task = self._active_tasks.pop(job_id, None)
        if task and not task.done():
            task.cancel()

        job = await db_repo.get_job(job_id)
        if job:
            job.status = "CANCELLED"
            job.error_message = "Cancelled by user"
            job.completed_at = datetime.now(timezone.utc)
            for c in job.chunks:
                if c.status in ("PENDING", "DOWNLOADING"):
                    c.status = "CANCELLED"
            await db_repo.save_job(job)
        return job

    async def delete_job(self, job_id: str) -> bool:
        """Cancel if running and remove from database and manifest."""
        await self.cancel_job(job_id)
        return await db_repo.delete_job(job_id)

    async def enqueue_download(
        self,
        symbol: str,
        timeframe: str,
        start_date: date,
        end_date: date,
        force_refresh: bool = False,
    ) -> HistoricalDownloadJob:
        """Create and enqueue a background historical download job."""
        if not check_disk_space(required_mb=500):
            raise IOError("Insufficient disk space to enqueue historical download")

        sym_upper = symbol.strip().upper()
        dataset_id = f"{sym_upper}_{timeframe.upper()}"
        job_id = f"job_{sym_upper}_{timeframe}_{int(datetime.now(timezone.utc).timestamp())}"

        # Ensure dataset catalog entry exists
        exchange = "BSE" if "BSE" in self.provider.resolve_provider_symbol(sym_upper) else "NSE"
        asset_type = "INDEX" if sym_upper in ("SENSEX", "NIFTY", "BANKNIFTY", "FINNIFTY", "INDIAVIX") else "EQUITY"

        dataset = await db_repo.get_dataset(dataset_id)
        if not dataset:
            dataset = HistoricalDataset(
                id=dataset_id,
                symbol=sym_upper,
                exchange=exchange,
                asset_type=asset_type,
                timeframe=timeframe,
                provider=self.provider.provider_id,
                status="INITIALIZED",
            )
            await db_repo.upsert_dataset(dataset)

        # Split range into chunks
        date_chunks = split_date_range(start_date, end_date)
        chunks: List[HistoricalDownloadChunk] = []
        for i, (c_start, c_end) in enumerate(date_chunks):
            chunks.append(HistoricalDownloadChunk(
                chunk_id=f"{job_id}_c{i}",
                job_id=job_id,
                chunk_index=i,
                range_from=c_start,
                range_to=c_end,
                status="PENDING",
            ))

        job = HistoricalDownloadJob(
            job_id=job_id,
            dataset_id=dataset_id,
            symbol=sym_upper,
            timeframe=timeframe,
            provider=self.provider.provider_id,
            range_from=start_date,
            range_to=end_date,
            status="QUEUED",
            total_chunks=len(chunks),
            chunks=chunks,
        )
        await db_repo.save_job(job)

        # Track and fire background worker
        task = asyncio.create_task(self._run_job_pipeline(job, force_refresh))
        self._active_tasks[job_id] = task
        task.add_done_callback(lambda _: self._active_tasks.pop(job_id, None))
        return job

    async def _run_job_pipeline(self, job: HistoricalDownloadJob, force_refresh: bool) -> None:
        """Internal asynchronous pipeline running chunks, quality checks and storage."""
        logger.info("historical_job_started", job_id=job.job_id, symbol=job.symbol, chunks=job.total_chunks)
        job.status = "RUNNING"
        job.started_at = datetime.now(timezone.utc)
        await db_repo.save_job(job)

        all_chunk_dfs: List[pl.DataFrame] = []

        try:
            for i, chunk in enumerate(job.chunks):
                chunk.status = "DOWNLOADING"
                chunk.started_at = datetime.now(timezone.utc)
                await db_repo.save_job(job)

                try:
                    df_chunk = await self.provider.fetch_candles(
                        symbol=job.symbol,
                        timeframe=job.timeframe,
                        start_date=chunk.range_from,
                        end_date=chunk.range_to,
                        job_id=job.job_id,
                    )
                    chunk.rows_fetched = len(df_chunk)
                    chunk.status = "COMPLETED"
                    chunk.completed_at = datetime.now(timezone.utc)
                    all_chunk_dfs.append(df_chunk)
                    job.completed_chunks += 1
                    job.rows_downloaded += len(df_chunk)
                    job.progress_pct = round((job.completed_chunks / max(1, job.total_chunks)) * 100.0, 1)
                    await db_repo.save_job(job)
                except Exception as chunk_err:
                    chunk.status = "FAILED"
                    chunk.error_message = str(chunk_err)
                    logger.error("chunk_download_failed", chunk_id=chunk.chunk_id, error=str(chunk_err))
                    await db_repo.save_job(job)

            # Combine downloaded chunks
            valid_dfs = [df for df in all_chunk_dfs if not df.is_empty()]
            if not valid_dfs:
                job.status = "COMPLETED"
                job.completed_at = datetime.now(timezone.utc)
                job.error_message = "No data returned by provider for requested date range"
                await db_repo.save_job(job)
                return

            new_df = pl.concat(valid_dfs).unique(subset=["symbol", "timeframe", "timestamp"]).sort("timestamp")

            # If incremental and not force_refresh, merge with existing disk parquet if exists
            final_df = new_df
            if not force_refresh:
                try:
                    existing_df = parquet_repo.load_candles(job.symbol, job.timeframe)
                    if not existing_df.is_empty():
                        final_df = pl.concat([existing_df, new_df]).unique(subset=["symbol", "timeframe", "timestamp"]).sort("timestamp")
                except Exception:
                    pass

            job.rows_valid = len(final_df)

            # Run Quality Engine
            dataset = await db_repo.get_dataset(job.dataset_id)
            asset_type = dataset.asset_type if dataset else "INDEX"

            report = quality_engine.validate_dataset(
                df=final_df,
                symbol=job.symbol,
                timeframe=job.timeframe,
                asset_type=asset_type,
                start_date=job.range_from,
                end_date=job.range_to,
                dataset_id=job.dataset_id,
            )
            await db_repo.save_quality_report(report)

            # Run Gap Detector
            gaps = gap_detector.detect_gaps(
                df=final_df,
                dataset_id=job.dataset_id,
                start_date=job.range_from,
                end_date=job.range_to,
                timeframe=job.timeframe,
            )
            for g in gaps:
                await db_repo.save_gap(g)

            # Versioning
            version_count = len(await db_repo.list_versions(job.dataset_id))
            version_tag = f"v{version_count + 1}"

            parquet_path, checksum = parquet_repo.save_dataset_version(
                df=final_df,
                symbol=job.symbol,
                timeframe=job.timeframe,
                version_tag=version_tag,
                lineage=LineageMetadata(
                    engine_version="1.0.0",
                    provider_id=self.provider.provider_id,
                ),
                quality_score=report.quality_score,
            )

            min_ts = final_df["timestamp"].min()
            max_ts = final_df["timestamp"].max()

            version_rec = HistoricalDatasetVersion(
                version_id=f"{job.dataset_id}_{version_tag}",
                dataset_id=job.dataset_id,
                version_tag=version_tag,
                start_time=min_ts,
                end_time=max_ts,
                row_count=len(final_df),
                checksum_sha256=checksum,
                quality_score=report.quality_score,
                quality_status=report.status,
                parquet_path=str(parquet_path),
            )
            await db_repo.create_version(version_rec)

            # Update Dataset Catalog
            if dataset:
                dataset.current_version_id = version_rec.version_id
                dataset.status = "READY" if report.hard_gates_passed and report.quality_score >= 80.0 else "DEGRADED"
                dataset.earliest_available_ts = min_ts
                dataset.latest_available_ts = max_ts
                dataset.total_candles = len(final_df)
                dataset.latest_quality_score = report.quality_score
                dataset.parquet_relative_path = str(parquet_path)
                try:
                    dataset.storage_bytes = parquet_path.stat().st_size
                except Exception:
                    pass
                await db_repo.upsert_dataset(dataset)

            job.status = "COMPLETED"
            job.completed_at = datetime.now(timezone.utc)
            await db_repo.save_job(job)
            logger.info("historical_job_completed", job_id=job.job_id, rows=len(final_df), quality=report.quality_score)

            # Automatically derive higher timeframes (5m, 15m, 30m, 1h, 1D) from validated 1m data
            if job.timeframe.lower() in ("1m", "1", "1min"):
                try:
                    logger.info("auto_deriving_higher_timeframes_started", symbol=job.symbol)
                    derived = await derive_higher_timeframe_datasets(job.symbol, source_timeframe="1m")
                    logger.info("auto_deriving_higher_timeframes_completed", symbol=job.symbol, count=len(derived))
                except Exception as derive_err:
                    logger.warning("auto_derivation_failed", symbol=job.symbol, error=str(derive_err))

        except Exception as err:
            logger.error("historical_job_fatal_error", job_id=job.job_id, error=str(err))
            job.status = "FAILED"
            job.error_message = str(err)
            job.completed_at = datetime.now(timezone.utc)
            await db_repo.save_job(job)


# Global download service instance
download_service = HistoricalDownloadService()
