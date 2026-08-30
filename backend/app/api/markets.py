from fastapi import APIRouter, HTTPException, Query
from app.services.market_service import MarketService
from app.models.market import (
    NormalizedQuote, NormalizedCandle, IndexCard,
    MarketStatusResponse, MarketBreadthData,
    ApiResponse, ApiMeta, DataStatus,
)
from datetime import datetime, timezone
import structlog

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/markets", tags=["markets"])


def _make_meta(provider: str = "mock", status: DataStatus = DataStatus.DEMO) -> ApiMeta:
    return ApiMeta(
        provider=provider,
        timestamp=datetime.now(timezone.utc),
        status=status,
    )


@router.get("/quotes")
async def get_all_quotes():
    """Get quotes for all tracked instruments."""
    service = MarketService()
    try:
        quotes = await service.get_quotes()
        return {
            "data": [q.model_dump() for q in quotes],
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        logger.error("get_quotes_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/quote")
async def get_quote(symbol: str):
    """Get quote for a specific symbol."""
    service = MarketService()
    try:
        quote = await service.get_quote(symbol)
        return {
            "data": quote.model_dump(),
            "error": None,
            "meta": _make_meta(provider=quote.provider, status=quote.status).model_dump(),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("get_quote_failed", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/candles")
async def get_candles(
    symbol: str,
    timeframe: str = Query(default="5m", pattern="^(1m|5m|15m|1h|1D)$"),
):
    """Get historical candles for a symbol."""
    service = MarketService()
    try:
        candles = await service.get_candles(symbol, timeframe)
        return {
            "data": [c.model_dump() for c in candles],
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("get_candles_failed", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_market_status():
    """Get current market session status."""
    service = MarketService()
    status = await service.get_market_status()
    return {
        "data": status.model_dump(),
        "error": None,
        "meta": _make_meta().model_dump(),
    }


@router.get("/breadth")
async def get_market_breadth():
    """Get market breadth data."""
    service = MarketService()
    breadth = await service.get_market_breadth()
    return {
        "data": breadth.model_dump(),
        "error": None,
        "meta": _make_meta().model_dump(),
    }


@router.get("/cards")
async def get_index_cards():
    """Get dashboard index cards."""
    service = MarketService()
    cards = await service.get_index_cards()
    return {
        "data": [c.model_dump() for c in cards],
        "error": None,
        "meta": _make_meta().model_dump(),
    }
