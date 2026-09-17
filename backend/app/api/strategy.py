"""
Strategy Engine API — Sections 61 through 70
Exposes Strategy Builder, Templates, Payoff Curve calculation, and Multi-factor Strategy Scanner.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.api.envelope import envelope

router = APIRouter(prefix="/api/v1/strategy", tags=["strategy"])

_PROVIDER = "strategy_engine"


TEMPLATES = [
    {"id": "bull_call_spread", "name": "Bull Call Spread", "category": "DIRECTIONAL_BULLISH", "legs_count": 2, "description": "Buy ATM Call, Sell OTM Call"},
    {"id": "bear_put_spread", "name": "Bear Put Spread", "category": "DIRECTIONAL_BEARISH", "legs_count": 2, "description": "Buy ATM Put, Sell OTM Put"},
    {"id": "short_straddle", "name": "Short Straddle", "category": "NON_DIRECTIONAL_INCOME", "legs_count": 2, "description": "Sell ATM Call + ATM Put"},
    {"id": "short_strangle", "name": "Short Strangle", "category": "NON_DIRECTIONAL_INCOME", "legs_count": 2, "description": "Sell OTM Call + OTM Put"},
    {"id": "iron_condor", "name": "Iron Condor", "category": "DEFINED_RISK_INCOME", "legs_count": 4, "description": "Bear Call Spread + Bull Put Spread"},
    {"id": "iron_butterfly", "name": "Iron Butterfly", "category": "DEFINED_RISK_INCOME", "legs_count": 4, "description": "Short Straddle with OTM wings"},
    {"id": "calendar_spread", "name": "Calendar Spread", "category": "TIME_DECAY", "legs_count": 2, "description": "Sell near expiry, Buy far expiry"},
    {"id": "ratio_spread", "name": "Call Ratio Spread", "category": "VOLATILITY_SKEW", "legs_count": 3, "description": "Buy 1 ATM Call, Sell 2 OTM Calls"},
]


class StrategyLeg(BaseModel):
    id: Optional[str] = None
    option_type: str
    side: str
    strike: float
    quantity: int
    price: float
    iv: Optional[float] = 0.15
    expiry: Optional[str] = None
    lot_size: Optional[int] = 75


class PayoffRequest(BaseModel):
    underlying: str
    spot_price: float
    expiry: Optional[str] = None
    legs: List[StrategyLeg]


def _compute_payoff(spot_price: float, legs: List[StrategyLeg]) -> List[Dict[str, float]]:
    step = spot_price * 0.005
    prices = [spot_price + (i - 15) * step for i in range(31)]
    curve = []
    for p in prices:
        total_pnl = 0.0
        for leg in legs:
            lot = leg.lot_size or 75
            qty = leg.quantity * lot
            if leg.option_type == "CE":
                intrinsic = max(0.0, p - leg.strike)
            else:
                intrinsic = max(0.0, leg.strike - p)
            if leg.side == "BUY":
                leg_pnl = (intrinsic - leg.price) * qty
            else:
                leg_pnl = (leg.price - intrinsic) * qty
            total_pnl += leg_pnl
        curve.append({"spot": round(p, 2), "pnl": round(total_pnl, 2)})
    return curve


@router.get("/templates")
async def get_templates():
    return envelope(TEMPLATES, provider=_PROVIDER)


@router.post("/build-template")
async def build_template(template_id: str = Query(...), symbol: str = Query(default="NIFTY")):
    """Build a template strategy off the LIVE FYERS spot.

    Truth-of-Wall: premiums/quantities are caller-supplied estimation inputs
    for payoff math; the spot and strikes come from the real feed. With no
    live quote this endpoint fails closed (404) instead of fabricating a
    strategy on a hardcoded spot.
    """
    from app.services.market_service import MarketService
    from fastapi import HTTPException

    underlying = symbol.upper().replace(" 50", "")
    try:
        quote = await MarketService().get_quote(symbol.upper())
    except Exception:
        quote = None
    spot = float(quote.ltp) if quote is not None and quote.ltp and quote.ltp > 0 else None
    if spot is None:
        raise HTTPException(
            status_code=503,
            detail=f"No live FYERS spot for {underlying} — template strategies require real market data (no fabricated spot).",
        )

    # Premiums are estimation placeholders the caller is expected to replace —
    # they only shape the payoff curve, never claim to be market prices.
    est_atm_premium = round(spot * 0.0057, 2)
    est_otm_premium = round(est_atm_premium * 0.32, 2)
    legs = [
        StrategyLeg(id="leg_1", option_type="CE", side="BUY", strike=spot, quantity=1, price=est_atm_premium, expiry=None, lot_size=75),
        StrategyLeg(id="leg_2", option_type="CE", side="SELL", strike=spot + 300, quantity=1, price=est_otm_premium, expiry=None, lot_size=75),
    ]
    payoff = _compute_payoff(spot, legs)
    debit = (est_atm_premium - est_otm_premium)
    width = 300.0
    data = {
        "template_id": template_id,
        "underlying": underlying,
        "spot_price": spot,
        "legs": [l.model_dump() for l in legs],
        "premium_note": "Premiums are estimation inputs for payoff shape only — replace with live chain premiums before trading.",
        "max_profit": round((width - debit) * 75, 2),
        "max_loss": round(debit * 75, 2),
        "risk_reward": round((width - debit) / debit, 2) if debit > 0 else None,
        "payoff_curve": payoff,
    }
    return envelope(data, provider=_PROVIDER)


@router.post("/payoff")
async def calculate_payoff(payload: PayoffRequest):
    curve = _compute_payoff(payload.spot_price, payload.legs)
    data = {
        "underlying": payload.underlying,
        "spot_price": payload.spot_price,
        "payoff_curve": curve,
        "legs_count": len(payload.legs),
    }
    return envelope(data, provider=_PROVIDER)


@router.get("/scanner")
async def get_strategy_scanner(min_pop: float = Query(default=20.0)):
    """Multi-factor strategy scanner.

    Truth-of-Wall: no fabricated recommendations. The historical response
    served invented "STRONG_BUY" entries with made-up PoP/ROI numbers. A real
    scanner requires live option-chain analytics; until that exists this
    returns an honest empty result with the limitation stated.
    """
    data: list[dict] = []
    return envelope(
        {
            "scans": data,
            "count": 0,
            "limitation": "Strategy scanner not yet wired to live option-chain analytics — no recommendations are fabricated (Truth of Wall).",
        },
        provider=_PROVIDER,
    )
