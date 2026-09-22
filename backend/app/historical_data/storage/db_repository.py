"""Database Repository for Historical Metadata, Jobs, Versions, and Gaps.

Works with Supabase PostgreSQL (via SQLAlchemy async session) and includes
a persistent local manifest + automated cold-start Parquet disk hydration
for offline local-first resilience.
"""

from __future__ import annotations
import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy import text
import polars as pl
import structlog

from app.core.database import get_async_session_factory
from app.historical_data.models.dataset import HistoricalDataset, HistoricalDatasetVersion, LineageMetadata, MethodologyEvent
from app.historical_data.models.job import HistoricalDownloadJob, HistoricalDownloadChunk
from app.historical_data.models.gap import DataGap
from app.historical_data.models.quality import HistoricalQualityReport
from app.historical_data.storage.paths import resolve_historical_data_dir
from app.historical_data.storage.lifecycle import calculate_file_sha256

logger = structlog.get_logger(__name__)


def _parse_ts(val: Any) -> Optional[datetime]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val))
    except Exception:
        return None


class HistoricalDBRepository:
    """Async database repository for historical data governance."""

    def __init__(self, base_dir: Optional[Path] = None):
        self._is_default_base_dir = base_dir is None
        self.base_dir = base_dir or resolve_historical_data_dir()
        self.manifest_path = self.base_dir / "catalog_manifest.json"
        self._postgres_disabled = False

        # Local in-memory state mirrors database for offline/local-first execution
        self._mem_datasets: Dict[str, HistoricalDataset] = {}
        self._mem_versions: Dict[str, List[HistoricalDatasetVersion]] = {}
        self._mem_jobs: Dict[str, HistoricalDownloadJob] = {}
        self._mem_gaps: Dict[str, List[DataGap]] = {}
        self._mem_reports: Dict[str, List[HistoricalQualityReport]] = {}

        # 1. Load cached state from local manifest
        self._load_manifest()

        # 2. If empty or files exist on disk, scan and hydrate immediately
        if not self._mem_datasets:
            self._sync_from_disk_internal()

    # ── LOCAL MANIFEST PERSISTENCE ────────────────────────────────────────

    def _load_manifest(self) -> None:
        if not self.manifest_path.exists():
            return
        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for k, v in data.get("datasets", {}).items():
                self._mem_datasets[k] = HistoricalDataset(**v)

            for k, v_list in data.get("versions", {}).items():
                self._mem_versions[k] = [HistoricalDatasetVersion(**ver) for ver in v_list]

            for k, j in data.get("jobs", {}).items():
                self._mem_jobs[k] = HistoricalDownloadJob(**j)

            for k, g_list in data.get("gaps", {}).items():
                self._mem_gaps[k] = [DataGap(**g) for g in g_list]

            logger.info("loaded_historical_manifest", datasets=len(self._mem_datasets), jobs=len(self._mem_jobs))
        except Exception as e:
            logger.warning("failed_to_load_historical_manifest", error=str(e))

    def _save_manifest(self) -> None:
        try:
            self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "datasets": {k: v.model_dump(mode="json") for k, v in self._mem_datasets.items()},
                "versions": {k: [ver.model_dump(mode="json") for ver in v_list] for k, v_list in self._mem_versions.items()},
                "jobs": {k: j.model_dump(mode="json") for k, j in self._mem_jobs.items()},
                "gaps": {k: [g.model_dump(mode="json") for g in g_list] for k, g_list in self._mem_gaps.items()},
            }
            tmp = self.manifest_path.with_suffix(f".tmp.{os.getpid()}")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            try:
                tmp.replace(self.manifest_path)
            except Exception:
                import shutil
                shutil.copyfile(tmp, self.manifest_path)
                try:
                    tmp.unlink(missing_ok=True)
                except Exception:
                    pass
        except Exception as e:
            logger.warning("failed_to_save_historical_manifest", error=str(e))

    # ── DISK DISCOVERY & COLD-START HYDRATION ─────────────────────────────

    def _scan_disk_for_datasets(self) -> Tuple[Dict[str, HistoricalDataset], Dict[str, List[HistoricalDatasetVersion]]]:
        """Scan local parquet directories and sidecars to reconstruct datasets and versions."""
        candidate_dirs = [self.base_dir / "parquet"]
        if self._is_default_base_dir:
            cwd_parquet = Path.cwd() / "data" / "historical" / "parquet"
            if cwd_parquet.exists() and cwd_parquet not in candidate_dirs:
                candidate_dirs.append(cwd_parquet)

        discovered_versions: Dict[str, List[HistoricalDatasetVersion]] = {}

        for p_dir in candidate_dirs:
            if not p_dir.exists():
                continue

            for parquet_file in p_dir.rglob("candles_*.parquet"):
                try:
                    # e.g. .../parquet/sensex/1m/candles_v1.parquet
                    tf_dir = parquet_file.parent
                    sym_dir = tf_dir.parent
                    symbol_str = sym_dir.name.upper().replace("_INDEX", "")
                    timeframe_str = tf_dir.name.lower()

                    match = re.search(r"candles_(v\d+)\.parquet$", parquet_file.name)
                    version_tag = match.group(1) if match else "v1"

                    sidecar_file = parquet_file.with_suffix(".json")
                    if sidecar_file.exists():
                        with open(sidecar_file, "r", encoding="utf-8") as sf:
                            meta = json.load(sf)
                        symbol = meta.get("symbol", symbol_str)
                        timeframe = meta.get("timeframe", timeframe_str)
                        version_tag = meta.get("version_tag", version_tag)
                        row_count = int(meta.get("row_count", 0))
                        start_time = _parse_ts(meta.get("start_time"))
                        end_time = _parse_ts(meta.get("end_time"))
                        checksum = meta.get("checksum_sha256") or calculate_file_sha256(parquet_file)
                        quality_score = float(meta.get("quality_score", 100.0))
                        lineage = LineageMetadata(**meta.get("lineage", {})) if meta.get("lineage") else LineageMetadata()
                        methodology_events = [MethodologyEvent(**e) for e in meta.get("methodology_events", [])]
                    else:
                        # Inspect parquet file via Polars lazy scan
                        lf = pl.scan_parquet(parquet_file)
                        row_count = lf.select(pl.len()).collect().item()
                        min_ts = lf.select(pl.col("timestamp").min()).collect().item()
                        max_ts = lf.select(pl.col("timestamp").max()).collect().item()
                        symbol = symbol_str
                        timeframe = timeframe_str
                        start_time = min_ts if isinstance(min_ts, datetime) else _parse_ts(min_ts)
                        end_time = max_ts if isinstance(max_ts, datetime) else _parse_ts(max_ts)
                        checksum = calculate_file_sha256(parquet_file)
                        quality_score = 100.0
                        lineage = LineageMetadata()
                        methodology_events = []

                    dataset_id = f"{symbol.upper()}_{timeframe.upper()}"
                    version_id = f"{dataset_id}_{version_tag}"

                    v_rec = HistoricalDatasetVersion(
                        version_id=version_id,
                        dataset_id=dataset_id,
                        version_tag=version_tag,
                        start_time=start_time or datetime.now(timezone.utc),
                        end_time=end_time or datetime.now(timezone.utc),
                        row_count=row_count,
                        checksum_sha256=checksum,
                        quality_score=quality_score,
                        quality_status="PASSED" if quality_score >= 80.0 else "DEGRADED",
                        parquet_path=str(parquet_file),
                        lineage=lineage,
                        methodology_events=methodology_events,
                    )

                    if dataset_id not in discovered_versions:
                        discovered_versions[dataset_id] = []

                    # Avoid duplicate versions if scanned multiple paths
                    if not any(x.version_tag == version_tag for x in discovered_versions[dataset_id]):
                        discovered_versions[dataset_id].append(v_rec)

                except Exception as ex:
                    logger.warning("failed_to_inspect_parquet_file", file=str(parquet_file), error=str(ex))

        # Reconstruct HistoricalDataset entities from discovered versions
        discovered_datasets: Dict[str, HistoricalDataset] = {}
        for dataset_id, v_list in discovered_versions.items():
            # Sort versions by version tag (e.g. v1, v2)
            v_list.sort(key=lambda x: int(re.sub(r"\D", "", x.version_tag) or "0"))
            latest_v = v_list[-1]

            symbol = latest_v.version_id.split("_")[0]
            tf = latest_v.version_id.split("_")[1]
            exchange = "BSE" if "SENSEX" in symbol.upper() else "NSE"

            total_storage = 0
            for v in v_list:
                try:
                    total_storage += Path(v.parquet_path).stat().st_size
                except Exception:
                    pass

            min_start = min((v.start_time for v in v_list if v.start_time), default=datetime.now(timezone.utc))
            max_end = max((v.end_time for v in v_list if v.end_time), default=datetime.now(timezone.utc))

            ds = HistoricalDataset(
                id=dataset_id,
                symbol=symbol,
                exchange=exchange,
                asset_type="INDEX",
                timeframe=tf.lower(),
                provider=latest_v.lineage.provider_id if latest_v.lineage else "fyers",
                status="READY" if latest_v.quality_score >= 80.0 else "DEGRADED",
                current_version_id=latest_v.version_id,
                earliest_available_ts=min_start,
                latest_available_ts=max_end,
                total_candles=latest_v.row_count,
                latest_quality_score=latest_v.quality_score,
                storage_bytes=total_storage,
                parquet_relative_path=str(latest_v.parquet_path),
                metadata={
                    "source": "disk_scan",
                    "available_versions": [v.version_tag for v in v_list],
                },
            )
            discovered_datasets[dataset_id] = ds

        return discovered_datasets, discovered_versions

    def _sync_from_disk_internal(self) -> None:
        """Internal synchronous scan and hydrate."""
        d_map, v_map = self._scan_disk_for_datasets()
        for d_id, ds in d_map.items():
            self._mem_datasets[d_id] = ds
        for d_id, v_list in v_map.items():
            self._mem_versions[d_id] = v_list
        if d_map:
            self._save_manifest()
            logger.info("historical_disk_scan_hydrated", count=len(d_map), datasets=list(d_map.keys()))

    async def sync_from_disk(self) -> List[HistoricalDataset]:
        """Discover on-disk parquet files and synchronize with catalog and database."""
        self._sync_from_disk_internal()

        # If database session is available, sync to Postgres as well
        factory = get_async_session_factory()
        if factory and not self._postgres_disabled:
            try:
                for ds in self._mem_datasets.values():
                    await self.upsert_dataset(ds)
                if not self._postgres_disabled:
                    for v_list in self._mem_versions.values():
                        for ver in v_list:
                            await self.create_version(ver)
            except Exception as e:
                logger.warning("db_sync_from_disk_postgres_fallback", error=str(e))

        return list(self._mem_datasets.values())

    # ── DATASETS ──────────────────────────────────────────────────────────

    async def upsert_dataset(self, dataset: HistoricalDataset) -> HistoricalDataset:
        self._mem_datasets[dataset.id] = dataset
        self._save_manifest()

        factory = get_async_session_factory()
        if factory and not self._postgres_disabled:
            try:
                async with factory() as session:
                    query = text("""
                        INSERT INTO historical_datasets (
                            id, symbol, exchange, asset_type, timeframe, provider,
                            status, current_version_id, earliest_available_ts, latest_available_ts,
                            total_candles, latest_quality_score, storage_bytes, parquet_relative_path,
                            metadata_json, updated_at
                        ) VALUES (
                            :id, :symbol, :exchange, :asset_type, :timeframe, :provider,
                            :status, :current_version_id, :earliest_available_ts, :latest_available_ts,
                            :total_candles, :latest_quality_score, :storage_bytes, :parquet_relative_path,
                            :metadata_json, NOW()
                        )
                        ON CONFLICT (id) DO UPDATE SET
                            status = EXCLUDED.status,
                            current_version_id = EXCLUDED.current_version_id,
                            earliest_available_ts = EXCLUDED.earliest_available_ts,
                            latest_available_ts = EXCLUDED.latest_available_ts,
                            total_candles = EXCLUDED.total_candles,
                            latest_quality_score = EXCLUDED.latest_quality_score,
                            storage_bytes = EXCLUDED.storage_bytes,
                            parquet_relative_path = EXCLUDED.parquet_relative_path,
                            metadata_json = EXCLUDED.metadata_json,
                            updated_at = NOW();
                    """)
                    await session.execute(query, {
                        "id": dataset.id,
                        "symbol": dataset.symbol,
                        "exchange": dataset.exchange,
                        "asset_type": dataset.asset_type,
                        "timeframe": dataset.timeframe,
                        "provider": dataset.provider,
                        "status": dataset.status,
                        "current_version_id": dataset.current_version_id,
                        "earliest_available_ts": dataset.earliest_available_ts,
                        "latest_available_ts": dataset.latest_available_ts,
                        "total_candles": dataset.total_candles,
                        "latest_quality_score": dataset.latest_quality_score,
                        "storage_bytes": dataset.storage_bytes,
                        "parquet_relative_path": dataset.parquet_relative_path,
                        "metadata_json": json.dumps(dataset.metadata),
                    })
                    await session.commit()
            except Exception as e:
                if "does not exist" in str(e).lower():
                    self._postgres_disabled = True
                    logger.info("postgres_historical_tables_missing_local_mode_active")
                else:
                    logger.warning("db_upsert_dataset_fallback_to_memory", error=str(e))

        return dataset

    async def get_dataset(self, dataset_id: str) -> Optional[HistoricalDataset]:
        factory = get_async_session_factory()
        if factory:
            try:
                async with factory() as session:
                    res = await session.execute(
                        text("SELECT * FROM historical_datasets WHERE id = :id"),
                        {"id": dataset_id}
                    )
                    row = res.mappings().first()
                    if row:
                        return HistoricalDataset(
                            id=row["id"],
                            symbol=row["symbol"],
                            exchange=row["exchange"],
                            asset_type=row["asset_type"],
                            timeframe=row["timeframe"],
                            provider=row["provider"],
                            status=row["status"],
                            current_version_id=row["current_version_id"],
                            earliest_available_ts=row["earliest_available_ts"],
                            latest_available_ts=row["latest_available_ts"],
                            total_candles=row["total_candles"],
                            latest_quality_score=row["latest_quality_score"],
                            storage_bytes=row["storage_bytes"],
                            parquet_relative_path=row["parquet_relative_path"],
                            metadata=row["metadata_json"] if isinstance(row["metadata_json"], dict) else json.loads(row["metadata_json"] or "{}"),
                            created_at=row["created_at"],
                            updated_at=row["updated_at"],
                        )
            except Exception as e:
                logger.warning("db_get_dataset_failed", error=str(e))

        if dataset_id not in self._mem_datasets:
            self._sync_from_disk_internal()

        return self._mem_datasets.get(dataset_id)

    async def list_datasets(self) -> List[HistoricalDataset]:
        factory = get_async_session_factory()
        if factory:
            try:
                async with factory() as session:
                    res = await session.execute(text("SELECT * FROM historical_datasets ORDER BY updated_at DESC"))
                    datasets = []
                    for row in res.mappings().all():
                        datasets.append(HistoricalDataset(
                            id=row["id"],
                            symbol=row["symbol"],
                            exchange=row["exchange"],
                            asset_type=row["asset_type"],
                            timeframe=row["timeframe"],
                            provider=row["provider"],
                            status=row["status"],
                            current_version_id=row["current_version_id"],
                            earliest_available_ts=row["earliest_available_ts"],
                            latest_available_ts=row["latest_available_ts"],
                            total_candles=row["total_candles"],
                            latest_quality_score=row["latest_quality_score"],
                            storage_bytes=row["storage_bytes"],
                            parquet_relative_path=row["parquet_relative_path"],
                            metadata=row["metadata_json"] if isinstance(row["metadata_json"], dict) else json.loads(row["metadata_json"] or "{}"),
                            created_at=row["created_at"],
                            updated_at=row["updated_at"],
                        ))
                    if datasets:
                        return datasets
            except Exception as e:
                logger.warning("db_list_datasets_failed", error=str(e))

        if not self._mem_datasets:
            await self.sync_from_disk()

        return list(self._mem_datasets.values())

    # ── DATASET VERSIONS ──────────────────────────────────────────────────

    async def create_version(self, version: HistoricalDatasetVersion) -> HistoricalDatasetVersion:
        if version.dataset_id not in self._mem_versions:
            self._mem_versions[version.dataset_id] = []
        # Deduplicate in memory
        existing = [v for v in self._mem_versions[version.dataset_id] if v.version_id == version.version_id]
        if existing:
            self._mem_versions[version.dataset_id].remove(existing[0])
        self._mem_versions[version.dataset_id].append(version)
        self._save_manifest()

        factory = get_async_session_factory()
        if factory and not self._postgres_disabled:
            try:
                async with factory() as session:
                    query = text("""
                        INSERT INTO historical_dataset_versions (
                            version_id, dataset_id, version_tag, start_time, end_time,
                            row_count, checksum_sha256, quality_score, quality_status,
                            parquet_path, lineage_json, methodology_events_json, created_at
                        ) VALUES (
                            :version_id, :dataset_id, :version_tag, :start_time, :end_time,
                            :row_count, :checksum_sha256, :quality_score, :quality_status,
                            :parquet_path, :lineage_json, :methodology_events_json, NOW()
                        )
                        ON CONFLICT (version_id) DO UPDATE SET
                            start_time = EXCLUDED.start_time,
                            end_time = EXCLUDED.end_time,
                            row_count = EXCLUDED.row_count,
                            checksum_sha256 = EXCLUDED.checksum_sha256,
                            quality_score = EXCLUDED.quality_score,
                            quality_status = EXCLUDED.quality_status,
                            parquet_path = EXCLUDED.parquet_path,
                            lineage_json = EXCLUDED.lineage_json,
                            methodology_events_json = EXCLUDED.methodology_events_json;
                    """)
                    await session.execute(query, {
                        "version_id": version.version_id,
                        "dataset_id": version.dataset_id,
                        "version_tag": version.version_tag,
                        "start_time": version.start_time,
                        "end_time": version.end_time,
                        "row_count": version.row_count,
                        "checksum_sha256": version.checksum_sha256,
                        "quality_score": version.quality_score,
                        "quality_status": version.quality_status,
                        "parquet_path": version.parquet_path,
                        "lineage_json": json.dumps(version.lineage.model_dump(mode="json")),
                        "methodology_events_json": json.dumps([e.model_dump(mode="json") for e in version.methodology_events]),
                    })
                    await session.commit()
            except Exception as e:
                if "does not exist" in str(e).lower():
                    self._postgres_disabled = True
                    logger.info("postgres_historical_tables_missing_local_mode_active")
                else:
                    logger.warning("db_create_version_failed", error=str(e))

        return version

    async def list_versions(self, dataset_id: str) -> List[HistoricalDatasetVersion]:
        factory = get_async_session_factory()
        if factory:
            try:
                async with factory() as session:
                    res = await session.execute(
                        text("SELECT * FROM historical_dataset_versions WHERE dataset_id = :id ORDER BY created_at DESC"),
                        {"id": dataset_id}
                    )
                    versions = []
                    for row in res.mappings().all():
                        versions.append(HistoricalDatasetVersion(
                            version_id=row["version_id"],
                            dataset_id=row["dataset_id"],
                            version_tag=row["version_tag"],
                            start_time=row["start_time"],
                            end_time=row["end_time"],
                            row_count=row["row_count"],
                            checksum_sha256=row["checksum_sha256"],
                            quality_score=row["quality_score"],
                            quality_status=row["quality_status"],
                            parquet_path=row["parquet_path"],
                            created_at=row["created_at"],
                        ))
                    if versions:
                        return versions
            except Exception as e:
                logger.warning("db_list_versions_failed", error=str(e))

        if dataset_id not in self._mem_versions:
            self._sync_from_disk_internal()

        return self._mem_versions.get(dataset_id, [])

    # ── DOWNLOAD JOBS ─────────────────────────────────────────────────────

    async def save_job(self, job: HistoricalDownloadJob) -> HistoricalDownloadJob:
        self._mem_jobs[job.job_id] = job
        self._save_manifest()

        factory = get_async_session_factory()
        if factory:
            try:
                async with factory() as session:
                    query = text("""
                        INSERT INTO historical_download_jobs (
                            job_id, dataset_id, symbol, timeframe, provider,
                            range_from, range_to, status, progress_pct, total_chunks,
                            completed_chunks, rows_downloaded, rows_valid, rows_rejected,
                            retry_count, error_message, started_at, completed_at, created_at
                        ) VALUES (
                            :job_id, :dataset_id, :symbol, :timeframe, :provider,
                            :range_from, :range_to, :status, :progress_pct, :total_chunks,
                            :completed_chunks, :rows_downloaded, :rows_valid, :rows_rejected,
                            :retry_count, :error_message, :started_at, :completed_at, NOW()
                        )
                        ON CONFLICT (job_id) DO UPDATE SET
                            status = EXCLUDED.status,
                            progress_pct = EXCLUDED.progress_pct,
                            completed_chunks = EXCLUDED.completed_chunks,
                            rows_downloaded = EXCLUDED.rows_downloaded,
                            rows_valid = EXCLUDED.rows_valid,
                            rows_rejected = EXCLUDED.rows_rejected,
                            retry_count = EXCLUDED.retry_count,
                            error_message = EXCLUDED.error_message,
                            started_at = EXCLUDED.started_at,
                            completed_at = EXCLUDED.completed_at;
                    """)
                    await session.execute(query, {
                        "job_id": job.job_id,
                        "dataset_id": job.dataset_id,
                        "symbol": job.symbol,
                        "timeframe": job.timeframe,
                        "provider": job.provider,
                        "range_from": job.range_from,
                        "range_to": job.range_to,
                        "status": job.status,
                        "progress_pct": job.progress_pct,
                        "total_chunks": job.total_chunks,
                        "completed_chunks": job.completed_chunks,
                        "rows_downloaded": job.rows_downloaded,
                        "rows_valid": job.rows_valid,
                        "rows_rejected": job.rows_rejected,
                        "retry_count": job.retry_count,
                        "error_message": job.error_message,
                        "started_at": job.started_at,
                        "completed_at": job.completed_at,
                    })
                    await session.commit()
            except Exception as e:
                logger.warning("db_save_job_failed", error=str(e))

        return job

    async def get_job(self, job_id: str) -> Optional[HistoricalDownloadJob]:
        return self._mem_jobs.get(job_id)

    async def list_jobs(self, limit: int = 20) -> List[HistoricalDownloadJob]:
        return list(sorted(self._mem_jobs.values(), key=lambda j: j.created_at, reverse=True))[:limit]

    async def reconcile_orphaned_jobs(self) -> int:
        """Mark any jobs left in RUNNING or QUEUED state from previous server runs as CANCELLED."""
        reconciled = 0
        now = datetime.now(timezone.utc)
        for job in list(self._mem_jobs.values()):
            if job.status in ("RUNNING", "QUEUED"):
                job.status = "CANCELLED"
                job.error_message = "Interrupted by server restart"
                job.completed_at = now
                for chunk in job.chunks:
                    if chunk.status in ("PENDING", "DOWNLOADING"):
                        chunk.status = "CANCELLED"
                await self.save_job(job)
                reconciled += 1
        if reconciled > 0:
            logger.info("reconciled_orphaned_jobs", count=reconciled)
        return reconciled

    async def delete_job(self, job_id: str) -> bool:
        """Delete a job record from memory, manifest, and PostgreSQL."""
        if job_id in self._mem_jobs:
            del self._mem_jobs[job_id]
            self._save_manifest()

        factory = get_async_session_factory()
        if factory:
            try:
                async with factory() as session:
                    await session.execute(
                        text("DELETE FROM historical_download_jobs WHERE job_id = :job_id"),
                        {"job_id": job_id}
                    )
                    await session.commit()
            except Exception as e:
                logger.warning("db_delete_job_failed", job_id=job_id, error=str(e))
        return True

    # ── GAPS ──────────────────────────────────────────────────────────────

    async def save_gap(self, gap: DataGap) -> DataGap:
        if gap.dataset_id not in self._mem_gaps:
            self._mem_gaps[gap.dataset_id] = []
        existing = [g for g in self._mem_gaps[gap.dataset_id] if g.gap_id == gap.gap_id]
        if existing:
            self._mem_gaps[gap.dataset_id].remove(existing[0])
        self._mem_gaps[gap.dataset_id].append(gap)
        self._save_manifest()
        return gap

    async def list_gaps(self, dataset_id: str) -> List[DataGap]:
        return self._mem_gaps.get(dataset_id, [])

    # ── QUALITY REPORTS ───────────────────────────────────────────────────

    async def save_quality_report(self, report: HistoricalQualityReport) -> HistoricalQualityReport:
        if report.dataset_id not in self._mem_reports:
            self._mem_reports[report.dataset_id] = []
        self._mem_reports[report.dataset_id].append(report)
        return report

    async def get_latest_quality_report(self, dataset_id: str) -> Optional[HistoricalQualityReport]:
        reports = self._mem_reports.get(dataset_id, [])
        if reports:
            return sorted(reports, key=lambda r: r.created_at, reverse=True)[0]
        return None


# Global database repository instance
db_repo = HistoricalDBRepository()
