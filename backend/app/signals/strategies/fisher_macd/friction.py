"""DROID — Friction-Aware Outcome Layer (§58).

Implements realistic market friction for Index Futures and Options:
- Statutory costs (STT, GST, Exchange charges, SEBI turnover, Stamp duty)
- Bid-Ask Spread and Execution Slippage
- Net ATR-adjusted forward outcome analysis
- Sensitivity across [0.00 ATR, 0.05 ATR, 0.10 ATR, 0.15 ATR] haircuts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
import numpy as np


@dataclass(frozen=True)
class FrictionModelConfig:
    spread_atr_fraction: float = 0.02       # 0.02 ATR bid-ask spread
    slippage_atr_fraction: float = 0.03     # 0.03 ATR execution slippage
    round_trip_cost_atr: float = 0.05       # Total default round trip friction (0.05 ATR)
    statutory_cost_rate: float = 0.0006     # 0.06% combined STT, GST, SEBI, exchange fee
    brokerage_per_order_inr: float = 20.0   # Flat discount broker fee (₹20)


@dataclass(frozen=True)
class FrictionAdjustedOutcome:
    raw_success: bool
    raw_pnl_atr: float
    raw_pnl_points: float
    friction_cost_atr: float
    friction_cost_points: float
    net_pnl_atr: float
    net_pnl_points: float
    net_success: bool                      # Net PnL > 0 after friction


def apply_friction_to_outcomes(
    raw_successes: Sequence[bool],
    raw_pnl_atrs: Sequence[float],
    atr_values: Sequence[float],
    friction_atr: float = 0.05,
) -> list[FrictionAdjustedOutcome]:
    """Adjust a series of raw trade outcomes by applying round-trip execution friction (§58)."""
    adjusted: list[FrictionAdjustedOutcome] = []

    for success, pnl_atr, atr in zip(raw_successes, raw_pnl_atrs, atr_values):
        cost_atr = friction_atr
        cost_pts = cost_atr * atr
        raw_pts = pnl_atr * atr

        net_atr = pnl_atr - cost_atr
        net_pts = raw_pts - cost_pts
        net_win = net_atr > 0.0

        adjusted.append(
            FrictionAdjustedOutcome(
                raw_success=bool(success),
                raw_pnl_atr=float(pnl_atr),
                raw_pnl_points=round(float(raw_pts), 2),
                friction_cost_atr=float(cost_atr),
                friction_cost_points=round(float(cost_pts), 2),
                net_pnl_atr=round(float(net_atr), 3),
                net_pnl_points=round(float(net_pts), 2),
                net_success=bool(net_win),
            )
        )

    return adjusted


def compute_friction_sensitivity(
    raw_successes: Sequence[bool],
    raw_pnl_atrs: Sequence[float],
    atr_values: Sequence[float],
    haircut_grid: Sequence[float] = (0.00, 0.05, 0.10, 0.15),
) -> list[dict]:
    """Compute performance metrics across a grid of friction haircuts (§58 Table)."""
    n = len(raw_successes)
    if n == 0:
        return []

    results = []
    for haircut in haircut_grid:
        adj = apply_friction_to_outcomes(raw_successes, raw_pnl_atrs, atr_values, friction_atr=haircut)
        wins = sum(1 for a in adj if a.net_success)
        wr = (wins / n) * 100
        gross_profit = sum(a.net_pnl_atr for a in adj if a.net_pnl_atr > 0)
        gross_loss = abs(sum(a.net_pnl_atr for a in adj if a.net_pnl_atr <= 0))
        pf = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if wins > 0 else 0.0)
        total_net_gain = sum(a.net_pnl_atr for a in adj)
        ev = total_net_gain / n

        results.append({
            "friction_haircut_atr": haircut,
            "total_trades": n,
            "net_wins": wins,
            "net_win_rate_pct": round(wr, 1),
            "profit_factor": round(pf, 2),
            "total_net_gain_atr": round(total_net_gain, 2),
            "expected_value_atr": round(ev, 3),
            "is_economically_viable": bool(ev > 0.0 and pf > 1.0),
        })

    return results
