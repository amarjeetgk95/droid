"""DROID MACD + Fisher-9 Exhaustion Research — Wilder's ATR Indicator.

Specification Reference: DEC-003.
Precision: float64 throughout.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class ATRPoint:
    """Output for a single bar."""
    bar_index: int
    tr: float
    atr: float | None

    def __float__(self) -> float:
        if self.atr is None:
            raise TypeError("Cannot convert None ATR to float")
        return float(self.atr)


def calculate_atr_series(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> list[ATRPoint]:
    """Calculate 14-period Wilder's Average True Range.

    Seeding Rules (DEC-003):
      - TR[i] = max(High[i] - Low[i], abs(High[i] - Close[i-1]), abs(Low[i] - Close[i-1]))
      - TR[0] = High[0] - Low[0]
      - Bar period-1 seeds ATR with SMA(TR, period)
      - Subsequent bars: ATR[t] = (ATR[t-1] * (period - 1) + TR[t]) / period
    """
    n = len(closes)
    if n == 0 or len(highs) != n or len(lows) != n:
        raise ValueError("highs, lows, and closes must all have the same non-zero length")

    tr_list: list[float] = [float(highs[0] - lows[0])]
    for i in range(1, n):
        h = float(highs[i])
        l = float(lows[i])
        prev_c = float(closes[i - 1])
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        tr_list.append(tr)

    atr_vals: list[float | None] = [None] * n
    if n >= period:
        seed_atr = sum(tr_list[:period]) / period
        atr_vals[period - 1] = seed_atr
        curr_atr = seed_atr

        for i in range(period, n):
            curr_atr = (curr_atr * (period - 1) + tr_list[i]) / period
            atr_vals[i] = curr_atr
    return atr_vals
