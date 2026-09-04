"""
Position Sizing — §32

risk_per_unit = abs(entry - stop) * contract_multiplier
max_quantity = floor(risk_budget / risk_per_unit)
Round down to lot, never exceed capital/risk/margin/portfolio/lot/broker
"""
from __future__ import annotations

from decimal import Decimal
from dataclasses import dataclass
from app.algo.money import D
import structlog

logger = structlog.get_logger()


@dataclass
class SizingInputs:
    algo_capital_available: Decimal
    risk_budget: Decimal          # e.g. max_loss_per_trade or risk_per_trade_pct * capital
    entry_price: Decimal
    stop_price: Decimal | None
    lot_size: int = 1
    contract_multiplier: Decimal = D(1)
    max_capital_per_trade: Decimal | None = None
    max_position_size: int | None = None
    max_notional: Decimal | None = None
    margin_per_unit: Decimal | None = None
    available_margin: Decimal | None = None
    portfolio_capacity: Decimal | None = None  # remaining portfolio headroom


@dataclass
class SizingResult:
    quantity: int  # lot-aligned
    notional: Decimal
    risk_per_unit: Decimal | None
    reason: str
    capped_by: str | None = None


def size_position(inp: SizingInputs) -> SizingResult:
    # Validate
    entry = D(inp.entry_price)
    stop = D(inp.stop_price) if inp.stop_price is not None else None
    risk_budget = D(inp.risk_budget)
    if risk_budget <= D(0):
        return SizingResult(quantity=0, notional=D(0), risk_per_unit=None, reason="ZERO_RISK_BUDGET", capped_by="RISK_BUDGET")

    # Risk-based sizing if stop provided
    if stop is not None and stop > D(0) and entry != stop:
        risk_per_unit = abs(entry - stop) * D(inp.contract_multiplier)
        if risk_per_unit <= D(0):
            return SizingResult(quantity=0, notional=D(0), risk_per_unit=risk_per_unit, reason="ZERO_RISK_PER_UNIT", capped_by="RISK_PER_UNIT")
        max_qty_risk = (risk_budget / risk_per_unit).to_integral_value(rounding="ROUND_FLOOR")
        max_qty_risk = int(max_qty_risk)
    else:
        risk_per_unit = None
        # fallback: size by notional / risk_budget heuristic
        max_qty_risk = int((risk_budget / (entry * D(inp.contract_multiplier))).to_integral_value(rounding="ROUND_FLOOR")) if entry > 0 else 0

    qty = max_qty_risk

    # Align down to lot
    if inp.lot_size > 1:
        qty = (qty // inp.lot_size) * inp.lot_size

    capped = None

    # Cap by capital
    max_qty_capital = None
    cap_limit = inp.max_capital_per_trade
    if cap_limit is not None and entry > 0:
        # qty * entry * multiplier <= cap
        # For options, entry is premium; notional = qty * entry * multiplier
        max_qty_capital = int((D(cap_limit) / (entry * D(inp.contract_multiplier))).to_integral_value(rounding="ROUND_FLOOR"))
        if inp.lot_size > 1:
            max_qty_capital = (max_qty_capital // inp.lot_size) * inp.lot_size
        if max_qty_capital is not None and qty > max_qty_capital:
            capped = "MAX_CAPITAL_PER_TRADE"
            qty = max_qty_capital

    # Cap by algo capital available
    if entry > 0:
        max_qty_avail = int((D(inp.algo_capital_available) / (entry * D(inp.contract_multiplier))).to_integral_value(rounding="ROUND_FLOOR"))
        if inp.lot_size > 1:
            max_qty_avail = (max_qty_avail // inp.lot_size) * inp.lot_size
        if qty > max_qty_avail:
            capped = "AVAILABLE_CAPITAL"
            qty = max_qty_avail

    # Cap by margin
    if inp.margin_per_unit is not None and inp.available_margin is not None and inp.margin_per_unit > D(0):
        max_qty_margin = int((D(inp.available_margin) / D(inp.margin_per_unit)).to_integral_value(rounding="ROUND_FLOOR"))
        if inp.lot_size > 1:
            max_qty_margin = (max_qty_margin // inp.lot_size) * inp.lot_size
        if qty > max_qty_margin:
            capped = "AVAILABLE_MARGIN"
            qty = max_qty_margin

    # Cap by max position size
    if inp.max_position_size is not None and qty > inp.max_position_size:
        capped = "MAX_POSITION_SIZE"
        qty = (inp.max_position_size // inp.lot_size) * inp.lot_size if inp.lot_size > 1 else inp.max_position_size

    # Cap by max notional
    if inp.max_notional is not None and entry > 0:
        max_qty_notional = int((D(inp.max_notional) / (entry * D(inp.contract_multiplier))).to_integral_value(rounding="ROUND_FLOOR"))
        if inp.lot_size > 1:
            max_qty_notional = (max_qty_notional // inp.lot_size) * inp.lot_size
        if qty > max_qty_notional:
            capped = "MAX_NOTIONAL"
            qty = max_qty_notional

    # Cap by portfolio capacity (in currency terms converted to qty)
    if inp.portfolio_capacity is not None and entry > 0:
        max_qty_pf = int((D(inp.portfolio_capacity) / (entry * D(inp.contract_multiplier))).to_integral_value(rounding="ROUND_FLOOR"))
        if inp.lot_size > 1:
            max_qty_pf = (max_qty_pf // inp.lot_size) * inp.lot_size
        if qty > max_qty_pf:
            capped = "PORTFOLIO_CAPACITY"
            qty = max_qty_pf

    if qty < 0:
        qty = 0
    if qty > 0 and qty < inp.lot_size:
        qty = 0
        capped = "LOT_SIZE_MINIMUM"

    notional = D(qty) * entry * D(inp.contract_multiplier)
    reason = "SIZED_OK" if qty > 0 else "SIZED_ZERO"
    if capped:
        reason = f"CAPPED_BY_{capped}"
    if qty == 0:
        logger.info("position_sizing_zero", reason=reason, entry=str(entry), risk_budget=str(risk_budget))

    return SizingResult(quantity=qty, notional=notional, risk_per_unit=risk_per_unit, reason=reason, capped_by=capped)
