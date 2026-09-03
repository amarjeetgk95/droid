from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query
from app.services.binance_service import binance_service
from app.services.market_data_health import market_health_tracker
from app.models.crypto import ALLOWED_CRYPTO_SYMBOLS
from app.models.market import ApiMeta, DataStatus

router = APIRouter(prefix="/api/v1/crypto", tags=["crypto"])


def _make_meta(provider: str = "binance") -> ApiMeta:
    return ApiMeta(
        provider=provider,
        timestamp=datetime.now(timezone.utc),
        status=DataStatus.LIVE,
    )


def _check_symbol(symbol: str) -> str:
    try:
        return binance_service.validate_symbol(symbol)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported symbol '{symbol}'. Allowed symbols: {list(ALLOWED_CRYPTO_SYMBOLS)}",
        )


@router.get("/tickers")
async def get_crypto_tickers():
    """Retrieve 24h ticker statistics strictly for Bitcoin (BTC) and Ethereum (ETH) pairs."""
    try:
        tickers = await binance_service.get_top_tickers()
        return {
            "data": [t.model_dump(mode="json") for t in tickers],
            "error": None,
            "meta": _make_meta("binance_spot").model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/comparison")
async def get_crypto_comparison():
    """Retrieve relative strength, performance spread, and ETH/BTC ratio analytics."""
    try:
        comparison = await binance_service.get_pair_comparison()
        return {
            "data": comparison.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta("binance_analytics").model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/market-overview")
async def get_crypto_market_overview():
    """Retrieve macro Bitcoin and Ethereum metrics, dominance %, and sentiment."""
    try:
        overview = await binance_service.get_market_overview()
        return {
            "data": overview.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta("binance_market").model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def get_crypto_health():
    """Retrieve operational health, latency, and status of BTC & ETH subsystems."""
    try:
        health = market_health_tracker.get_health()
        return {
            "data": health.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta("system").model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/quote")
async def get_crypto_quote(symbol: str):
    """Retrieve detailed 24hr quote for a whitelisted crypto symbol (BTCUSDT, ETHUSDT, ETHBTC)."""
    clean_sym = _check_symbol(symbol)
    try:
        ticker = await binance_service.get_ticker(clean_sym)
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
    clean_sym = _check_symbol(symbol)
    try:
        candles = await binance_service.get_candles(clean_sym, timeframe, limit)
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
    market: str = Query(default="spot", description="Market type: spot or futures"),
):
    """Retrieve real-time order book depth with sequence verification and spread analysis."""
    clean_sym = _check_symbol(symbol)
    market_clean = market.lower()
    if market_clean not in ("spot", "futures"):
        market_clean = "spot"
    try:
        orderbook = await binance_service.get_order_book(clean_sym, limit, market_type=market_clean)
        return {
            "data": orderbook.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta(f"binance_depth_{market_clean}").model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/derivatives")
async def get_crypto_derivatives(symbol: str):
    """Retrieve live funding rate, countdown timer, open interest, and spot-futures Basis."""
    clean_sym = _check_symbol(symbol)
    try:
        derivs = await binance_service.get_derivatives_data(clean_sym)
        return {
            "data": derivs.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta("binance_futures").model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
