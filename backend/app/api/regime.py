from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from app.services.regime_service import regime_service
from app.models.market import ApiMeta, DataStatus

router = APIRouter(prefix="/api/v1/regime", tags=["regime"])


def _make_meta() -> ApiMeta:
    return ApiMeta(
        provider="regime_quant_engine",
        timestamp=datetime.now(timezone.utc),
        status=DataStatus.DEMO,
    )


@router.get("/{symbol}/overview")
async def get_market_regime_overview(symbol: str):
    """Retrieve full Market Regime diagnosis, technical indicators, and key levels."""
    try:
        overview = await regime_service.classify_market_regime(symbol)
        return {
            "data": overview.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/pivots")
async def get_key_levels(symbol: str):
    """Retrieve Support & Resistance key levels (Classic, Fibonacci, Camarilla, Value Area)."""
    try:
        levels = await regime_service.get_key_levels(symbol)
        return {
            "data": levels.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/indicators")
async def get_technical_indicators(symbol: str):
    """Retrieve institutional technical indicator suite (RSI, ADX, ATR, Bollinger, Supertrend)."""
    try:
        indicators = await regime_service.get_technical_indicators(symbol)
        return {
            "data": indicators.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vix-status")
async def get_vix_regime():
    """Retrieve India VIX volatility classification and option strategy bias."""
    try:
        vix_info = await regime_service.get_vix_regime()
        return {
            "data": vix_info.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
