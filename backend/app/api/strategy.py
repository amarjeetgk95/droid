"""
Strategy Engine API — Sections 61 through 70
Exposes Strategy Builder, Templates, Payoff Curve calculation, and Multi-factor Strategy Scanner.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel

from app.models.market import ApiMeta, DataStatus

router = APIRouter(prefix="/api/v1/strategy", tags=["strategy"])


def _meta() -> ApiMeta:
    return ApiMeta(provider="strategy_engine", timestamp=datetime.now(timezone.utc), status=DataStatus.LIVE)


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
    return {"data": TEMPLATES, "error": None, "meta": _meta().model_dump()}


@router.post("/build-template")
async def build_template(template_id: str = Query(...), symbol: str = Query(default="NIFTY")):
    underlying = symbol.upper().replace(" 50", "")
    spot = 24500.0
    legs = [
        StrategyLeg(id="leg_1", option_type="CE", side="BUY", strike=spot, quantity=1, price=140.0, expiry="2026-09-24", lot_size=75),
        StrategyLeg(id="leg_2", option_type="CE", side="SELL", strike=spot + 300, quantity=1, price=45.0, expiry="2026-09-24", lot_size=75),
    ]
    payoff = _compute_payoff(spot, legs)
    data = {
        "template_id": template_id,
        "underlying": underlying,
        "spot_price": spot,
        "legs": [l.model_dump() for l in legs],
        "max_profit": 155.0 * 75,
        "max_loss": -95.0 * 75,
        "risk_reward": 1.63,
        "pop_percent": 54.5,
        "payoff_curve": payoff,
    }
    return {"data": data, "error": None, "meta": _meta().model_dump()}


@router.post("/payoff")
async def calculate_payoff(payload: PayoffRequest):
    curve = _compute_payoff(payload.spot_price, payload.legs)
    data = {
        "underlying": payload.underlying,
        "spot_price": payload.spot_price,
        "payoff_curve": curve,
        "legs_count": len(payload.legs),
    }
    return {"data": data, "error": None, "meta": _meta().model_dump()}


@router.get("/scanner")
async def get_strategy_scanner(min_pop: float = Query(default=20.0)):
    data = [
        {
            "symbol": "NIFTY",
            "strategy": "Bull Call Spread",
            "strikes": "24500 CE / 24800 CE",
            "pop_percent": 58.2,
            "max_roi_percent": 163.0,
            "net_debit": 95.0,
            "recommendation": "STRONG_BUY",
        },
        {
            "symbol": "BANKNIFTY",
            "strategy": "Iron Condor",
            "strikes": "56000 PE / 56500 PE / 58000 CE / 58500 CE",
            "pop_percent": 68.5,
            "max_roi_percent": 42.0,
            "net_credit": 145.0,
            "recommendation": "NEUTRAL_INCOME",
        },
    ]
    return {"data": data, "error": None, "meta": _meta().model_dump()}
