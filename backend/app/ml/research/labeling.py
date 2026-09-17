"""Triple-Barrier Trade Labeling & Path Excursion Engine.

Implements Section 13 and Section 15 of the DROID ML Specification.
Labels strategy candidates using explicit path-dependent Triple Barriers:
  1. Upper Barrier: Target 1 (or profit taking level)
  2. Lower Barrier: Stop Loss
  3. Horizontal Barrier: Time Expiry (e.g., 45 minutes)

Computes continuous path excursions:
  - Maximum Favorable Excursion (MFE in R-multiples)
  - Maximum Adverse Excursion (MAE in R-multiples)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Tuple

LabelName = Literal["TARGET_FIRST", "STOP_FIRST", "TIMEOUT"]
LABEL_TARGET_FIRST = 2
LABEL_TIMEOUT = 1
LABEL_STOP_FIRST = 0

INV_TRIPLE_BARRIER_LABEL = {
    LABEL_TARGET_FIRST: "TARGET_FIRST",
    LABEL_TIMEOUT: "TIMEOUT",
    LABEL_STOP_FIRST: "STOP_FIRST",
}


@dataclass(frozen=True)
class TripleBarrierOutcome:
    label: int  # 2=TARGET_FIRST, 0=STOP_FIRST, 1=TIMEOUT
    label_name: LabelName
    mfe_r: float  # Max favorable excursion in units of risk R
    mae_r: float  # Max adverse excursion in units of risk R
    bars_to_exit: int
    exit_price: float
    realized_ret_pct: float
    risk_points: float


def compute_triple_barrier(
    entry_price: float,
    target_1: float,
    stop_loss: float,
    direction: str,
    future_bars: List[Dict[str, Any]],
    time_limit_bars: int = 45,
) -> TripleBarrierOutcome:
    """
    Evaluates tick/bar path against upper, lower, and horizontal barriers.
    
    Args:
        entry_price: Exact limit/spot entry price
        target_1: Target 1 price level
        stop_loss: Initial hard stop loss price level
        direction: "LONG_CALL" | "LONG_PUT" | "CALL" | "PUT"
        future_bars: Sequence of subsequent 1-minute bars
        time_limit_bars: Horizon limit (horizontal barrier)
    """
    if entry_price <= 0:
        raise ValueError(f"entry_price must be positive, got {entry_price}")

    risk = abs(entry_price - stop_loss)
    if risk <= 0:
        risk = entry_price * 0.002  # 0.2% minimum risk floor

    is_call = "CALL" in direction.upper() or direction.upper() in ("LONG", "BUY")

    max_fav = 0.0
    max_adv = 0.0
    evaluated_bars = future_bars[:time_limit_bars]

    if not evaluated_bars:
        return TripleBarrierOutcome(
            label=LABEL_TIMEOUT,
            label_name="TIMEOUT",
            mfe_r=0.0,
            mae_r=0.0,
            bars_to_exit=0,
            exit_price=entry_price,
            realized_ret_pct=0.0,
            risk_points=risk,
        )

    for idx, bar in enumerate(evaluated_bars):
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])

        if is_call:
            fav = max(0.0, high - entry_price)
            adv = max(0.0, entry_price - low)
            max_fav = max(max_fav, fav)
            max_adv = max(max_adv, adv)

            # Check if stop loss was touched first (conservative: check SL before Target)
            if low <= stop_loss:
                ret = (stop_loss - entry_price) / entry_price
                return TripleBarrierOutcome(
                    label=LABEL_STOP_FIRST,
                    label_name="STOP_FIRST",
                    mfe_r=round(max_fav / risk, 3),
                    mae_r=round(max_adv / risk, 3),
                    bars_to_exit=idx + 1,
                    exit_price=stop_loss,
                    realized_ret_pct=round(ret, 5),
                    risk_points=risk,
                )

            # Check if Target 1 was touched
            if high >= target_1:
                ret = (target_1 - entry_price) / entry_price
                return TripleBarrierOutcome(
                    label=LABEL_TARGET_FIRST,
                    label_name="TARGET_FIRST",
                    mfe_r=round(max_fav / risk, 3),
                    mae_r=round(max_adv / risk, 3),
                    bars_to_exit=idx + 1,
                    exit_price=target_1,
                    realized_ret_pct=round(ret, 5),
                    risk_points=risk,
                )
        else:
            # Bearish (Put) logic: Target is lower, Stop Loss is higher
            fav = max(0.0, entry_price - low)
            adv = max(0.0, high - entry_price)
            max_fav = max(max_fav, fav)
            max_adv = max(max_adv, adv)

            # Check stop loss hit first
            if high >= stop_loss:
                ret = (entry_price - stop_loss) / entry_price
                return TripleBarrierOutcome(
                    label=LABEL_STOP_FIRST,
                    label_name="STOP_FIRST",
                    mfe_r=round(max_fav / risk, 3),
                    mae_r=round(max_adv / risk, 3),
                    bars_to_exit=idx + 1,
                    exit_price=stop_loss,
                    realized_ret_pct=round(ret, 5),
                    risk_points=risk,
                )

            # Check target hit
            if low <= target_1:
                ret = (entry_price - target_1) / entry_price
                return TripleBarrierOutcome(
                    label=LABEL_TARGET_FIRST,
                    label_name="TARGET_FIRST",
                    mfe_r=round(max_fav / risk, 3),
                    mae_r=round(max_adv / risk, 3),
                    bars_to_exit=idx + 1,
                    exit_price=target_1,
                    realized_ret_pct=round(ret, 5),
                    risk_points=risk,
                )

    # Reached horizontal barrier without touching SL or T1
    last_bar = evaluated_bars[-1]
    final_close = float(last_bar["close"])
    if is_call:
        ret = (final_close - entry_price) / entry_price
    else:
        ret = (entry_price - final_close) / entry_price

    return TripleBarrierOutcome(
        label=LABEL_TIMEOUT,
        label_name="TIMEOUT",
        mfe_r=round(max_fav / risk, 3),
        mae_r=round(max_adv / risk, 3),
        bars_to_exit=len(evaluated_bars),
        exit_price=final_close,
        realized_ret_pct=round(ret, 5),
        risk_points=risk,
    )
