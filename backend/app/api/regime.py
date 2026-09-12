from fastapi import APIRouter
from app.api.envelope import envelope
from app.models.market import DataStatus
from app.services.regime_service import regime_service

router = APIRouter(prefix="/api/v1/regime", tags=["regime"])

_PROVIDER = "regime_quant_engine"


@router.get("/{symbol}/overview")
async def get_market_regime_overview(symbol: str):
    """Retrieve full Market Regime diagnosis, technical indicators, and key levels."""
    overview = await regime_service.classify_market_regime(symbol)
    return envelope(overview, provider=_PROVIDER, status=DataStatus.OFFLINE)


@router.get("/{symbol}/pivots")
async def get_key_levels(symbol: str):
    """Retrieve Support & Resistance key levels (Classic, Fibonacci, Camarilla, Value Area)."""
    levels = await regime_service.get_key_levels(symbol)
    return envelope(levels, provider=_PROVIDER, status=DataStatus.OFFLINE)


@router.get("/{symbol}/indicators")
async def get_technical_indicators(symbol: str):
    """Retrieve institutional technical indicator suite (RSI, ADX, ATR, Bollinger, Supertrend)."""
    indicators = await regime_service.get_technical_indicators(symbol)
    return envelope(indicators, provider=_PROVIDER, status=DataStatus.OFFLINE)


@router.get("/vix-status")
async def get_vix_regime():
    """Retrieve India VIX volatility classification and option strategy bias."""
    vix_info = await regime_service.get_vix_regime()
    return envelope(vix_info, provider=_PROVIDER, status=DataStatus.OFFLINE)
