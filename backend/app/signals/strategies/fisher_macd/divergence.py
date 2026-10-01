"""DROID — Point-in-Time Divergence Detection Engine (§23R).

Detects confirmed pivots and price/indicator divergences:
- Regular Bullish: Price Lower Low, Indicator Higher Low
- Regular Bearish: Price Higher High, Indicator Lower High
- Hidden Bullish: Price Higher Low, Indicator Lower Low
- Hidden Bearish: Price Lower High, Indicator Higher High

Strict Timing Invariance:
A pivot at bar i with right_bars=R is ONLY confirmed at bar i + R close.
The event is emitted at confirmation bar (i + R), with:
- pivot_index = i
- confirmation_index = i + R
- indicator_at_pivot = indicator[i]
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence
import numpy as np
import pandas as pd


class DivergenceType(str, Enum):
    REGULAR_BULLISH = "REGULAR_BULLISH"
    REGULAR_BEARISH = "REGULAR_BEARISH"
    HIDDEN_BULLISH = "HIDDEN_BULLISH"
    HIDDEN_BEARISH = "HIDDEN_BEARISH"


class PivotType(str, Enum):
    HIGH = "HIGH"
    LOW = "LOW"


@dataclass(frozen=True)
class Pivot:
    pivot_type: PivotType
    pivot_index: int           # Bar where extremum occurred
    confirmation_index: int    # Bar where pivot was confirmed (pivot_index + right_bars)
    price: float               # High for pivot high, Low for pivot low
    indicator_value: float     # Indicator value at pivot_index
    timestamp: str | None = None


@dataclass(frozen=True)
class DivergenceEvent:
    divergence_type: DivergenceType
    indicator_name: str        # e.g. "fisher", "macd", "macd_hist"
    confirmation_index: int    # When signal becomes actionable in real time
    curr_pivot_index: int      # Most recent extremum bar index
    prev_pivot_index: int      # Previous extremum bar index
    curr_price: float
    prev_price: float
    curr_indicator: float
    prev_indicator: float
    price_delta: float
    price_delta_atr: float
    indicator_delta: float
    pivot_separation_bars: int
    confirmation_lag: int
    timestamp: str | None = None


def detect_pivots(
    highs: Sequence[float],
    lows: Sequence[float],
    indicator_values: Sequence[float | None],
    timestamps: Sequence[str] | None = None,
    left_bars: int = 5,
    right_bars: int = 5,
) -> tuple[list[Pivot], list[Pivot]]:
    """Detect strictly confirmed pivot highs and pivot lows without lookahead.
    
    A pivot at bar i is confirmed at bar i + right_bars.
    """
    n = len(highs)
    pivot_highs: list[Pivot] = []
    pivot_lows: list[Pivot] = []

    if n < left_bars + right_bars + 1:
        return pivot_highs, pivot_lows

    for i in range(left_bars, n - right_bars):
        conf_idx = i + right_bars
        ind_val = indicator_values[i]
        if ind_val is None or np.isnan(ind_val):
            continue

        curr_h = highs[i]
        curr_l = lows[i]
        ts = timestamps[conf_idx] if timestamps is not None and conf_idx < len(timestamps) else None

        # Check Pivot High: strictly greater than left window, greater or equal to right window
        is_pivot_h = (
            all(curr_h > highs[j] for j in range(i - left_bars, i))
            and all(curr_h >= highs[j] for j in range(i + 1, i + right_bars + 1))
        )
        if is_pivot_h:
            pivot_highs.append(
                Pivot(
                    pivot_type=PivotType.HIGH,
                    pivot_index=i,
                    confirmation_index=conf_idx,
                    price=float(curr_h),
                    indicator_value=float(ind_val),
                    timestamp=ts,
                )
            )

        # Check Pivot Low: strictly less than left window, less or equal to right window
        is_pivot_l = (
            all(curr_l < lows[j] for j in range(i - left_bars, i))
            and all(curr_l <= lows[j] for j in range(i + 1, i + right_bars + 1))
        )
        if is_pivot_l:
            pivot_lows.append(
                Pivot(
                    pivot_type=PivotType.LOW,
                    pivot_index=i,
                    confirmation_index=conf_idx,
                    price=float(curr_l),
                    indicator_value=float(ind_val),
                    timestamp=ts,
                )
            )

    return pivot_highs, pivot_lows


def detect_divergences(
    highs: Sequence[float],
    lows: Sequence[float],
    indicator_values: Sequence[float | None],
    atr_values: Sequence[float | None],
    indicator_name: str = "fisher",
    timestamps: Sequence[str] | None = None,
    pivot_left_bars: int = 5,
    pivot_right_bars: int = 5,
    min_pivot_separation: int = 5,
    max_pivot_separation: int = 100,
    pairing_strategy: str = "nearest",
) -> list[DivergenceEvent]:
    """Detect strictly confirmed divergences across confirmed pivots (§23R)."""
    pivot_highs, pivot_lows = detect_pivots(
        highs=highs,
        lows=lows,
        indicator_values=indicator_values,
        timestamps=timestamps,
        left_bars=pivot_left_bars,
        right_bars=pivot_right_bars,
    )

    divergences: list[DivergenceEvent] = []

    # 1. Evaluate Bearish Divergences on Pivot Highs
    for i in range(1, len(pivot_highs)):
        curr_p = pivot_highs[i]
        
        # Candidate previous pivots in valid separation range
        candidates = [
            pivot_highs[k] for k in range(i - 1, -1, -1)
            if min_pivot_separation <= (curr_p.pivot_index - pivot_highs[k].pivot_index) <= max_pivot_separation
        ]
        if not candidates:
            continue

        selected = candidates if pairing_strategy == "all" else [candidates[0]]

        for prev_p in selected:
            sep = curr_p.pivot_index - prev_p.pivot_index
            p_curr = curr_p.price
            p_prev = prev_p.price
            ind_curr = curr_p.indicator_value
            ind_prev = prev_p.indicator_value
            conf_idx = curr_p.confirmation_index
            atr = atr_values[conf_idx] if conf_idx < len(atr_values) and atr_values[conf_idx] else 1.0
            if atr is None or np.isnan(atr) or atr <= 0:
                atr = 1.0

            p_delta = p_curr - p_prev
            ind_delta = ind_curr - ind_prev
            ts = timestamps[conf_idx] if timestamps is not None and conf_idx < len(timestamps) else None

            # Regular Bearish: Price Higher High (p_curr > p_prev), Indicator Lower High (ind_curr < ind_prev)
            if p_curr > p_prev and ind_curr < ind_prev:
                divergences.append(
                    DivergenceEvent(
                        divergence_type=DivergenceType.REGULAR_BEARISH,
                        indicator_name=indicator_name,
                        confirmation_index=conf_idx,
                        curr_pivot_index=curr_p.pivot_index,
                        prev_pivot_index=prev_p.pivot_index,
                        curr_price=p_curr,
                        prev_price=p_prev,
                        curr_indicator=ind_curr,
                        prev_indicator=ind_prev,
                        price_delta=round(float(p_delta), 2),
                        price_delta_atr=round(float(p_delta / atr), 3),
                        indicator_delta=round(float(ind_delta), 3),
                        pivot_separation_bars=sep,
                        confirmation_lag=pivot_right_bars,
                        timestamp=ts,
                    )
                )
            # Hidden Bearish: Price Lower High (p_curr < p_prev), Indicator Higher High (ind_curr > ind_prev)
            elif p_curr < p_prev and ind_curr > ind_prev:
                divergences.append(
                    DivergenceEvent(
                        divergence_type=DivergenceType.HIDDEN_BEARISH,
                        indicator_name=indicator_name,
                        confirmation_index=conf_idx,
                        curr_pivot_index=curr_p.pivot_index,
                        prev_pivot_index=prev_p.pivot_index,
                        curr_price=p_curr,
                        prev_price=p_prev,
                        curr_indicator=ind_curr,
                        prev_indicator=ind_prev,
                        price_delta=round(float(p_delta), 2),
                        price_delta_atr=round(float(p_delta / atr), 3),
                        indicator_delta=round(float(ind_delta), 3),
                        pivot_separation_bars=sep,
                        confirmation_lag=pivot_right_bars,
                        timestamp=ts,
                    )
                )

    # 2. Evaluate Bullish Divergences on Pivot Lows
    for i in range(1, len(pivot_lows)):
        curr_p = pivot_lows[i]
        
        candidates = [
            pivot_lows[k] for k in range(i - 1, -1, -1)
            if min_pivot_separation <= (curr_p.pivot_index - pivot_lows[k].pivot_index) <= max_pivot_separation
        ]
        if not candidates:
            continue

        selected = candidates if pairing_strategy == "all" else [candidates[0]]

        for prev_p in selected:
            sep = curr_p.pivot_index - prev_p.pivot_index
            p_curr = curr_p.price
            p_prev = prev_p.price
            ind_curr = curr_p.indicator_value
            ind_prev = prev_p.indicator_value
            conf_idx = curr_p.confirmation_index
            atr = atr_values[conf_idx] if conf_idx < len(atr_values) and atr_values[conf_idx] else 1.0
            if atr is None or np.isnan(atr) or atr <= 0:
                atr = 1.0

            p_delta = p_curr - p_prev
            ind_delta = ind_curr - ind_prev
            ts = timestamps[conf_idx] if timestamps is not None and conf_idx < len(timestamps) else None

            # Regular Bullish: Price Lower Low (p_curr < p_prev), Indicator Higher Low (ind_curr > ind_prev)
            if p_curr < p_prev and ind_curr > ind_prev:
                divergences.append(
                    DivergenceEvent(
                        divergence_type=DivergenceType.REGULAR_BULLISH,
                        indicator_name=indicator_name,
                        confirmation_index=conf_idx,
                        curr_pivot_index=curr_p.pivot_index,
                        prev_pivot_index=prev_p.pivot_index,
                        curr_price=p_curr,
                        prev_price=p_prev,
                        curr_indicator=ind_curr,
                        prev_indicator=ind_prev,
                        price_delta=round(float(p_delta), 2),
                        price_delta_atr=round(float(p_delta / atr), 3),
                        indicator_delta=round(float(ind_delta), 3),
                        pivot_separation_bars=sep,
                        confirmation_lag=pivot_right_bars,
                        timestamp=ts,
                    )
                )
            # Hidden Bullish: Price Higher Low (p_curr > p_prev), Indicator Lower Low (ind_curr < ind_prev)
            elif p_curr > p_prev and ind_curr < ind_prev:
                divergences.append(
                    DivergenceEvent(
                        divergence_type=DivergenceType.HIDDEN_BULLISH,
                        indicator_name=indicator_name,
                        confirmation_index=conf_idx,
                        curr_pivot_index=curr_p.pivot_index,
                        prev_pivot_index=prev_p.pivot_index,
                        curr_price=p_curr,
                        prev_price=p_prev,
                        curr_indicator=ind_curr,
                        prev_indicator=ind_prev,
                        price_delta=round(float(p_delta), 2),
                        price_delta_atr=round(float(p_delta / atr), 3),
                        indicator_delta=round(float(ind_delta), 3),
                        pivot_separation_bars=sep,
                        confirmation_lag=pivot_right_bars,
                        timestamp=ts,
                    )
                )

    # Sort strictly by confirmation_index
    divergences.sort(key=lambda d: d.confirmation_index)
    return divergences


def get_active_divergence_at_bar(
    bar_index: int,
    divergences: Sequence[DivergenceEvent],
    max_recency_bars: int = 15,
) -> DivergenceEvent | None:
    """Return the most recently confirmed divergence within max_recency_bars of bar_index.
    
    Point-in-time rule: confirmation_index <= bar_index and (bar_index - confirmation_index) <= max_recency_bars.
    """
    valid = [
        d for d in divergences
        if d.confirmation_index <= bar_index and (bar_index - d.confirmation_index) <= max_recency_bars
    ]
    return valid[-1] if valid else None
