"""Forward-return prediction analysis (§8 of the priority list, §41).

The question this answers is narrow and it is the only one worth asking:

    After this exact signal, in this instrument, on this timeframe, over this
    date range, what did the next N bars actually do — and how does that differ
    from what *every* bar does?

The second half is the part most research tools omit. A mean forward return of
+0.12% sounds like edge until you learn the unconditional mean for the same
period is +0.11%, at which point the finding evaporates. Every horizon here is
therefore reported next to its unconditional baseline and an excess figure.

Nothing in this module reports "accuracy" or a probability of profit. It reports
sample statistics with the sample size attached, because that is what the data
supports.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from app.indicator_research.backtesting.metrics import forward_return_stats

#: Horizons in bars. Kept short — a long-horizon study needs a long history,
#: and the sample size shrinks with the horizon.
DEFAULT_HORIZONS: tuple[int, ...] = (1, 2, 3, 5, 10, 20)

DISCLAIMER = (
    "Descriptive statistics over a historical sample. A positive mean forward "
    "return after a signal is not a probability of profit, and an in-sample "
    "result without out-of-sample confirmation is a hypothesis, not evidence."
)


def _finite(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _close_series(candles: Sequence[Mapping[str, Any]]) -> list[float | None]:
    return [_finite(c.get("close")) for c in candles]


def forward_returns(
    candles: Sequence[Mapping[str, Any]],
    indices: Sequence[int],
    horizon: int,
    direction: float = 1.0,
) -> list[float]:
    """Percentage forward return for each index, signed by ``direction``.

    Signals whose forward window runs past the end of the data are dropped, not
    truncated: a partial window would be a different (shorter) horizon and would
    bias the result toward whatever happened last.
    """
    closes = _close_series(candles)
    n = len(closes)
    out: list[float] = []
    for index in indices:
        if index < 0 or index + horizon >= n:
            continue
        entry = closes[index]
        exit_price = closes[index + horizon]
        if entry in (None, 0.0) or exit_price is None:
            continue
        out.append(direction * (float(exit_price) - float(entry)) / float(entry) * 100.0)
    return out


def unconditional_forward_returns(
    candles: Sequence[Mapping[str, Any]], horizon: int, direction: float = 1.0
) -> list[float]:
    """The same statistic over every bar — the baseline to beat."""
    closes = _close_series(candles)
    n = len(closes)
    out: list[float] = []
    for index in range(n - horizon):
        entry = closes[index]
        exit_price = closes[index + horizon]
        if entry in (None, 0.0) or exit_price is None:
            continue
        out.append(direction * (float(exit_price) - float(entry)) / float(entry) * 100.0)
    return out


def prediction_analysis(
    *,
    candles: Sequence[Mapping[str, Any]],
    signal_indices: Sequence[int],
    instrument: str,
    timeframe: str,
    signal_definition: str,
    direction: float = 1.0,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
    date_range: Mapping[str, Any] | None = None,
    out_of_sample: bool = False,
) -> dict[str, Any]:
    """Forward-return study for one signal definition.

    Every response carries the context required to interpret a number: the
    instrument, the timeframe, the date range, the signal definition, the
    horizon, the observation count, whether costs were applied and whether the
    sample is in or out of sample.
    """
    horizon_reports: dict[str, Any] = {}
    for horizon in horizons:
        signal_returns = forward_returns(candles, signal_indices, horizon, direction)
        baseline_returns = unconditional_forward_returns(candles, horizon, direction)
        stats = forward_return_stats(signal_returns)
        baseline = forward_return_stats(baseline_returns)
        excess = None
        overlapping = horizon > 1 and stats["n"] > 0
        if stats["mean_pct"] is not None and baseline["mean_pct"] is not None:
            excess = round(stats["mean_pct"] - baseline["mean_pct"], 4)
        horizon_reports[str(horizon)] = {
            "horizon_bars": horizon,
            "signal": stats,
            "unconditional": baseline,
            "excess_mean_pct": excess,
            "excess_positive": bool(excess is not None and excess > 0),
            "overlapping_windows": overlapping,
            "note": (
                "Consecutive signals share forward bars, so observations overlap "
                "and the effective sample is smaller than n. The p-value is "
                "therefore optimistic."
                if overlapping
                else None
            ),
        }

    return {
        "instrument": instrument,
        "timeframe": timeframe,
        "date_range": dict(date_range or {}),
        "signal_definition": signal_definition,
        "direction": "long" if direction >= 0 else "short",
        "n_signals": len(signal_indices),
        "n_bars": len(candles),
        "costs_applied": False,
        "sample_status": "out_of_sample" if out_of_sample else "in_sample",
        "horizons": horizon_reports,
        "context_required": [
            "instrument",
            "timeframe",
            "date_range",
            "signal_definition",
            "prediction_horizon",
            "n_observations",
            "costs_applied",
            "sample_status",
        ],
        "disclaimer": DISCLAIMER,
    }


def time_of_day_returns(
    candles: Sequence[Mapping[str, Any]],
    indices: Sequence[int],
    horizon: int,
    direction: float = 1.0,
) -> dict[str, Any]:
    """Forward returns bucketed by the IST session phase of the signal bar.

    Bucketing by entry time is the cheapest way to ask whether apparent edge is
    really just a session effect (the open and the close have a different return
    distribution from midday).
    """
    from app.indicator_research.backtesting.engine import time_bucket

    buckets: dict[str, list[float]] = {}
    for index, value in zip(
        indices, forward_returns(candles, indices, horizon, direction)
    ):
        bucket = time_bucket(candles[index].get("timestamp") if index < len(candles) else None)
        buckets.setdefault(bucket, []).append(value)
    return {name: forward_return_stats(values) for name, values in sorted(buckets.items())}


__all__ = [
    "DEFAULT_HORIZONS",
    "DISCLAIMER",
    "forward_returns",
    "prediction_analysis",
    "time_of_day_returns",
    "unconditional_forward_returns",
]
