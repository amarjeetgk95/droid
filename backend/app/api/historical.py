from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query
from app.services.historical_service import historical_service
from app.models.market import ApiMeta, DataStatus

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
