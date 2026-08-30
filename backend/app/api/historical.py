from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from app.services.historical_service import historical_service
from app.models.market import ApiMeta, DataStatus
from app.models.historical import PatternHitRateResponse, PatternOutcomeRecord, PatternOutcomesRequest

router = APIRouter(tags=["historical"])


def _make_meta() -> ApiMeta:
    return ApiMeta(
        provider="historical_intelligence_engine",
        timestamp=datetime.now(timezone.utc),
        status=DataStatus.DEMO,
    )


@router.get("/api/v1/history/{symbol}/patterns")
async def get_detected_patterns(
    symbol: str,
    timeframe: str = Query(default="5m", description="Candle timeframe e.g. 5m, 15m, 1h, 1D"),
):
    """Detect recent candlestick and volatility price action patterns."""
    try:
        patterns = await historical_service.scan_patterns(symbol, timeframe)
        return {
            "data": [p.model_dump(mode="json") for p in patterns],
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/history/{symbol}/shifts")
async def get_historical_shifts(
    symbol: str,
    days: int = Query(default=10, description="Number of historical sessions"),
):
    """Retrieve multi-session historical shifts for PCR, Max Pain, and ATM IV."""
    try:
        shifts = await historical_service.get_historical_shifts(symbol, days)
        return {
            "data": shifts.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/history/{symbol}/seasonality")
async def get_seasonality(symbol: str):
    """Retrieve day-of-the-week return and volatility distribution."""
    try:
        seasonality = historical_service.get_seasonality(symbol)
        return {
            "data": seasonality.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/watchlist")
async def get_watchlist():
    """Retrieve user watchlist instruments with live quotes and active patterns."""
    try:
        items = await historical_service.get_watchlist()
        return {
            "data": [item.model_dump(mode="json") for item in items],
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/watchlist/add")
async def add_to_watchlist(symbol: str = Query(description="Instrument symbol e.g. NIFTY 50")):
    """Add an instrument to the user watchlist."""
    try:
        historical_service.add_to_watchlist(symbol)
        return {"data": {"symbol": symbol, "status": "added"}, "error": None, "meta": _make_meta().model_dump()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/watchlist/remove")
async def remove_from_watchlist(symbol: str = Query(description="Instrument symbol to remove")):
    """Remove an instrument from the user watchlist."""
    try:
        historical_service.remove_from_watchlist(symbol)
        return {"data": {"symbol": symbol, "status": "removed"}, "error": None, "meta": _make_meta().model_dump()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Pattern Outcome Tracking Endpoints (Historical Intelligence v2)
# ============================================================

@router.get("/api/v1/history/{symbol}/hit-rates")
async def get_pattern_hit_rates(
    symbol: str,
    timeframe: Optional[str] = Query(default=None, description="Filter by timeframe e.g. 5m, 15m, 1h, 1D"),
):
    """Get aggregated hit-rate statistics for detected patterns."""
    try:
        hit_rates = await historical_service.get_hit_rates(symbol, timeframe)
        return {
            "data": hit_rates.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/history/{symbol}/outcomes")
async def get_recent_pattern_outcomes(
    symbol: str,
    pattern_types: Optional[str] = Query(default=None, description="Comma-separated pattern types"),
    timeframe: Optional[str] = Query(default=None, description="Filter by timeframe"),
    limit: int = Query(default=20, description="Max outcomes to return"),
):
    """Get recent labeled pattern outcomes for a symbol."""
    try:
        pattern_list = pattern_types.split(",") if pattern_types else None
        outcomes = await historical_service.get_recent_outcomes(symbol, pattern_list, timeframe, limit)
        return {
            "data": [o.model_dump(mode="json") for o in outcomes],
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/history/{symbol}/label-outcomes")
async def label_pattern_outcomes(
    symbol: str,
    pattern_types: Optional[str] = Query(default=None, description="Comma-separated pattern types"),
    timeframe: Optional[str] = Query(default=None, description="Filter by timeframe"),
):
    """Trigger on-demand outcome labeling for unlabeled patterns."""
    try:
        pattern_list = pattern_types.split(",") if pattern_types else None
        labeled_count = await historical_service.label_outcomes_for_symbol(symbol, pattern_list, timeframe, "on_demand")
        return {
            "data": {"symbol": symbol, "labeled_count": labeled_count, "status": "completed"},
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/history/hit-rates/refresh")
async def refresh_hit_rates_view():
    """Refresh the materialized view for hit rates."""
    try:
        success = await historical_service.refresh_hit_rates_view()
        return {
            "data": {"refreshed": success},
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
