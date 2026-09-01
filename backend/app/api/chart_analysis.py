from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from typing import Literal, Optional
from app.chart_analysis.service import analyze_instrument, CHART_TFS
from app.models.market import ApiMeta, DataStatus
from app.instruments.registry import CHART_ANALYSIS_UNIVERSE
from app.instruments.resolver import normalize_query

router = APIRouter(prefix="/api/v1/chart-analysis", tags=["chart-analysis"])

# Strict forecast schema per §7
class ForecastDirection(BaseModel):
    up: float = Field(ge=0, le=1)
    sideways: float = Field(ge=0, le=1)
    down: float = Field(ge=0, le=1)

class ForecastRange(BaseModel):
    low: float
    high: float

class ForecastObject(BaseModel):
    symbol: str
    timeframe: str = Field(pattern="^(1m|5m|15m|1h|30m|4h|1D|1W|1d)$")
    generated_at: str
    data_timestamp: Optional[str] = None
    horizon_minutes: int = Field(gt=0)
    direction: ForecastDirection
    expected_move_percent: float
    expected_range: ForecastRange
    confidence: Literal["HIGH", "MODERATE", "LOW"]
    technical_score: Optional[float] = None
    fno_score: Optional[float] = None

def _meta(provider="chart_analysis_engine"):
    return ApiMeta(provider=provider, timestamp=datetime.now(timezone.utc), status=DataStatus.OFFLINE)

@router.get("/universe")
async def get_universe():
    """Return fixed 7-instrument derivatives universe for Chart Analysis."""
    return {
        "data": {
            "universe": CHART_ANALYSIS_UNIVERSE,
            "timeframes": CHART_TFS,
            "note": "Fixed universe — no dynamic discovery. Data unavailable instruments show 'Data unavailable' without substitution.",
        },
        "error": None,
        "meta": _meta(provider="chart_analysis_universe").model_dump(mode="json"),
    }

@router.get("/{symbol}")
async def get_chart_analysis(symbol: str, timeframe: str | None = Query(default=None, pattern="^(1m|5m|15m|1h|30m|4h|1D|1W|1d)$")):
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
async def get_forecast(symbol: str, timeframe: str | None = Query(default=None, pattern="^(1m|5m|15m|1h|4h|1D|1d)$")):
    # Normalize Daily casing if passed via query without exact chart TF match
    if timeframe == "1d":
        timeframe = "1D"
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

@router.get("/{symbol}/technical")
async def get_technical(symbol: str, timeframe: str | None = Query(default=None, pattern="^(1m|5m|15m|1h|4h|1D|1d)$")):
    if timeframe == "1d":
        timeframe = "1D"
    try:
        result = await analyze_instrument(symbol.strip(), requested_timeframe=timeframe)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    tfs = result["timeframes"]
    return {
        "data": {
            "symbol": result["symbol"],
            "timeframes": tfs,
            "fno": result["fno"],
            "generated_at": result["generated_at"],
            "disclaimer": "Technical analysis for decision support — not guaranteed outcome."
        },
        "error": None,
        "meta": _meta().model_dump(mode="json"),
    }

@router.get("/{symbol}/historical-similarity")
async def get_historical_similarity(symbol: str, timeframe: str | None = Query(default="15m", pattern="^(1m|5m|15m|1h|4h|1D|1d)$")):
    try:
        result = await analyze_instrument(symbol.strip(), requested_timeframe=None)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    tf = timeframe or "15m"
    hist = result["historical_similarity"].get(tf) or result["historical_similarity"].get("15m")
    return {
        "data": {
            "symbol": result["symbol"],
            "timeframe": tf,
            "historical_similarity": hist,
            "all_timeframes": result["historical_similarity"],
            "disclaimer": "Historical similarity is descriptive, not predictive guarantee. Sample size matters."
        },
        "error": None,
        "meta": _meta().model_dump(mode="json"),
    }
