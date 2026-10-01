"""Pure-stdlib numerical helpers for indicator calculation.

Every helper here is **causal**: the value at index ``i`` depends only on
``values[0..i]``. The whole no-lookahead guarantee rests on that property, and
it is asserted by ``tests/test_indicator_research_causality.py``.

All helpers return a list of the same length as their input. Positions where
the statistic is undefined (the warm-up window) are ``None`` rather than ``0``:
a zero would look like a real reading to the rule engine and would create
phantom signals at the start of every backtest.

No numpy/pandas: these are deliberately dependency-free so indicator modules
stay trivially portable and unit-testable against hand calculations.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Sequence

Numeric = float | int | None


# --------------------------------------------------------------------------- #
# Coercion / small utilities
# --------------------------------------------------------------------------- #
def finite(value: Any) -> float | None:
    """Coerce to a finite float or ``None``.

    ``nan`` / ``inf`` / non-numeric input all collapse to ``None`` so a broken
    upstream candle can never propagate into a signal.
    """
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def series(candles: Sequence[Mapping[str, Any]], field: str) -> list[float | None]:
    """Extract one field from a candle sequence, coercing non-finite to None."""
    return [finite(c.get(field)) for c in candles]


def closes(candles: Sequence[Mapping[str, Any]]) -> list[float | None]:
    return series(candles, "close")


def highs(candles: Sequence[Mapping[str, Any]]) -> list[float | None]:
    return series(candles, "high")


def lows(candles: Sequence[Mapping[str, Any]]) -> list[float | None]:
    return series(candles, "low")


def clamp(value: float, low: float, high: float) -> float:
    return low if value < low else high if value > high else value


def round_or_none(value: float | None, digits: int = 6) -> float | None:
    return None if value is None else round(value, digits)


def last_n(values: Sequence[Numeric], n: int) -> list[float] | None:
    """Window of the last ``n`` finite values ending at the series end.

    Returns ``None`` if the window runs off the start or contains a gap.
    """
    if n <= 0 or len(values) < n:
        return None
    window = values[len(values) - n :]
    out: list[float] = []
    for v in window:
        f = finite(v)
        if f is None:
            return None
        out.append(f)
    return out


# --------------------------------------------------------------------------- #
# Moving averages
# --------------------------------------------------------------------------- #
def sma(values: Sequence[Numeric], n: int) -> list[float | None]:
    """Simple moving average. ``None`` until ``n`` observations exist."""
    out: list[float | None] = [None] * len(values)
    if n <= 0:
        return out
    window: list[float] = []
    total = 0.0
    for i, raw in enumerate(values):
        v = finite(raw)
        # A gap restarts the window: averaging across a hole would silently
        # splice unrelated prices together.
        if v is None:
            window.clear()
            total = 0.0
            continue
        window.append(v)
        total += v
        if len(window) > n:
            total -= window.pop(0)
        if len(window) == n:
            out[i] = total / n
    return out


def ema(values: Sequence[Numeric], n: int) -> list[float | None]:
    """Exponential moving average seeded with the first ``n``-period SMA.

    The SMA seed (rather than seeding on the first close) is the convention
    used by every mainstream charting platform, so research output matches what
    a trader sees on their own chart.
    """
    out: list[float | None] = [None] * len(values)
    if n <= 0:
        return out
    k = 2.0 / (n + 1.0)
    seed_window: list[float] = []
    prev: float | None = None
    for i, raw in enumerate(values):
        v = finite(raw)
        if v is None:
            seed_window.clear()
            prev = None
            continue
        if prev is None:
            seed_window.append(v)
            if len(seed_window) < n:
                continue
            if len(seed_window) > n:
                seed_window.pop(0)
            prev = sum(seed_window) / n
        else:
            prev = v * k + prev * (1.0 - k)
        out[i] = prev
    return out


def wilder(values: Sequence[Numeric], n: int) -> list[float | None]:
    """Wilder's smoothing (RMA). Used by RSI, ATR and ADX.

    Seeded with the SMA of the first ``n`` values, then
    ``smooth[i] = (smooth[i-1] * (n - 1) + value[i]) / n``. That recursive form
    is the one Wilder published; the ``1/n`` EMA variant is a different
    smoothing factor and is not interchangeable.
    """
    out: list[float | None] = [None] * len(values)
    if n <= 0:
        return out
    seed: list[float] = []
    prev: float | None = None
    for i, raw in enumerate(values):
        v = finite(raw)
        if v is None:
            seed.clear()
            prev = None
            continue
        if prev is None:
            seed.append(v)
            if len(seed) < n:
                continue
            if len(seed) > n:
                seed.pop(0)
            prev = sum(seed) / n
        else:
            prev = (prev * (n - 1) + v) / n
        out[i] = prev
    return out


# --------------------------------------------------------------------------- #
# Dispersion / extremes
# --------------------------------------------------------------------------- #
def stdev(values: Sequence[Numeric], n: int, population: bool = True) -> list[float | None]:
    """Rolling standard deviation over ``n`` observations.

    Population (not sample) deviation, matching Bollinger Bands as published.
    """
    out: list[float | None] = [None] * len(values)
    if n <= 1:
        return out
    window: list[float] = []
    total = 0.0
    total_sq = 0.0
    for i, raw in enumerate(values):
        v = finite(raw)
        if v is None:
            window.clear()
            total = total_sq = 0.0
            continue
        window.append(v)
        total += v
        total_sq += v * v
        if len(window) > n:
            old = window.pop(0)
            total -= old
            total_sq -= old * old
        if len(window) == n:
            mean = total / n
            variance = (total_sq / n) - mean * mean
            if variance < 0.0:  # float cancellation on near-constant windows
                variance = 0.0
            out[i] = math.sqrt(variance)
    return out


def highest(values: Sequence[Numeric], n: int) -> list[float | None]:
    """Rolling maximum of the last ``n`` values."""
    return _extreme(values, n, want_max=True)


def lowest(values: Sequence[Numeric], n: int) -> list[float | None]:
    """Rolling minimum of the last ``n`` values."""
    return _extreme(values, n, want_max=False)


def _extreme(values: Sequence[Numeric], n: int, *, want_max: bool) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if n <= 0:
        return out
    window: list[float] = []
    for i, raw in enumerate(values):
        v = finite(raw)
        if v is None:
            window.clear()
            continue
        window.append(v)
        if len(window) > n:
            window.pop(0)
        if len(window) == n:
            out[i] = max(window) if want_max else min(window)
    return out


# --------------------------------------------------------------------------- #
# Volatility on candle series
# --------------------------------------------------------------------------- #
def true_range(candles: Sequence[Mapping[str, Any]]) -> list[float | None]:
    """Wilder true range: max(H-L, |H-prevClose|, |L-prevClose|)."""
    out: list[float | None] = [None] * len(candles)
    prev_close: float | None = None
    for i, c in enumerate(candles):
        h, low, cl = finite(c.get("high")), finite(c.get("low")), finite(c.get("close"))
        if h is None or low is None or cl is None:
            prev_close = cl
            continue
        if prev_close is None:
            out[i] = h - low
        else:
            out[i] = max(h - low, abs(h - prev_close), abs(low - prev_close))
        prev_close = cl
    return out


def atr(candles: Sequence[Mapping[str, Any]], n: int) -> list[float | None]:
    """Average true range (Wilder). ``None`` until ``n`` ranges exist."""
    return wilder(true_range(candles), n)


def typical_price(candle: Mapping[str, Any]) -> float | None:
    """(H + L + C) / 3 — the VWAP / CCI pivot price."""
    h, low, cl = finite(candle.get("high")), finite(candle.get("low")), finite(candle.get("close"))
    if h is None or low is None or cl is None:
        return None
    return (h + low + cl) / 3.0


def median_price(candle: Mapping[str, Any]) -> float | None:
    """(H + L) / 2 — the Stochastic / WaveTrend midpoint."""
    h, low = finite(candle.get("high")), finite(candle.get("low"))
    if h is None or low is None:
        return None
    return (h + low) / 2.0


def vwap(candles: Sequence[Mapping[str, Any]], window: int = 0) -> list[float | None]:
    """Volume-weighted average price using typical price.

    ``window=0`` accumulates from the start of the series (session-anchored
    only if the caller passes a single session). ``window>0`` is a rolling VWAP.
    A zero-volume bar inherits the previous VWAP instead of dividing by zero.
    """
    out: list[float | None] = [None] * len(candles)
    cum_vol = 0.0
    cum_pv = 0.0
    window_buf: list[tuple[float, float]] = []  # (price, volume)
    prev: float | None = None
    for i, c in enumerate(candles):
        tp = typical_price(c)
        vol = finite(c.get("volume")) or 0.0
        if tp is None:
            out[i] = prev
            continue
        if window > 0:
            window_buf.append((tp, vol))
            cum_pv += tp * vol
            cum_vol += vol
            if len(window_buf) > window:
                old_p, old_v = window_buf.pop(0)
                cum_pv -= old_p * old_v
                cum_vol -= old_v
        else:
            cum_pv += tp * vol
            cum_vol += vol
        if cum_vol > 0.0:
            prev = cum_pv / cum_vol
        out[i] = prev
    return out


# --------------------------------------------------------------------------- #
# Regression / slope
# --------------------------------------------------------------------------- #
def linreg_slope(values: Sequence[Numeric], n: int) -> list[float | None]:
    """Slope of the least-squares line over the last ``n`` values (per bar)."""
    out: list[float | None] = [None] * len(values)
    if n <= 1:
        return out
    # x = 0..n-1 ; sum_x and sum_x2 are constants for a fixed window size.
    sum_x = n * (n - 1) / 2.0
    sum_x2 = n * (n - 1) * (2 * n - 1) / 6.0
    denom = n * sum_x2 - sum_x * sum_x
    if denom == 0:
        return out
    window: list[float] = []
    for i, raw in enumerate(values):
        v = finite(raw)
        if v is None:
            window.clear()
            continue
        window.append(v)
        if len(window) > n:
            window.pop(0)
        if len(window) == n:
            sum_y = sum(window)
            sum_xy = sum(x * y for x, y in enumerate(window))
            out[i] = (n * sum_xy - sum_x * sum_y) / denom
    return out


def linreg_value(values: Sequence[Numeric], n: int) -> list[float | None]:
    """Least-squares endpoint (the regression line's value at the last bar)."""
    out: list[float | None] = [None] * len(values)
    if n <= 1:
        return out
    sum_x = n * (n - 1) / 2.0
    sum_x2 = n * (n - 1) * (2 * n - 1) / 6.0
    denom = n * sum_x2 - sum_x * sum_x
    if denom == 0:
        return out
    window: list[float] = []
    for i, raw in enumerate(values):
        v = finite(raw)
        if v is None:
            window.clear()
            continue
        window.append(v)
        if len(window) > n:
            window.pop(0)
        if len(window) == n:
            sum_y = sum(window)
            sum_xy = sum(x * y for x, y in enumerate(window))
            slope = (n * sum_xy - sum_x * sum_y) / denom
            intercept = (sum_y - slope * sum_x) / n
            out[i] = intercept + slope * (n - 1)
    return out


# --------------------------------------------------------------------------- #
# Differences / crossover primitives
# --------------------------------------------------------------------------- #
def diff(values: Sequence[Numeric], lag: int = 1) -> list[float | None]:
    """``values[i] - values[i-lag]`` with ``None`` where either side is missing."""
    out: list[float | None] = [None] * len(values)
    if lag <= 0:
        return out
    for i in range(lag, len(values)):
        a, b = finite(values[i]), finite(values[i - lag])
        out[i] = None if a is None or b is None else a - b
    return out


def cross_above(a: Sequence[Numeric], b: Sequence[Numeric], i: int) -> bool:
    """True when ``a`` crosses above ``b`` at index ``i`` (strict on the bar)."""
    if i < 1 or i >= len(a) or i >= len(b):
        return False
    a0, a1 = finite(a[i - 1]), finite(a[i])
    b0, b1 = finite(b[i - 1]), finite(b[i])
    if None in (a0, a1, b0, b1):
        return False
    return a0 <= b0 and a1 > b1


def cross_below(a: Sequence[Numeric], b: Sequence[Numeric], i: int) -> bool:
    """True when ``a`` crosses below ``b`` at index ``i``."""
    if i < 1 or i >= len(a) or i >= len(b):
        return False
    a0, a1 = finite(a[i - 1]), finite(a[i])
    b0, b1 = finite(b[i - 1]), finite(b[i])
    if None in (a0, a1, b0, b1):
        return False
    return a0 >= b0 and a1 < b1


def ema_alpha(values: Sequence[Numeric], alpha: float) -> list[float | None]:
    """EMA with an explicit smoothing factor (not derived from a period).

    Used by the Schaff Trend Cycle, which smooths with a fixed ``alpha``
    (~0.5) rather than a bar count. Seeded on the first defined value.
    """
    out: list[float | None] = [None] * len(values)
    if not (0.0 < alpha <= 1.0):
        return out
    prev: float | None = None
    for i, raw in enumerate(values):
        v = finite(raw)
        if v is None:
            prev = None
            continue
        prev = v if prev is None else v * alpha + prev * (1.0 - alpha)
        out[i] = prev
    return out


SOURCE_CHOICES = ("close", "open", "high", "low", "hl2", "hlc3", "ohlc4")


def source_series(
    candles: Sequence[Mapping[str, Any]], source: str = "close"
) -> list[float | None]:
    """Extract a standard price source from candles.

    Shared by every indicator that exposes a ``source`` parameter, so the
    choice behaves identically everywhere (and the UI can offer one enum).
    """
    key = (source or "close").strip().lower()
    if key == "close":
        return closes(candles)
    if key == "open":
        return series(candles, "open")
    if key == "high":
        return highs(candles)
    if key == "low":
        return lows(candles)

    out: list[float | None] = [None] * len(candles)
    for i, c in enumerate(candles):
        h, low, cl = finite(c.get("high")), finite(c.get("low")), finite(c.get("close"))
        op = finite(c.get("open"))
        if key == "hl2":
            out[i] = None if h is None or low is None else (h + low) / 2.0
        elif key == "hlc3":
            out[i] = typical_price(c)
        elif key == "ohlc4":
            if None in (op, h, low, cl):
                out[i] = None
            else:
                out[i] = (op + h + low + cl) / 4.0
        else:
            raise ValueError(
                f"Unknown price source '{source}'. Expected one of {list(SOURCE_CHOICES)}"
            )
    return out


PRICE_COLUMNS: tuple[str, ...] = ("open", "high", "low", "close", "volume")


def ohlcv_features(
    candles: Sequence[Mapping[str, Any]],
) -> dict[str, list[float | None]]:
    """The price columns every rule can reference, index-aligned to candles.

    Shared by the engine and the research layer so a rule that references
    ``close`` resolves to exactly the same column in both, and so the causality
    checker rebuilds an identical feature map when it re-runs on a prefix.
    """
    return {name: series(candles, name) for name in PRICE_COLUMNS}


def rolling_mean(values: Iterable[Numeric]) -> float | None:
    """Mean of the given window, or ``None`` if any element is missing."""
    acc: list[float] = []
    for v in values:
        f = finite(v)
        if f is None:
            return None
        acc.append(f)
    return sum(acc) / len(acc) if acc else None
