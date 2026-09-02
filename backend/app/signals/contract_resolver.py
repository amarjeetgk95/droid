"""
Institutional Instrument Master & Contract Resolver
Enforces:
  - Approved Universe: NIFTY, BANKNIFTY, SENSEX only
  - Dynamic lot size & tick size resolution
  - Expiry calculation (Weekly/Monthly/Expiring Today)
  - Strike step mapping & CE/PE contract resolution
  - Price tick quantization & Lot-aware position sizing
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal, Optional
from pydantic import BaseModel, Field

APPROVED_UNDERLYINGS = {"NIFTY", "BANKNIFTY", "SENSEX"}

# Dynamic Contract specifications baseline (versioned)
INDEX_CONTRACT_CONFIGS: dict[str, dict] = {
    "NIFTY": {
        "underlying": "NIFTY",
        "display_name": "NIFTY 50",
        "exchange": "NSE",
        "fyers_index_symbol": "NSE:NIFTY50-INDEX",
        "fyers_opt_prefix": "NSE:NIFTY",
        "strike_interval": Decimal("50.0"),
        "lot_size": 75,
        "tick_size": Decimal("0.05"),
        "contract_multiplier": Decimal("1.0"),
        "weekly_expiry_day": 3,  # Thursday
        "monthly_expiry_day": 3,
    },
    "BANKNIFTY": {
        "underlying": "BANKNIFTY",
        "display_name": "NIFTY Bank",
        "exchange": "NSE",
        "fyers_index_symbol": "NSE:NIFTYBANK-INDEX",
        "fyers_opt_prefix": "NSE:BANKNIFTY",
        "strike_interval": Decimal("100.0"),
        "lot_size": 30,
        "tick_size": Decimal("0.05"),
        "contract_multiplier": Decimal("1.0"),
        "weekly_expiry_day": 2,  # Wednesday
        "monthly_expiry_day": 3,
    },
    "SENSEX": {
        "underlying": "SENSEX",
        "display_name": "BSE SENSEX",
        "exchange": "BSE",
        "fyers_index_symbol": "BSE:SENSEX-INDEX",
        "fyers_opt_prefix": "BSE:SENSEX",
        "strike_interval": Decimal("100.0"),
        "lot_size": 10,
        "tick_size": Decimal("0.05"),
        "contract_multiplier": Decimal("1.0"),
        "weekly_expiry_day": 4,  # Friday
        "monthly_expiry_day": 4,
    },
}


class InstrumentMaster(BaseModel):
    instrument_id: str
    broker_symbol: str
    underlying: Literal["NIFTY", "BANKNIFTY", "SENSEX"]
    exchange: Literal["NSE", "BSE"]
    instrument_type: Literal["INDEX", "OPTION"]
    option_type: Optional[Literal["CE", "PE"]] = None
    strike: Optional[Decimal] = None
    expiry_date: Optional[date] = None
    expiry_type: Optional[Literal["WEEKLY", "MONTHLY", "EXPIRING_TODAY"]] = None
    lot_size: int
    tick_size: Decimal
    contract_multiplier: Decimal = Decimal("1.0")
    strike_interval: Decimal
    contract_version: str = "v1.0"
    active: bool = True


def validate_underlying(underlying: str) -> str:
    """Validate that instrument is within the approved universe."""
    clean = underlying.strip().upper()
    if clean in ("NIFTY 50", "NIFTY50", "CNX NIFTY"):
        clean = "NIFTY"
    elif clean in ("NIFTY BANK", "NIFTYBANK", "BANK NIFTY", "BANK"):
        clean = "BANKNIFTY"
    elif clean in ("BSE SENSEX", "SENSEX 30", "SENSEX30"):
        clean = "SENSEX"
    if clean not in APPROVED_UNDERLYINGS:
        raise ValueError(f"Instrument '{underlying}' is forbidden. Approved universe: {sorted(list(APPROVED_UNDERLYINGS))}")
    return clean


def normalize_price(price: Decimal | float | int, tick_size: Decimal = Decimal("0.05")) -> Decimal:
    """Normalize a price to the exchange tick size grid."""
    d_price = Decimal(str(price))
    d_tick = Decimal(str(tick_size))
    if d_tick <= Decimal("0"):
        return d_price
    steps = (d_price / d_tick).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return (steps * d_tick).quantize(Decimal("0.05"))


def resolve_nearest_expiry(underlying: str, ref_date: Optional[date] = None) -> tuple[date, Literal["WEEKLY", "MONTHLY", "EXPIRING_TODAY"]]:
    """Calculate the nearest valid option expiry for an approved underlying."""
    u = validate_underlying(underlying)
    today = ref_date or datetime.now(timezone.utc).date()
    cfg = INDEX_CONTRACT_CONFIGS[u]
    target_weekday = cfg["weekly_expiry_day"]
    
    days_ahead = target_weekday - today.weekday()
    if days_ahead < 0:
        days_ahead += 7
    expiry = today + timedelta(days=days_ahead)
    
    if expiry == today:
        exp_type: Literal["WEEKLY", "MONTHLY", "EXPIRING_TODAY"] = "EXPIRING_TODAY"
    else:
        next_week = expiry + timedelta(days=7)
        if next_week.month != expiry.month:
            exp_type = "MONTHLY"
        else:
            exp_type = "WEEKLY"
    return expiry, exp_type


def resolve_atm_strike(underlying: str, spot_price: Decimal | float) -> Decimal:
    """Calculate nearest ATM strike based on standard strike step."""
    u = validate_underlying(underlying)
    cfg = INDEX_CONTRACT_CONFIGS[u]
    step = cfg["strike_interval"]
    d_spot = Decimal(str(spot_price))
    steps = (d_spot / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return steps * step


def resolve_option_contract(
    underlying: str,
    spot_price: Decimal | float,
    option_type: Literal["CE", "PE"],
    strike_offset: int = 0,
    ref_date: Optional[date] = None,
) -> InstrumentMaster:
    """Resolve authoritative InstrumentMaster for an option contract."""
    u = validate_underlying(underlying)
    cfg = INDEX_CONTRACT_CONFIGS[u]
    atm_strike = resolve_atm_strike(u, spot_price)
    step = cfg["strike_interval"]
    
    if option_type == "CE":
        selected_strike = atm_strike + (Decimal(strike_offset) * step)
    else:
        selected_strike = atm_strike - (Decimal(strike_offset) * step)
        
    expiry, expiry_type = resolve_nearest_expiry(u, ref_date)
    
    strike_int = int(selected_strike)
    yy = str(expiry.year)[-2:]
    mm = expiry.strftime("%b").upper()
    dd = f"{expiry.day:02d}"
    
    fyers_symbol = f"{cfg['fyers_opt_prefix']}{yy}{mm}{dd}{strike_int}{option_type}"
    instr_id = f"{u}_{expiry.strftime('%Y%m%d')}_{strike_int}_{option_type}"
    
    return InstrumentMaster(
        instrument_id=instr_id,
        broker_symbol=fyers_symbol,
        underlying=u,
        exchange=cfg["exchange"],
        instrument_type="OPTION",
        option_type=option_type,
        strike=selected_strike,
        expiry_date=expiry,
        expiry_type=expiry_type,
        lot_size=cfg["lot_size"],
        tick_size=cfg["tick_size"],
        contract_multiplier=cfg["contract_multiplier"],
        strike_interval=step,
        contract_version="v1.0",
        active=True,
    )


def calculate_position_sizing(
    available_capital: Decimal | float,
    risk_percent: float,
    entry_price: Decimal | float,
    stop_loss: Decimal | float,
    lot_size: int,
    contract_multiplier: Decimal = Decimal("1.0"),
    max_lots: int = 50,
) -> dict:
    d_cap = Decimal(str(available_capital))
    d_risk_pct = Decimal(str(risk_percent)) / Decimal("100")
    d_entry = Decimal(str(entry_price))
    d_sl = Decimal(str(stop_loss))
    d_lot = Decimal(str(lot_size))
    d_mult = Decimal(str(contract_multiplier))
    
    risk_points = abs(d_entry - d_sl)
    if risk_points <= Decimal("0"):
        return {"lots": 0, "quantity": 0, "risk_capital": 0.0, "risk_per_lot": 0.0, "allowed": False, "reason": "Zero risk points"}
        
    risk_per_lot = risk_points * d_lot * d_mult
    risk_capital = d_cap * d_risk_pct
    
    raw_lots = int(math.floor(risk_capital / risk_per_lot)) if risk_per_lot > 0 else 0
    final_lots = max(0, min(raw_lots, max_lots))
    final_qty = final_lots * lot_size
    
    return {
        "lots": final_lots,
        "quantity": final_qty,
        "lot_size": lot_size,
        "risk_capital": float(risk_capital.quantize(Decimal("0.01"))),
        "risk_per_lot": float(risk_per_lot.quantize(Decimal("0.01"))),
        "risk_points": float(risk_points.quantize(Decimal("0.01"))),
        "allowed": final_lots >= 1,
        "reason": "OK" if final_lots >= 1 else f"Insufficient risk capital (requires ₹{risk_per_lot:,.2f} for 1 lot)",
    }
