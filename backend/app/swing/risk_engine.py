"""
Swing Risk & Position Sizing Engine (v5.0 §13, §14, §21).
Rules:
  1. Structural Invalidation + 1.2x Daily ATR Floor:
     effective_stop_distance = max(structural_distance, 1.2 * daily_atr)
  2. Fixed % Portfolio Risk Sizing (0.5% - 1.0%).
  3. Max Chase Protection (entry strictly <= trigger * 1.01).
  4. Multi-target projection (T1 = 1.5R, T2 = 3.0R).
"""
from __future__ import annotations

import math
from typing import NamedTuple


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
    max_capital_pct_per_pos: float = 20.0, # Max 20% equity in one stock
    atr_multiplier: float = 1.2,
) -> SwingRiskResult:
    """
    Computes rigorous swing trade levels and capital sizing.
    """
    if trigger_price <= 0:
        raise ValueError("Trigger price must be greater than zero.")

    # Structural distance
    struct_dist = max(0.01, trigger_price - structural_stop_price)

    # 1.2x ATR Floor
    atr_floor_dist = max(0.01, atr_multiplier * daily_atr)

    # Non-negotiable rule: max(structural, ATR floor)
    effective_dist = max(struct_dist, atr_floor_dist)
    effective_stop = round(trigger_price - effective_dist, 2)

    # Targets
    t1 = round(trigger_price + 1.5 * effective_dist, 2)
    t2 = round(trigger_price + 3.0 * effective_dist, 2)

    # Max chase price (1.0% tolerance above trigger)
    max_chase = round(trigger_price * 1.01, 2)

    # Risk metrics
    risk_per_share = round(effective_dist, 2)
    risk_pct = round((risk_per_share / trigger_price) * 100.0, 2)
    rr_t1 = round((t1 - trigger_price) / effective_dist, 2)
    rr_t2 = round((t2 - trigger_price) / effective_dist, 2)

    # Position sizing
    risk_budget = portfolio_equity * (risk_percent / 100.0)
    raw_qty = int(risk_budget / effective_dist) if effective_dist > 0 else 0

    # Capital ceiling (e.g. max 20% equity in one stock)
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
