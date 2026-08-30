from datetime import datetime, timezone
from fastapi import APIRouter, Query
from app.services.timeseries_store import timeseries_store
from app.services.write_pipeline import write_pipeline
from app.models.market import ApiMeta, DataStatus

router = APIRouter(prefix="/api/v1/timeseries", tags=["timeseries"])


def _make_meta() -> ApiMeta:
    return ApiMeta(
        provider="timeseries_engine",
        timestamp=datetime.now(timezone.utc),
        status=DataStatus.LIVE,
    )


@router.get("/{symbol}/history")
async def get_historical_timeseries(
    symbol: str,
    timeframe: str = Query(default="5m", pattern="^(1m|5m|15m|1h|1D)$"),
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = Query(default=500, le=2000),
):
    """Retrieve historical time-series candles with on-the-fly resampling."""
    candles = await timeseries_store.get_candles(
        symbol=symbol.upper(),
        timeframe=timeframe,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )
    return {
        "data": [c.model_dump(mode="json") for c in candles],
        "error": None,
        "meta": _make_meta().model_dump(),
    }


@router.get("/pipeline-stats")
async def get_pipeline_stats():
    """Get time-series storage and batch write pipeline metrics."""
    return {
        "data": {
            "timeseries_store": timeseries_store.get_stats(),
            "write_pipeline": write_pipeline.get_stats(),
        },
        "error": None,
        "meta": _make_meta().model_dump(),
    }
