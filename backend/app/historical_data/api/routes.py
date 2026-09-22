"""FastAPI REST Router for Historical Data Management."""

from __future__ import annotations
from datetime import date, datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
import io
import structlog

from app.historical_data.api.schemas import DownloadRequest, RepairRequest, DeriveRequest, CandlePageResponse
from app.historical_data.services.dataset_service import dataset_service
from app.historical_data.services.download_service import download_service
from app.historical_data.services.repair_service import repair_service
from app.historical_data.services.aggregator_service import derive_higher_timeframe_datasets
from app.historical_data.services.auto_sync_service import auto_sync_service
from app.historical_data.storage.db_repository import db_repo

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/historical-data", tags=["historical_data"])


@router.get("/datasets", summary="List all managed historical datasets")
async def list_datasets():
    datasets = await dataset_service.list_datasets()
    return {"datasets": datasets}


@router.post("/sync", summary="Synchronize datasets and versions from local Parquet storage")
async def sync_datasets():
    synced = await db_repo.sync_from_disk()
    return {"status": "success", "count": len(synced), "datasets": [d.model_dump() for d in synced]}


@router.get("/auto-sync/status", summary="Get status of automated daily EOD historical sync")
async def get_auto_sync_status():
    return auto_sync_service.get_status()


@router.post("/auto-sync/toggle", summary="Enable or disable automated daily EOD historical sync")
async def toggle_auto_sync(enabled: Optional[bool] = None):
    if enabled is None:
        auto_sync_service.enabled = not auto_sync_service.enabled
    else:
        auto_sync_service.enabled = enabled
    return auto_sync_service.get_status()


@router.post("/auto-sync/trigger", summary="Manually trigger an immediate EOD delta sync / catch-up")
async def trigger_auto_sync():
    res = await auto_sync_service.sync_deltas(reason="MANUAL_UI_TRIGGER")
    return res


@router.get("/datasets/{dataset_id}", summary="Get detailed dataset info, versions, and quality report")
async def get_dataset_details(dataset_id: str):
    details = await dataset_service.get_dataset_details(dataset_id)
    if not details:
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")
    return details


@router.get("/candles", response_model=CandlePageResponse, summary="Query paginated candles for the Candle Inspector")
async def get_candles(
    symbol: str = Query("SENSEX"),
    timeframe: str = Query("1m"),
    version: str = Query("v1"),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=10, le=1000),
    sort_desc: bool = Query(True),
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
):
    try:
        page_res = dataset_service.get_candle_page(
            symbol=symbol,
            timeframe=timeframe,
            version_tag=version,
            page=page,
            page_size=page_size,
            sort_desc=sort_desc,
            start_time=start_time,
            end_time=end_time,
        )
        return page_res
    except Exception as e:
        logger.error("get_candles_failed", symbol=symbol, error=str(e))
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/download", summary="Enqueue a background download job")
async def trigger_download(req: DownloadRequest):
    try:
        job = await download_service.enqueue_download(
            symbol=req.symbol,
            timeframe=req.timeframe,
            start_date=req.range_from,
            end_date=req.range_to,
            force_refresh=req.force_refresh,
        )
        return {"status": "enqueued", "job": job.model_dump()}
    except Exception as e:
        logger.error("trigger_download_failed", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/jobs", summary="List historical download jobs")
async def list_jobs(limit: int = Query(20, ge=1, le=100)):
    jobs = await db_repo.list_jobs(limit=limit)
    return {"jobs": [j.model_dump() for j in jobs]}


@router.get("/jobs/{job_id}", summary="Get job status and chunk details")
async def get_job_status(job_id: str):
    job = await db_repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job": job.model_dump()}


@router.post("/jobs/{job_id}/cancel", summary="Cancel a running or queued download job")
async def cancel_job(job_id: str):
    job = await download_service.cancel_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "cancelled", "job": job.model_dump()}


@router.delete("/jobs/{job_id}", summary="Delete a job from history")
async def delete_job(job_id: str):
    await download_service.delete_job(job_id)
    return {"status": "deleted", "job_id": job_id}


@router.post("/jobs/cleanup", summary="Reconcile and cleanup orphaned or stale jobs")
async def cleanup_jobs():
    count = await db_repo.reconcile_orphaned_jobs()
    return {"status": "ok", "reconciled_count": count}


@router.get("/gaps", summary="List detected session gaps")
async def list_gaps(dataset_id: str = Query("SENSEX_1M")):
    gaps = await db_repo.list_gaps(dataset_id)
    return {"gaps": [g.model_dump() for g in gaps]}


@router.post("/repair", summary="Trigger targeted gap repair")
async def repair_gap(req: RepairRequest):
    try:
        repaired = await repair_service.repair_gap(req.gap_id)
        return {"status": "success", "gap": repaired.model_dump()}
    except Exception as e:
        logger.error("repair_gap_failed", gap_id=req.gap_id, error=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/derive", summary="Derive higher timeframe datasets from 1m candles")
async def derive_datasets(req: DeriveRequest):
    try:
        derived = await derive_higher_timeframe_datasets(
            symbol=req.symbol,
            source_timeframe=req.source_timeframe,
            target_timeframes=req.target_timeframes,
        )
        return {
            "status": "success",
            "derived_count": len(derived),
            "datasets": [d.model_dump() for d in derived],
        }
    except Exception as e:
        logger.error("derive_datasets_failed", symbol=req.symbol, error=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/export", summary="Export dataset as Parquet or CSV")
async def export_dataset(
    symbol: str = Query("SENSEX"),
    timeframe: str = Query("1m"),
    version: str = Query("v1"),
    format: str = Query("csv"),
):
    try:
        content, media_type, filename = dataset_service.export_candles(
            symbol=symbol,
            timeframe=timeframe,
            version_tag=version,
            export_format=format,
        )
        return StreamingResponse(
            io.BytesIO(content),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
