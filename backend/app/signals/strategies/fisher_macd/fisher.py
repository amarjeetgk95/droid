"""DROID MACD + Fisher-9 Exhaustion Research — Pinned Fisher-9 Indicator.

Specification Reference: §10R (Ehlers' original Fisher Transform 2004, Chapter 4).
Precision: float64 throughout.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class FisherPoint:
    """Output for a single bar."""
    bar_index: int
    raw: float | None
    fisher: float | None
    trigger: float | None


def calculate_fisher_point(
    highs: Sequence[float],
    lows: Sequence[float],
    period: int = 9,
    price_source: str = "HL2",
    closes: Sequence[float] | None = None,
    opens: Sequence[float] | None = None,
) -> list[FisherPoint]:
    """Calculate Fisher Transform and Trigger series adhering strictly to §10R.

    Formula (Ehlers 2004):
      Period = 9
      For bar i >= period - 1:
        MaxH = Highest(High, Period)
        MinL = Lowest(Low, Period)
        Price = (High + Low) / 2.0 (or selected price source)
        Raw = 0.33 * 2.0 * ((Price - MinL) / (MaxH - MinL) - 0.5) + 0.67 * Raw[1]
        Clamp Raw to (-0.999, +0.999)
        Fisher = 0.5 * ln((1 + Raw) / (1 - Raw)) + 0.5 * Fisher[1]
        Trigger = Fisher[1]

    Initialization:
      Raw[1] = 0.0 before first valid bar.
      Fisher[1] = 0.0 before first valid bar.
      Bars < period - 1 return None.
    """
    n = len(highs)
    if len(lows) != n:
        raise ValueError(f"highs length ({n}) does not match lows length ({len(lows)})")

    results: list[FisherPoint] = []
    if n == 0:
        return results

    prev_raw = 0.0
    prev_fisher = 0.0

    for i in range(n):
        if i < period - 1:
            # Initialization period: before period bars are available
            results.append(
                FisherPoint(
                    bar_index=i,
                    raw=None,
                    fisher=None,
                    trigger=None,
                )
            )
            continue

        # Lookback slice for Highest High and Lowest Low
        h_slice = highs[i - period + 1 : i + 1]
        l_slice = lows[i - period + 1 : i + 1]

        max_h = float(max(h_slice))
        min_l = float(min(l_slice))

        # Price source resolution
        if price_source == "HL2":
            price = (float(highs[i]) + float(lows[i])) / 2.0
        elif price_source == "Close":
            if closes is None:
                raise ValueError("closes sequence required for Close price source")
            price = float(closes[i])
        elif price_source == "HLC3":
            if closes is None:
                raise ValueError("closes sequence required for HLC3 price source")
            price = (float(highs[i]) + float(lows[i]) + float(closes[i])) / 3.0
        elif price_source == "OHLC4":
            if opens is None or closes is None:
                raise ValueError("opens and closes required for OHLC4 price source")
            price = (float(opens[i]) + float(highs[i]) + float(lows[i]) + float(closes[i])) / 4.0
        else:
            raise ValueError(f"Unsupported price_source: {price_source}")

        # Normalization with zero-division safeguard
        denom = max_h - min_l
        if denom > 1e-12:
            ratio = (price - min_l) / denom
        else:
            ratio = 0.5

        raw = 0.33 * 2.0 * (ratio - 0.5) + 0.67 * prev_raw

        # Clamp Raw to prevent math domain error in log
        raw_clamped = max(-0.999, min(0.999, raw))

        # Fisher calculation
        fisher = 0.5 * math.log((1.0 + raw_clamped) / (1.0 - raw_clamped)) + 0.5 * prev_fisher
        trigger = prev_fisher

        results.append(
            FisherPoint(
                bar_index=i,
                raw=raw_clamped,
                fisher=fisher,
                trigger=trigger,
            )
        )

        prev_raw = raw_clamped
        prev_fisher = fisher

    return results
