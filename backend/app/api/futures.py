"""
Futures Analytics API — Sections 45 through 50
Exposes Term Structure (Contango/Backwardation), Open Interest Buildup, and Expiry Rollover analytics.
Enforces The Truth of Wall: Never fabricates synthetic futures contracts or fake basis when broker data is unavailable.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.envelope import envelope
from app.models.market import DataStatus
from app.services.market_service import MarketService

router = APIRouter(prefix="/api/v1/futures", tags=["futures"])
market_service = MarketService()

_PROVIDER = "futures_engine"


@router.get("/{symbol}/overview")
async def get_futures_overview(symbol: str):
    underlying = symbol.upper().replace(" 50", "")
    try:
        quote = await market_service.get_quote(underlying)
        spot_price = quote.ltp if (quote and quote.ltp > 0) else None
    except Exception:
        spot_price = None

    is_live = spot_price is not None and spot_price > 0

    data = {
        "underlying": underlying,
        "spot_price": spot_price,
        "near_future_price": None,
        "basis_pts": None,
        "term_structure": {
            "underlying": underlying,
            "curve_state": "UNAVAILABLE",
            "contracts": [],
        },
        "buildup": {
            "underlying": underlying,
            "buildup_type": "UNAVAILABLE",
            "price_change_pct": 0.0,
            "oi_change_pct": 0.0,
            "interpretation": "Authentic broker futures data offline or unavailable.",
        },
        "rollover": {
            "underlying": underlying,
            "rollover_percent": None,
            "rollover_pace": "UNAVAILABLE",
            "previous_month_rollover": None,
        },
    }
    return envelope(data, provider=_PROVIDER, status=DataStatus.LIVE if is_live else DataStatus.OFFLINE)


@router.get("/{symbol}/term-structure")
async def get_term_structure(symbol: str):
    underlying = symbol.upper().replace(" 50", "")
    data = {
        "underlying": underlying,
        "curve_state": "UNAVAILABLE",
        "contracts": [],
    }
    return envelope(data, provider=_PROVIDER, status=DataStatus.OFFLINE)


@router.get("/{symbol}/buildup")
async def get_oi_buildup(symbol: str):
    underlying = symbol.upper().replace(" 50", "")
    data = {
        "underlying": underlying,
        "buildup_type": "UNAVAILABLE",
        "price_change_pct": 0.0,
        "oi_change_pct": 0.0,
        "interpretation": "Authentic broker futures data offline or unavailable.",
    }
    return envelope(data, provider=_PROVIDER, status=DataStatus.OFFLINE)


@router.get("/{symbol}/rollover")
async def get_rollover(symbol: str):
    underlying = symbol.upper().replace(" 50", "")
    data = {
        "underlying": underlying,
        "rollover_percent": None,
        "rollover_pace": "UNAVAILABLE",
        "previous_month_rollover": None,
    }
    return envelope(data, provider=_PROVIDER, status=DataStatus.OFFLINE)
