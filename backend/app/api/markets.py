from fastapi import APIRouter, HTTPException, Query

import structlog

from app.api.envelope import envelope
from app.models.market import DataStatus
from app.services.market_service import MarketService

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/markets", tags=["markets"])

_FALLBACK_PROVIDER = "market_data"


def _active_provider(service: MarketService) -> str:
    try:
        return service._provider.provider_name
    except Exception:
        return _FALLBACK_PROVIDER


@router.get("/quotes")
async def get_all_quotes():
    """Get quotes for all tracked instruments."""
    service = MarketService()
    try:
        quotes = await service.get_quotes()
    except Exception as e:
        logger.error("get_quotes_failed", error=str(e))
        raise
    active_status = quotes[0].status if quotes else DataStatus.OFFLINE
    return envelope([q.model_dump() for q in quotes], provider=_active_provider(service), status=active_status)


@router.get("/{symbol}/quote")
async def get_quote(symbol: str):
    """Get quote for a specific symbol."""
    service = MarketService()
    try:
        quote = await service.get_quote(symbol)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return envelope(quote.model_dump(), provider=quote.provider, status=quote.status)


@router.get("/{symbol}/candles")
async def get_candles(
    symbol: str,
    timeframe: str = Query(default="5m", pattern="^(1m|5m|15m|1h|1D)$"),
):
    """Get historical candles for a symbol."""
    service = MarketService()
    try:
        candles = await service.get_candles(symbol, timeframe)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return envelope(
        [c.model_dump() for c in candles],
        provider=_active_provider(service),
        status=DataStatus.LIVE if candles else DataStatus.OFFLINE,
    )


@router.get("/status")
async def get_market_status():
    """Get current market session status."""
    service = MarketService()
    status = await service.get_market_status()
    # Coordinator cache may hold a plain dict from an older deployment /
    # Redis pickle — accept both instead of 500ing (which the header pill
    # renders as broker-gateway OFFLINE).
    if isinstance(status, dict):
        try:
            from app.models.market import MarketStatusResponse

            status = MarketStatusResponse(**status)
        except Exception as e:
            logger.error("get_market_status_shape_invalid", error=str(e))
            raise HTTPException(status_code=500, detail=str(e))
    return envelope(status.model_dump(), provider=status.provider, status=status.data_status)


@router.get("/breadth")
async def get_market_breadth():
    """Get market breadth data."""
    service = MarketService()
    breadth = await service.get_market_breadth()
    return envelope(breadth.model_dump(), provider=_active_provider(service), status=breadth.status)


@router.get("/cards")
async def get_index_cards():
    """Get dashboard index cards."""
    service = MarketService()
    cards = await service.get_index_cards()
    active_status = cards[0].status if cards else DataStatus.OFFLINE
    return envelope([c.model_dump() for c in cards], provider=_active_provider(service), status=active_status)
