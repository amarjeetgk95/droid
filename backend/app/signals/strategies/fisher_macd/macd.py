"""DROID MACD + Fisher-9 Exhaustion Research — MACD Indicator (12, 26, 9).

Specification Reference: §8 & §10R.
Precision: float64 throughout.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class MACDPoint:
    """Output for a single bar."""
    bar_index: int
    ema_fast: float | None
    ema_slow: float | None
    macd_line: float | None
    signal_line: float | None
    histogram: float | None

    @property
    def macd(self) -> float | None:
        return self.macd_line

    @property
    def signal(self) -> float | None:
        return self.signal_line


def calculate_macd(
    closes: Sequence[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
    *,
    fast: int | None = None,
    slow: int | None = None,
    signal: int | None = None,
) -> list[MACDPoint]:
    if fast is not None:
        fast_period = fast
    if slow is not None:
        slow_period = slow
    if signal is not None:
        signal_period = signal
    """Calculate standard 12/26/9 MACD series with honest EMA seeding.

    Seeding Rules (DEC-002):
      - Fast EMA (12): SMA over bars 0..11 seeds bar 11; multiplier = 2/(12+1)
      - Slow EMA (26): SMA over bars 0..25 seeds bar 25; multiplier = 2/(26+1)
      - MACD line: Fast EMA - Slow EMA (valid from bar 25 onwards)
      - Signal line (9): SMA over first 9 valid MACD values seeds bar 25+9-1 = 33;
        subsequent bars use multiplier = 2/(9+1) = 0.2
      - Histogram: MACD line - Signal line
    """
    n = len(closes)
    results: list[MACDPoint] = []
    if n == 0:
        return results

    if slow_period <= fast_period:
        raise ValueError(f"slow_period ({slow_period}) must be greater than fast_period ({fast_period})")

    k_fast = 2.0 / (fast_period + 1.0)
    k_slow = 2.0 / (slow_period + 1.0)
    k_sig = 2.0 / (signal_period + 1.0)

    ema_fast_list: list[float | None] = [None] * n
    ema_slow_list: list[float | None] = [None] * n
    macd_list: list[float | None] = [None] * n
    signal_list: list[float | None] = [None] * n
    hist_list: list[float | None] = [None] * n

    # Compute Fast EMA
    if n >= fast_period:
        fast_sma = sum(closes[:fast_period]) / fast_period
        ema_fast_list[fast_period - 1] = fast_sma
        curr = fast_sma
        for i in range(fast_period, n):
            curr = (closes[i] - curr) * k_fast + curr
            ema_fast_list[i] = curr

    # Compute Slow EMA and MACD Line
    if n >= slow_period:
        slow_sma = sum(closes[:slow_period]) / slow_period
        ema_slow_list[slow_period - 1] = slow_sma
        curr = slow_sma
        for i in range(slow_period, n):
            curr = (closes[i] - curr) * k_slow + curr
            ema_slow_list[i] = curr

        for i in range(slow_period - 1, n):
            ef = ema_fast_list[i]
            es = ema_slow_list[i]
            if ef is not None and es is not None:
                macd_list[i] = ef - es

    # Compute Signal Line
    valid_macd_indices = [i for i, val in enumerate(macd_list) if val is not None]
    if len(valid_macd_indices) >= signal_period:
        first_sig_idx = valid_macd_indices[signal_period - 1]
        sig_seed_values = [macd_list[idx] for idx in valid_macd_indices[:signal_period]]  # type: ignore
        sig_curr = sum(sig_seed_values) / signal_period
        signal_list[first_sig_idx] = sig_curr
        hist_list[first_sig_idx] = macd_list[first_sig_idx] - sig_curr  # type: ignore

        for i in range(first_sig_idx + 1, n):
            m = macd_list[i]
            if m is not None:
                sig_curr = (m - sig_curr) * k_sig + sig_curr
                signal_list[i] = sig_curr
                hist_list[i] = m - sig_curr

    for i in range(n):
        results.append(
            MACDPoint(
                bar_index=i,
                ema_fast=ema_fast_list[i],
                ema_slow=ema_slow_list[i],
                macd_line=macd_list[i],
                signal_line=signal_list[i],
                histogram=hist_list[i],
            )
        )

    return results
