from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query
from app.services.binance_service import binance_service
from app.models.market import ApiMeta, DataStatus

router = APIRouter(prefix="/api/v1/crypto", tags=["crypto"])


def _make_meta(provider: str = "binance") -> ApiMeta:
    return ApiMeta(
        provider=provider,
        timestamp=datetime.now(timezone.utc),
        status=DataStatus.LIVE,
    )


@router.get("/tickers")
async def get_crypto_tickers():
    """Retrieve 24h ticker statistics for top liquid cryptocurrency pairs on Binance."""
    try:
        tickers = await binance_service.get_top_tickers()
        return {
            "data": [t.model_dump(mode="json") for t in tickers],
            "error": None,
            "meta": _make_meta("binance_spot").model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/quote")
async def get_crypto_quote(symbol: str):
    """Retrieve detailed 24hr quote for a specific crypto symbol (e.g. BTCUSDT, ETHUSDT)."""
    try:
        ticker = await binance_service.get_ticker(symbol)
        return {
            "data": ticker.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta("binance_spot").model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/candles")
async def get_crypto_candles(
    symbol: str,
    timeframe: str = Query(default="1h", description="Candlestick interval: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w"),
    limit: int = Query(default=100, ge=10, le=500, description="Bar count to return"),
):
    """Retrieve historical candlestick bars from Binance Spot for interactive charting."""
    try:
        candles = await binance_service.get_candles(symbol, timeframe, limit)
        return {
            "data": [c.model_dump(mode="json") for c in candles],
            "error": None,
            "meta": _make_meta("binance_spot").model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/orderbook")
async def get_crypto_order_book(
    symbol: str,
    limit: int = Query(default=20, ge=5, le=50, description="Depth level count for bids and asks"),
):
    """Retrieve real-time order book depth (bids and asks) with spread analysis."""
    try:
        orderbook = await binance_service.get_order_book(symbol, limit)
        return {
            "data": orderbook.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta("binance_depth").model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/derivatives")
async def get_crypto_derivatives(symbol: str):
    """Retrieve live funding rate, countdown timer, open interest, and long/short ratio from Binance Futures."""
    try:
        derivs = await binance_service.get_derivatives_data(symbol)
        return {
            "data": derivs.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta("binance_futures").model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/market-overview")
async def get_crypto_market_overview():
    """Retrieve global cryptocurrency market metrics, Fear & Greed index, and top gainers/losers."""
    try:
        overview = await binance_service.get_market_overview()
        return {
            "data": overview.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta("binance_market").model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
