"""
Benchmark & Outcome Logging API — §38, §39
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.services.benchmark_service import run_benchmark, get_benchmark_history
from app.services.outcome_logger import log_ai_event, log_horizon_outcome, get_outcome_logs
from app.models.market import ApiMeta, DataStatus

router = APIRouter(prefix="/api/v1/benchmark", tags=["benchmark"])


def _meta() -> ApiMeta:
    return ApiMeta(provider="benchmark_engine", timestamp=datetime.now(timezone.utc), status=DataStatus.DEMO)


class BenchmarkRunPayload(BaseModel):
    models: list[str]
    task: str = "INTRADAY_ANALYSIS"
    snapshot_count: int = 10


@router.post("/run")
async def run_benchmark_endpoint(payload: BenchmarkRunPayload):
    # Synthetic snapshots for demo
    snapshots = [{"symbol": "NIFTY", "price": 24750 + i*10, "state_version": 18450+i} for i in range(payload.snapshot_count)]
    run = await run_benchmark(snapshots, payload.models, payload.task)
    return {"data": run, "error": None, "meta": _meta().model_dump()}


@router.get("/history")
async def benchmark_history(limit: int = Query(default=20, le=100)):
    history = get_benchmark_history(limit=limit)
    return {"data": history, "error": None, "meta": _meta().model_dump()}


@router.get("/outcomes")
async def outcome_history(limit: int = Query(default=20, le=100), symbol: str | None = None):
    logs = get_outcome_logs(limit=limit, symbol=symbol)
    return {"data": logs, "error": None, "meta": _meta().model_dump()}


@router.post("/outcomes/log")
async def log_outcome_endpoint(payload: dict):
    # Minimal proxy to log_ai_event
    entry = log_ai_event(
        state_version=payload.get("state_version", 0),
        timestamp=datetime.now(timezone.utc),
        symbol=payload.get("symbol", "NIFTY"),
        market_state=payload.get("market_state", {}),
        technical_features=payload.get("technical_features"),
        direction_prob=payload.get("direction_prob"),
        tsfm_forecast=payload.get("tsfm_forecast"),
        ai_provider=payload.get("ai_provider", "openrouter"),
        ai_model=payload.get("ai_model", "auto"),
        ai_task=payload.get("ai_task", "INTRADAY_ANALYSIS"),
        ai_bias=payload.get("ai_bias", "HOLD"),
        confidence_breakdown=payload.get("confidence_breakdown"),
        trigger_reason=payload.get("trigger_reason", "MANUAL_ANALYSIS"),
        risk_calculations=payload.get("risk_calculations"),
        analysis_id=payload.get("analysis_id", "test-id"),
    )
    return {"data": entry, "error": None, "meta": _meta().model_dump()}
