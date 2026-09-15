"""
Swing Risk & Position Sizing Engine (v6.0 Options Overhaul).
Dual-budget options sizing:
  1. Loss budget (e.g. max 1% equity at risk)
  2. Premium outlay budget (e.g. max 5% equity deployed)
  3. No forced minimum lot: if 1 lot exceeds limits -> rejection
  4. Preserves underlying spot structural & ATR floor calculations
"""
from __future__ import annotations

import math
from typing import NamedTuple, Optional


class SwingOptionsRiskResult(NamedTuple):
    num_lots: int
    total_premium_outlay: float      # entry_premium * lot_size * num_lots
    max_loss: float                  # (entry_premium - stop_premium) * lot_size * num_lots
    capital_at_risk_pct: float       # (max_loss / portfolio_equity) * 100
    theta_daily_cost: float          # abs(theta_day) * lot_size * num_lots
    risk_reward_t1: float
    risk_reward_t2: float
    premium_risk_per_lot: float
    is_viable: bool
    rejection_reason: Optional[str] = None


def compute_swing_options_risk(
    entry_premium: float,
    stop_premium: float,
    target_premium_1: float,
    target_premium_2: float,
    lot_size: int,
    unit_theta_day: float = 0.0,
    portfolio_equity: float = 1_000_000.0,
    max_risk_pct: float = 1.0,         # Max 1% equity at risk per trade
    max_premium_pct: float = 5.0,      # Max 5% equity deployed as premium outlay
) -> SwingOptionsRiskResult:
    """
    Computes option trade lot sizing and risk allocation under dual-budget constraints.
    Enforces §14: If smallest tradable position (1 lot) violates risk limits -> NO TRADE.
    """
    if entry_premium <= 0 or lot_size <= 0:
        return SwingOptionsRiskResult(
            num_lots=0, total_premium_outlay=0.0, max_loss=0.0, capital_at_risk_pct=0.0,
            theta_daily_cost=0.0, risk_reward_t1=0.0, risk_reward_t2=0.0, premium_risk_per_lot=0.0,
            is_viable=False, rejection_reason="Entry premium and lot size must be positive."
        )

    premium_risk_per_unit = max(0.01, entry_premium - stop_premium)
    premium_risk_per_lot = premium_risk_per_unit * lot_size
    premium_outlay_per_lot = entry_premium * lot_size

    risk_budget = portfolio_equity * (max_risk_pct / 100.0)
    premium_budget = portfolio_equity * (max_premium_pct / 100.0)

    lots_by_risk = int(risk_budget / premium_risk_per_lot) if premium_risk_per_lot > 0 else 0
    lots_by_premium = int(premium_budget / premium_outlay_per_lot) if premium_outlay_per_lot > 0 else 0

    num_lots = min(lots_by_risk, lots_by_premium)

    if num_lots < 1:
        return SwingOptionsRiskResult(
            num_lots=0,
            total_premium_outlay=0.0,
            max_loss=0.0,
            capital_at_risk_pct=0.0,
            theta_daily_cost=0.0,
            risk_reward_t1=0.0,
            risk_reward_t2=0.0,
            premium_risk_per_lot=round(premium_risk_per_lot, 2),
            is_viable=False,
            rejection_reason=(
                f"Capital budget insufficient for 1 lot: "
                f"Risk required ₹{premium_risk_per_lot:.0f} vs budget ₹{risk_budget:.0f}; "
                f"Outlay required ₹{premium_outlay_per_lot:.0f} vs budget ₹{premium_budget:.0f}."
            ),
        )

    total_premium_outlay = round(num_lots * premium_outlay_per_lot, 2)
    max_loss = round(num_lots * premium_risk_per_lot, 2)
    capital_at_risk_pct = round((max_loss / portfolio_equity) * 100.0, 2)
    theta_daily_cost = round(abs(unit_theta_day) * lot_size * num_lots, 2)

    rr_t1 = round((target_premium_1 - entry_premium) / premium_risk_per_unit, 2) if premium_risk_per_unit > 0 else 0.0
    rr_t2 = round((target_premium_2 - entry_premium) / premium_risk_per_unit, 2) if premium_risk_per_unit > 0 else 0.0

    return SwingOptionsRiskResult(
        num_lots=num_lots,
        total_premium_outlay=total_premium_outlay,
        max_loss=max_loss,
        capital_at_risk_pct=capital_at_risk_pct,
        theta_daily_cost=theta_daily_cost,
        risk_reward_t1=rr_t1,
        risk_reward_t2=rr_t2,
        premium_risk_per_lot=round(premium_risk_per_lot, 2),
        is_viable=True,
        rejection_reason=None,
    )


class SwingRiskResult(NamedTuple):
    trigger_price: float
    max_chase_price: float
    effective_stop: float
    structural_stop: float
    atr_floor: float
    target_1: float
    target_2: float
    risk_per_share: float
    risk_pct: float
    risk_reward_t1: float
    risk_reward_t2: float
    suggested_qty: int
    capital_required: float


def compute_swing_risk_levels(
    trigger_price: float,
    structural_stop_price: float,
    daily_atr: float,
    portfolio_equity: float = 1_000_000.0,
    risk_percent: float = 1.0,         # 1% risk per trade
    max_capital_pct_per_pos: float = 20.0,
    atr_multiplier: float = 1.2,
) -> SwingRiskResult:
    """
    Computes spot swing trade levels (structural stop vs 1.2x ATR floor) on the underlying.
    """
    if trigger_price <= 0:
        raise ValueError("Trigger price must be greater than zero.")

    struct_dist = max(0.01, trigger_price - structural_stop_price)
    atr_floor_dist = max(0.01, atr_multiplier * daily_atr)
    effective_dist = max(struct_dist, atr_floor_dist)
    effective_stop = round(trigger_price - effective_dist, 2)

    t1 = round(trigger_price + 1.5 * effective_dist, 2)
    t2 = round(trigger_price + 3.0 * effective_dist, 2)
    max_chase = round(trigger_price * 1.01, 2)

    risk_per_share = round(effective_dist, 2)
    risk_pct = round((risk_per_share / trigger_price) * 100.0, 2)
    rr_t1 = round((t1 - trigger_price) / effective_dist, 2)
    rr_t2 = round((t2 - trigger_price) / effective_dist, 2)

    risk_budget = portfolio_equity * (risk_percent / 100.0)
    raw_qty = int(risk_budget / effective_dist) if effective_dist > 0 else 0

    max_cap = portfolio_equity * (max_capital_pct_per_pos / 100.0)
    max_qty_by_cap = int(max_cap / trigger_price) if trigger_price > 0 else 0

    final_qty = max(1, min(raw_qty, max_qty_by_cap))
    total_capital = round(final_qty * trigger_price, 2)

    return SwingRiskResult(
        trigger_price=round(trigger_price, 2),
        max_chase_price=max_chase,
        effective_stop=effective_stop,
        structural_stop=round(structural_stop_price, 2),
        atr_floor=round(trigger_price - atr_floor_dist, 2),
        target_1=t1,
        target_2=t2,
        risk_per_share=risk_per_share,
        risk_pct=risk_pct,
        risk_reward_t1=rr_t1,
        risk_reward_t2=rr_t2,
        suggested_qty=final_qty,
        capital_required=total_capital,
    )

