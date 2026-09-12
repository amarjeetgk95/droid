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
from pydantic import BaseModel

IST = timezone(timedelta(hours=5, minutes=30))
APPROVED_UNDERLYINGS = {"NIFTY", "BANKNIFTY", "SENSEX"}

# FYERS v3 option symbology (authoritative: symbol master / fyers-skills):
#   Monthly: {EX}:{UNDERLYING}{YY}{MMM}{STRIKE}{CE|PE}      e.g. BSE:SENSEX26SEP75200PE
#   Weekly:  {EX}:{UNDERLYING}{YY}{M}{dd}{STRIKE}{CE|PE}    e.g. BSE:SENSEX26S1175200PE
# M is the single-letter month code (1-9, O, N, D). A full MMM on a weekly
# contract (e.g. ...26SEP1175200PE) is NOT a valid FYERS symbol (API -300).
FYERS_WEEKLY_MONTH_CODE: dict[int, str] = {
    1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8", 9: "9",
    10: "O", 11: "N", 12: "D",
}

# Dynamic Contract specifications baseline (versioned)
# SEBI Sep-2025 expiry harmonization (one weekly benchmark per exchange):
#   NSE NIFTY  -> Tuesday weeklies (incl. month-end Tuesday monthlies)
#   BSE SENSEX -> Thursday weeklies (incl. month-end Thursday monthlies)
#   BANKNIFTY  -> NO weeklies since Nov 2024; monthlies expire last Thursday.
# Python weekday(): Mon=0 ... Sun=6. Pre-2025 values (NIFTY Thu, SENSEX Fri)
# mint non-existent contracts — never revert without an exchange circular.
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
        "weekly_expiry_day": 1,  # Tuesday
        "monthly_expiry_day": 1,
        "has_weekly": True,
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
        "weekly_expiry_day": 3,  # Thursday (monthlies only — see has_weekly)
        "monthly_expiry_day": 3,
        "has_weekly": False,
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
        "weekly_expiry_day": 3,  # Thursday
        "monthly_expiry_day": 3,
        "has_weekly": True,
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
    # Provenance: "fyers_chain" when broker_symbol came from the live option
    # chain cache, "formula" when derived from weekday rules (offline).
    contract_source: str = "formula"
    live_premium: Optional[float] = None


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
    """Calculate the nearest valid option expiry for an approved underlying, adjusting for exchange holidays."""
    from app.services.calendar_service import calendar_service

    u = validate_underlying(underlying)
    now_ist = datetime.now(IST)
    today = ref_date or now_ist.date()
    cfg = INDEX_CONTRACT_CONFIGS[u]
    is_post_market = (now_ist.hour > 15) or (now_ist.hour == 15 and now_ist.minute >= 30)
    is_today = ref_date is None or ref_date == now_ist.date()

    if not cfg.get("has_weekly", True):
        # No weekly series: nearest expiry is the last monthly weekday
        # (e.g. BANKNIFTY -> last Thursday). Roll past months forward.
        year, month = today.year, today.month
        for _ in range(3):
            last_day = (date(year, month, 1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            while last_day.weekday() != cfg["monthly_expiry_day"]:
                last_day -= timedelta(days=1)
            expiry = calendar_service.adjust_expiry_if_holiday(last_day)
            if expiry > today or (expiry == today and not (is_today and is_post_market)):
                return expiry, "MONTHLY"
            month += 1
            if month > 12:
                month, year = 1, year + 1
        return expiry, "MONTHLY"

    target_weekday = cfg["weekly_expiry_day"]
    
    days_ahead = target_weekday - today.weekday()
    if days_ahead < 0:
        days_ahead += 7

    # If today is the target expiry day (days_ahead == 0), check current time.
    # If current IST time is >= 15:30 (market closed, session complete), the contract for today has expired.
    if days_ahead == 0:
        is_post_market = (now_ist.hour > 15) or (now_ist.hour == 15 and now_ist.minute >= 30)
        if (ref_date is None or ref_date == now_ist.date()) and is_post_market:
            days_ahead = 7

    tentative_expiry = today + timedelta(days=days_ahead)
    # Adjust for holidays: if scheduled expiry is a holiday/weekend, NSE rules move it backwards
    expiry = calendar_service.adjust_expiry_if_holiday(tentative_expiry)

    # If the adjusted holiday expiry has already passed relative to today, advance to next week
    is_today_post_market = ((now_ist.hour > 15) or (now_ist.hour == 15 and now_ist.minute >= 30)) and (ref_date is None or ref_date == now_ist.date())
    if expiry < today or (expiry == today and is_today_post_market):
        tentative_expiry = tentative_expiry + timedelta(days=7)
        expiry = calendar_service.adjust_expiry_if_holiday(tentative_expiry)
    
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
    exact_strike: Optional[Decimal | float] = None,
) -> InstrumentMaster:
    """Resolve authoritative InstrumentMaster for an option contract."""
    u = validate_underlying(underlying)
    cfg = INDEX_CONTRACT_CONFIGS[u]
    step = cfg["strike_interval"]

    if exact_strike is not None:
        selected_strike = Decimal(str(exact_strike))
    else:
        atm_strike = resolve_atm_strike(u, spot_price)
        if option_type == "CE":
            selected_strike = atm_strike + (Decimal(strike_offset) * step)
        else:
            selected_strike = atm_strike - (Decimal(strike_offset) * step)
        
    expiry, expiry_type = resolve_nearest_expiry(u, ref_date)
    
    strike_int = int(selected_strike)
    yy = str(expiry.year)[-2:]
    if expiry_type == "MONTHLY":
        # Monthly options carry no day component.
        date_part = f"{yy}{expiry.strftime('%b').upper()}"
    else:
        # Weekly / expiring-today: single-letter month code + zero-padded day.
        m_code = FYERS_WEEKLY_MONTH_CODE[expiry.month]
        dd = f"{expiry.day:02d}"
        date_part = f"{yy}{m_code}{dd}"

    fyers_symbol = f"{cfg['fyers_opt_prefix']}{date_part}{strike_int}{option_type}"
    instr_id = f"{u}_{expiry.strftime('%Y%m%d')}_{strike_int}_{option_type}"

    # Live source of truth first: the broker's own symbol for this exact
    # (expiry, strike, type) when the chain cache has it (same session).
    contract_source = "formula"
    live_premium: Optional[float] = None
    try:
        from app.signals.live_contract_cache import live_contract_cache
        live = live_contract_cache.lookup(u, expiry, strike_int, option_type)
        if live is not None:
            fyers_symbol = live.broker_symbol
            if live.mid > 0:
                live_premium = live.mid
            contract_source = "fyers_chain"
    except Exception:
        pass
    
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
        contract_source=contract_source,
        live_premium=live_premium,
    )


def parse_fyers_option_symbol(symbol: str) -> Optional[dict]:
    """Parse a FYERS v3 weekly/monthly option symbol.

    Returns {exchange, underlying, year, month, day|None, strike, option_type,
    expiry_kind} or None when the symbol is not well-formed. Day is None for
    monthly contracts (which carry no day component).
    """
    try:
        head, opt = symbol.rsplit(":", 1)
        exchange = head.strip().upper()
        rest = opt.strip().upper()
        underlying = None
        for u in ("BANKNIFTY", "NIFTY", "SENSEX"):
            if rest.startswith(u):
                underlying = u
                rest = rest[len(u):]
                break
        if underlying is None or len(rest) < 6:
            return None
        yy = rest[:2]
        if not yy.isdigit():
            return None
        tail = rest[2:]
        day: Optional[int] = None
        if len(tail) >= 3 and tail[:3].isalpha():
            # Monthly: MMM + strike + CE/PE
            month = datetime.strptime(tail[:3], "%b").month
            strike_type = tail[3:]
            kind = "MONTHLY"
        else:
            # Weekly: M + dd + strike + CE/PE
            m_code = tail[0]
            rev = {v: k for k, v in FYERS_WEEKLY_MONTH_CODE.items()}
            if m_code not in rev or not tail[1:3].isdigit():
                return None
            month = rev[m_code]
            day = int(tail[1:3])
            strike_type = tail[3:]
            kind = "WEEKLY"
        if not strike_type.endswith(("CE", "PE")):
            return None
        option_type = strike_type[-2:]
        strike_str = strike_type[:-2]
        if not strike_str.isdigit():
            return None
        return {
            "exchange": exchange,
            "underlying": underlying,
            "year": 2000 + int(yy),
            "month": month,
            "day": day,
            "strike": int(strike_str),
            "option_type": option_type,
            "expiry_kind": kind,
        }
    except Exception:
        return None


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


def calculate_option_buyer_sizing(
    available_capital: Decimal | float,
    risk_percent: float,
    option_entry_premium: Decimal | float,
    option_stop_premium: Optional[Decimal | float] = None,
    delta: Optional[float] = None,
    underlying_risk_points: Optional[Decimal | float] = None,
    lot_size: int = 75,
    max_capital_allocation_pct: float = 20.0,
    max_lots: int = 50,
) -> dict:
    """
    Precision position sizing for option buyers (§35).
    Determines lots based on option premium risk per lot, capped by maximum capital allocation.
    """
    d_cap = Decimal(str(available_capital))
    d_risk_pct = Decimal(str(risk_percent)) / Decimal("100")
    d_entry = Decimal(str(option_entry_premium))
    d_lot = Decimal(str(lot_size))

    if d_entry <= Decimal("0"):
        return {"lots": 0, "quantity": 0, "allowed": False, "reason": "Option entry premium must be positive"}

    # Determine risk per option share
    if option_stop_premium is not None and Decimal(str(option_stop_premium)) > Decimal("0"):
        d_stop = Decimal(str(option_stop_premium))
        option_risk_per_share = max(Decimal("1.0"), d_entry - d_stop)
    elif delta is not None and underlying_risk_points is not None:
        # Delta-implied option risk
        d_delta = Decimal(str(abs(delta)))
        d_und_risk = Decimal(str(underlying_risk_points))
        option_risk_per_share = max(Decimal("1.0"), min(d_entry, d_und_risk * d_delta))
    else:
        # Default conservative: 35% premium stop loss
        option_risk_per_share = d_entry * Decimal("0.35")

    risk_per_lot = option_risk_per_share * d_lot
    risk_capital = d_cap * d_risk_pct

    # Max rupee allocation per single option position (to prevent buying 100% OTM lots)
    max_trade_capital = d_cap * (Decimal(str(max_capital_allocation_pct)) / Decimal("100"))
    capital_per_lot = d_entry * d_lot

    # Sizing constrained by both risk capital and max allocation
    lots_by_risk = int(math.floor(risk_capital / risk_per_lot)) if risk_per_lot > 0 else 0
    lots_by_capital = int(math.floor(max_trade_capital / capital_per_lot)) if capital_per_lot > 0 else 0

    raw_lots = min(lots_by_risk, lots_by_capital)
    final_lots = max(0, min(raw_lots, max_lots))
    final_qty = final_lots * lot_size
    premium_outlay = float((Decimal(str(final_qty)) * d_entry).quantize(Decimal("0.01")))
    total_rupee_risk = float((Decimal(str(final_lots)) * risk_per_lot).quantize(Decimal("0.01")))

    return {
        "lots": final_lots,
        "quantity": final_qty,
        "lot_size": lot_size,
        "premium_outlay": premium_outlay,
        "max_rupee_loss": total_rupee_risk,
        "risk_per_lot": float(risk_per_lot.quantize(Decimal("0.01"))),
        "option_risk_per_share": float(option_risk_per_share.quantize(Decimal("0.01"))),
        "allowed": final_lots >= 1,
        "reason": "OK" if final_lots >= 1 else f"Insufficient risk capital (requires ₹{risk_per_lot:,.2f} for 1 lot)",
    }

