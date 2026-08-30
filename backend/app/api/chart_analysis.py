from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, timezone
from app.chart_analysis.service import analyze_instrument
from app.models.market import ApiMeta, DataStatus
from app.instruments.resolver import normalize_query

router = APIRouter(prefix="/api/v1/chart-analysis", tags=["chart-analysis"])

def _meta(provider="chart_analysis_engine"):
    return ApiMeta(provider=provider, timestamp=datetime.now(timezone.utc), status=DataStatus.DEMO)

@router.get("/{symbol}")
async def get_chart_analysis(symbol: str, timeframe: str | None = Query(default=None, pattern="^(1m|5m|15m|1h|30m|4h|1D|1W)$")):
    # Validate whitespace/normalize
    norm = symbol.strip()
    if not norm:
        raise HTTPException(status_code=400, detail="Symbol is required")
    try:
        result = await analyze_instrument(norm, requested_timeframe=timeframe)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {
        "data": result,
        "error": None,
        "meta": _meta().model_dump(mode="json"),
    }

@router.get("/{symbol}/forecast")
async def get_forecast(symbol: str, timeframe: str | None = Query(default=None)):
    try:
        result = await analyze_instrument(symbol.strip(), requested_timeframe=timeframe)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "data": {"symbol": result["symbol"], "forecasts": result["forecasts"], "generated_at": result["generated_at"]},
        "error": None,
        "meta": _meta().model_dump(mode="json"),
    }

@router.get("/{symbol}/multi-timeframe")
async def get_multi_timeframe(symbol: str):
    try:
        result = await analyze_instrument(symbol.strip())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "data": result["multi_timeframe"],
        "error": None,
        "meta": _meta().model_dump(mode="json"),
    }
