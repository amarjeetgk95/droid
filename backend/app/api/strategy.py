"""
Strategy Engine API — Sections 61 through 70
Exposes Strategy Builder, Templates, Payoff Curve calculation, and Multi-factor Strategy Scanner.

Truth-of-Wall contract for this module:
- Strikes, lot sizes and expiries come from the canonical contract config
  (`app.signals.contract_resolver.INDEX_CONTRACT_CONFIGS`) and the exchange
  calendar — templates never hardcode a strike offset or a lot size.
- Premiums are estimation inputs that only shape the payoff curve. They are
  labelled `premium_source: "ESTIMATED"` and never claim to be market prices;
  the caller replaces them with live chain quotes before trading.
- Payoff math is the terminal *expiry intrinsic* over the caller's own legs,
  with the curve's price axis including every leg strike (kinks) so sampled
  extremes are exact. Structures whose P&L is not an expiry-intrinsic function
  (calendar spreads) return an empty curve plus an explicit limitation instead
  of an invented number.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Callable, Dict, List, Literal, NamedTuple, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.envelope import envelope

router = APIRouter(prefix="/api/v1/strategy", tags=["strategy"])

_PROVIDER = "strategy_engine"

# Premium shape model for template scaffolds (estimation inputs only).
_ATM_PREMIUM_PCT = 0.0057
_PREMIUM_STEP_DECAY = 0.82

# Template offsets, expressed as a fraction of spot and snapped to the
# instrument's own strike grid: the same template lands on tradable strikes for
# NIFTY (50-point grid), BANKNIFTY and SENSEX (100-point grid).
_SPREAD_WIDTH_PCT = 0.007
_WING_NEAR_PCT = 0.008
_WING_FAR_PCT = 0.020


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

_TEMPLATE_NAMES = {row["id"]: row["name"] for row in TEMPLATES}


class StrategyLeg(BaseModel):
    id: Optional[str] = None
    option_type: Literal["CE", "PE"]
    side: Literal["BUY", "SELL"]
    strike: float = Field(gt=0)
    quantity: int = Field(gt=0)
    price: float = Field(ge=0)
    iv: Optional[float] = 0.15
    expiry: Optional[str] = None
    # None => resolve from the payload's underlying. The old 75 default silently
    # priced BANKNIFTY (30) and SENSEX (10) legs at 2.5x-7.5x their real size.
    lot_size: Optional[int] = Field(default=None, gt=0)


class PayoffRequest(BaseModel):
    underlying: str
    spot_price: float = Field(gt=0)
    expiry: Optional[str] = None
    legs: List[StrategyLeg] = Field(min_length=1)


class _ContractProfile(NamedTuple):
    underlying: str
    strike_step: float
    lot_size: int
    expiry: date
    expiry_type: str


class _BuildContext(NamedTuple):
    profile: _ContractProfile
    spot: float
    far_expiry: Optional[date]


class _BuiltStructure(NamedTuple):
    legs: List[StrategyLeg]
    # "EXPIRY_INTRINSIC" when the curve is a real terminal payoff;
    # "UNMODELLED" when this engine cannot price the structure honestly.
    payoff_model: Literal["EXPIRY_INTRINSIC", "UNMODELLED"]
    limitation: Optional[str] = None


def _contract_profile(symbol: str) -> _ContractProfile:
    """Canonical contract facts for an approved underlying (single source of truth)."""
    from app.signals.contract_resolver import INDEX_CONTRACT_CONFIGS, resolve_nearest_expiry, validate_underlying

    underlying = validate_underlying(symbol)  # normalises "NIFTY 50", "BANK NIFTY", ...
    cfg = INDEX_CONTRACT_CONFIGS[underlying]
    expiry, expiry_type = resolve_nearest_expiry(underlying)
    return _ContractProfile(
        underlying=underlying,
        strike_step=float(cfg["strike_interval"]),
        lot_size=int(cfg["lot_size"]),
        expiry=expiry,
        expiry_type=expiry_type,
    )


def _default_lot_size(underlying: str) -> int:
    """Lot size used for legs that omit one (never a blanket 75)."""
    from app.signals.transaction_costs import resolve_lot_size_for_underlying

    return resolve_lot_size_for_underlying(underlying)


def _snap_to_grid(value: float, step: float) -> float:
    return round(round(value / step) * step, 2)


def _steps_away(spot: float, pct: float, step: float) -> int:
    """Offset in whole strike steps, never fewer than one (keeps wings distinct)."""
    return max(1, int(round(spot * pct / step)))


def _est_premium(spot: float, steps_away: int) -> float:
    """Estimation input for payoff shape only — not a market price."""
    atm = spot * _ATM_PREMIUM_PCT
    return round(atm * (_PREMIUM_STEP_DECAY**steps_away), 2)


def _leg(
    leg_id: str,
    option_type: Literal["CE", "PE"],
    side: Literal["BUY", "SELL"],
    strike: float,
    spot: float,
    strike_step: float,
    lot_size: int,
    expiry: date,
    quantity: int = 1,
) -> StrategyLeg:
    steps_away = int(round(abs(strike - _snap_to_grid(spot, strike_step)) / strike_step))
    return StrategyLeg(
        id=leg_id,
        option_type=option_type,
        side=side,
        strike=strike,
        quantity=quantity,
        price=_est_premium(spot, steps_away),
        expiry=expiry.isoformat(),
        lot_size=lot_size,
    )


def _build_bull_call_spread(ctx: _BuildContext) -> _BuiltStructure:
    profile, spot = ctx.profile, ctx.spot
    step = profile.strike_step
    atm = _snap_to_grid(spot, step)
    short_strike = atm + _steps_away(spot, _SPREAD_WIDTH_PCT, step) * step
    return _BuiltStructure(
        legs=[
            _leg("leg_1", "CE", "BUY", atm, spot, step, profile.lot_size, profile.expiry),
            _leg("leg_2", "CE", "SELL", short_strike, spot, step, profile.lot_size, profile.expiry),
        ],
        payoff_model="EXPIRY_INTRINSIC",
    )


def _build_bear_put_spread(ctx: _BuildContext) -> _BuiltStructure:
    profile, spot = ctx.profile, ctx.spot
    step = profile.strike_step
    atm = _snap_to_grid(spot, step)
    short_strike = atm - _steps_away(spot, _SPREAD_WIDTH_PCT, step) * step
    return _BuiltStructure(
        legs=[
            _leg("leg_1", "PE", "BUY", atm, spot, step, profile.lot_size, profile.expiry),
            _leg("leg_2", "PE", "SELL", short_strike, spot, step, profile.lot_size, profile.expiry),
        ],
        payoff_model="EXPIRY_INTRINSIC",
    )


def _build_short_straddle(ctx: _BuildContext) -> _BuiltStructure:
    profile, spot = ctx.profile, ctx.spot
    atm = _snap_to_grid(spot, profile.strike_step)
    return _BuiltStructure(
        legs=[
            _leg("leg_1", "CE", "SELL", atm, spot, profile.strike_step, profile.lot_size, profile.expiry),
            _leg("leg_2", "PE", "SELL", atm, spot, profile.strike_step, profile.lot_size, profile.expiry),
        ],
        payoff_model="EXPIRY_INTRINSIC",
    )


def _build_short_strangle(ctx: _BuildContext) -> _BuiltStructure:
    profile, spot = ctx.profile, ctx.spot
    step = profile.strike_step
    atm = _snap_to_grid(spot, step)
    width = _steps_away(spot, _WING_NEAR_PCT, step) * step
    return _BuiltStructure(
        legs=[
            _leg("leg_1", "CE", "SELL", atm + width, spot, step, profile.lot_size, profile.expiry),
            _leg("leg_2", "PE", "SELL", atm - width, spot, step, profile.lot_size, profile.expiry),
        ],
        payoff_model="EXPIRY_INTRINSIC",
    )


def _build_iron_condor(ctx: _BuildContext) -> _BuiltStructure:
    profile, spot = ctx.profile, ctx.spot
    step = profile.strike_step
    atm = _snap_to_grid(spot, step)
    short_width = _steps_away(spot, _WING_NEAR_PCT, step) * step
    long_width = _steps_away(spot, _WING_FAR_PCT, step) * step
    return _BuiltStructure(
        legs=[
            _leg("leg_1", "PE", "BUY", atm - long_width, spot, step, profile.lot_size, profile.expiry),
            _leg("leg_2", "PE", "SELL", atm - short_width, spot, step, profile.lot_size, profile.expiry),
            _leg("leg_3", "CE", "SELL", atm + short_width, spot, step, profile.lot_size, profile.expiry),
            _leg("leg_4", "CE", "BUY", atm + long_width, spot, step, profile.lot_size, profile.expiry),
        ],
        payoff_model="EXPIRY_INTRINSIC",
    )


def _build_iron_butterfly(ctx: _BuildContext) -> _BuiltStructure:
    profile, spot = ctx.profile, ctx.spot
    step = profile.strike_step
    atm = _snap_to_grid(spot, step)
    wing = _steps_away(spot, _WING_FAR_PCT, step) * step
    return _BuiltStructure(
        legs=[
            _leg("leg_1", "PE", "BUY", atm - wing, spot, step, profile.lot_size, profile.expiry),
            _leg("leg_2", "PE", "SELL", atm, spot, step, profile.lot_size, profile.expiry),
            _leg("leg_3", "CE", "SELL", atm, spot, step, profile.lot_size, profile.expiry),
            _leg("leg_4", "CE", "BUY", atm + wing, spot, step, profile.lot_size, profile.expiry),
        ],
        payoff_model="EXPIRY_INTRINSIC",
    )


def _build_ratio_spread(ctx: _BuildContext) -> _BuiltStructure:
    profile, spot = ctx.profile, ctx.spot
    step = profile.strike_step
    atm = _snap_to_grid(spot, step)
    short_strike = atm + _steps_away(spot, _SPREAD_WIDTH_PCT, step) * step
    return _BuiltStructure(
        legs=[
            _leg("leg_1", "CE", "BUY", atm, spot, step, profile.lot_size, profile.expiry),
            _leg("leg_2", "CE", "SELL", short_strike, spot, step, profile.lot_size, profile.expiry, quantity=2),
        ],
        payoff_model="EXPIRY_INTRINSIC",
    )


def _build_calendar_spread(ctx: _BuildContext) -> _BuiltStructure:
    """Sell the near expiry, buy the far expiry at the same strike.

    The P&L of a calendar is driven by the far leg's remaining time value at the
    near expiry — it is NOT the terminal intrinsic payoff this engine computes,
    so the curve comes back empty with the limitation stated rather than a
    wrong number.
    """
    profile, spot = ctx.profile, ctx.spot
    atm = _snap_to_grid(spot, profile.strike_step)
    if ctx.far_expiry is None:
        return _BuiltStructure(
            legs=[],
            payoff_model="UNMODELLED",
            limitation="Far expiry could not be resolved from the exchange calendar — no strategy built.",
        )
    return _BuiltStructure(
        legs=[
            _leg("leg_1", "CE", "SELL", atm, spot, profile.strike_step, profile.lot_size, profile.expiry),
            _leg("leg_2", "CE", "BUY", atm, spot, profile.strike_step, profile.lot_size, ctx.far_expiry),
        ],
        payoff_model="UNMODELLED",
        limitation=(
            "Calendar P&L needs the far leg's time value at the near expiry (term-structure model); "
            "this engine only computes terminal intrinsic payoff, so no payoff curve or max profit/loss is reported."
        ),
    )


_TEMPLATE_BUILDERS: Dict[str, Callable[[_BuildContext], _BuiltStructure]] = {
    "bull_call_spread": _build_bull_call_spread,
    "bear_put_spread": _build_bear_put_spread,
    "short_straddle": _build_short_straddle,
    "short_strangle": _build_short_strangle,
    "iron_condor": _build_iron_condor,
    "iron_butterfly": _build_iron_butterfly,
    "calendar_spread": _build_calendar_spread,
    "ratio_spread": _build_ratio_spread,
}


def _payoff_axis(spot_price: float, legs: List[StrategyLeg]) -> List[float]:
    """Uniform ±7.5% grid plus every leg strike, so payoff kinks are sampled exactly."""
    step = spot_price * 0.005
    prices = {round(spot_price + (i - 15) * step, 2) for i in range(31)}
    prices.update(round(float(leg.strike), 2) for leg in legs)
    return sorted(prices)


def _compute_payoff(
    spot_price: float,
    legs: List[StrategyLeg],
    default_lot_size: int,
) -> List[Dict[str, float]]:
    """Terminal intrinsic payoff at expiry over caller-supplied legs."""
    curve: List[Dict[str, float]] = []
    for p in _payoff_axis(spot_price, legs):
        total_pnl = 0.0
        for leg in legs:
            lot = leg.lot_size or default_lot_size
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


def _tail_slopes(legs: List[StrategyLeg], default_lot_size: int) -> tuple[float, float]:
    """d(pnl)/d(spot) far above the highest strike and far below the lowest."""
    upper = 0.0  # spot -> +inf
    lower = 0.0  # spot -> 0
    for leg in legs:
        qty = leg.quantity * (leg.lot_size or default_lot_size)
        sign = 1.0 if leg.side == "BUY" else -1.0
        if leg.option_type == "CE":
            upper += sign * qty
        else:
            # Long put gains as spot falls, so its pnl slope vs spot is negative.
            lower -= sign * qty
    return upper, lower


def _expiry_groups(legs: List[StrategyLeg]) -> set:
    return {leg.expiry for leg in legs}


def _payoff_bounds(
    curve: List[Dict[str, float]],
    legs: List[StrategyLeg],
    default_lot_size: int,
) -> tuple[Optional[float], Optional[float], float, bool]:
    """(max_profit, max_loss, risk_reward, defined_risk) from the real legs.

    Unbounded tails are reported as None (never as a sampled-grid number that
    hides an uncapped loss).
    """
    pnls = [point["pnl"] for point in curve]
    if not pnls:
        return None, None, 0.0, True
    peak, trough = max(pnls), min(pnls)
    upper_slope, lower_slope = _tail_slopes(legs, default_lot_size)
    profit_unbounded = upper_slope > 0 or lower_slope < 0
    loss_unbounded = upper_slope < 0 or lower_slope > 0
    max_profit = None if profit_unbounded else round(peak, 2)
    max_loss = None if loss_unbounded else round(trough, 2)
    defined_risk = not loss_unbounded
    risk_reward = 0.0
    if max_profit is not None and max_loss is not None and max_loss < 0:
        risk_reward = round(max_profit / abs(max_loss), 2)
    return max_profit, max_loss, risk_reward, defined_risk


@router.get("/templates")
async def get_templates():
    return envelope(TEMPLATES, provider=_PROVIDER)


@router.post("/build-template")
async def build_template(template_id: str = Query(...), symbol: str = Query(default="NIFTY")):
    """Build the requested template off the LIVE FYERS spot.

    Truth-of-Wall: premiums/quantities are caller-supplied estimation inputs for
    payoff math; the spot, strikes, lot sizes and expiries come from the real
    feed / canonical contract config. With no live quote this endpoint fails
    closed (503) instead of fabricating a strategy on a hardcoded spot.
    """
    from app.services.market_service import MarketService

    if template_id not in _TEMPLATE_BUILDERS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown template_id {template_id!r}. Known templates: {sorted(_TEMPLATE_BUILDERS)}.",
        )

    try:
        profile = _contract_profile(symbol)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        quote = await MarketService().get_quote(symbol.upper())
    except Exception:
        quote = None
    spot = float(quote.ltp) if quote is not None and quote.ltp and quote.ltp > 0 else None
    if spot is None:
        raise HTTPException(
            status_code=503,
            detail=f"No live FYERS spot for {profile.underlying} — template strategies require real market data (no fabricated spot).",
        )

    far_expiry: Optional[date] = None
    if template_id == "calendar_spread":
        from app.signals.contract_resolver import resolve_nearest_expiry

        try:
            far_expiry, _ = resolve_nearest_expiry(profile.underlying, ref_date=profile.expiry + timedelta(days=1))
        except Exception:
            far_expiry = None

    structure = _TEMPLATE_BUILDERS[template_id](_BuildContext(profile=profile, spot=spot, far_expiry=far_expiry))

    data: Dict[str, object] = {
        "template_id": template_id,
        "template_name": _TEMPLATE_NAMES.get(template_id, template_id),
        "underlying": profile.underlying,
        "spot_price": spot,
        "expiry": profile.expiry.isoformat(),
        "expiry_type": profile.expiry_type,
        "legs": [leg.model_dump() for leg in structure.legs],
        "payoff_model": structure.payoff_model,
        "premium_note": "Premiums are estimation inputs for payoff shape only — replace with live chain premiums before trading.",
        "premium_source": "ESTIMATED",
    }
    if far_expiry is not None:
        data["far_expiry"] = far_expiry.isoformat()
    if structure.limitation is not None:
        data["limitation"] = structure.limitation

    if structure.payoff_model == "EXPIRY_INTRINSIC" and structure.legs:
        payoff = _compute_payoff(spot, structure.legs, profile.lot_size)
        max_profit, max_loss, risk_reward, defined_risk = _payoff_bounds(payoff, structure.legs, profile.lot_size)
        data.update(
            {
                "payoff_curve": payoff,
                "max_profit": max_profit,
                "max_loss": max_loss,
                "risk_reward": risk_reward if risk_reward else None,
                "defined_risk": defined_risk,
                "lot_size": profile.lot_size,
                "breakeven_note": "Breakevens are where the payoff curve crosses zero; unbounded tails report null bounds.",
            }
        )
    else:
        data.update(
            {
                "payoff_curve": [],
                "max_profit": None,
                "max_loss": None,
                "risk_reward": None,
                "defined_risk": None,
                "lot_size": profile.lot_size,
            }
        )
    return envelope(data, provider=_PROVIDER)


@router.post("/payoff")
async def calculate_payoff(payload: PayoffRequest):
    default_lot_size = _default_lot_size(payload.underlying)
    curve = _compute_payoff(payload.spot_price, payload.legs, default_lot_size)
    max_profit, max_loss, risk_reward, defined_risk = _payoff_bounds(curve, payload.legs, default_lot_size)
    expiries = _expiry_groups(payload.legs)
    data: Dict[str, object] = {
        "underlying": payload.underlying,
        "spot_price": payload.spot_price,
        "expiry": payload.expiry,
        "payoff_curve": curve,
        "legs_count": len(payload.legs),
        "default_lot_size": default_lot_size,
        "max_profit": max_profit,
        "max_loss": max_loss,
        "risk_reward": risk_reward if risk_reward else None,
        "defined_risk": defined_risk,
    }
    if len(expiries) > 1:
        data["limitation"] = (
            "Legs carry different expiries — the curve is the terminal intrinsic payoff of every leg at one "
            "terminal spot, which is not how cross-expiry (calendar) P&L behaves."
        )
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
            "min_pop": min_pop,
            "limitation": "Strategy scanner not yet wired to live option-chain analytics — no recommendations are fabricated (Truth of Wall).",
        },
        provider=_PROVIDER,
    )
