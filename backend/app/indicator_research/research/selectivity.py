"""Selectivity Analysis (§5 in the build order).

Selectivity measures how signal frequency, trade count, win rate, and expectancy
change as a signal threshold is tightened or loosened.

A robust indicator displays a smooth, predictable trade-off:
- Stricter thresholds produce fewer signals with higher average expectancy.
- Erratic or non-monotonic response curves indicate overfit noise.
- Extremely high win rates at extreme thresholds usually collapse due to
  insufficient sample size (e.g. 3 trades in 2 years).
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import structlog

from app.indicator_research.backtesting.metrics import forward_return_stats
from app.indicator_research.backtesting.models import BacktestSettings
from app.indicator_research.enums import SampleSizeFlag
from app.indicator_research.indicators.base import Candle
from app.indicator_research.indicators.helpers import PRICE_COLUMNS
from app.indicator_research.research.analysis import forward_returns
from app.indicator_research.research.features import (
    FeatureBuild,
    IndicatorSpec,
    build_features,
)
from app.indicator_research.research.runner import run_once
from app.indicator_research.signals.rules import evaluate_series

logger = structlog.get_logger(__name__)


def sweep_selectivity(
    *,
    candles: Sequence[Candle],
    specs: Sequence[IndicatorSpec],
    feature: str,
    operator: str = ">",
    thresholds: Sequence[float],
    direction: str = "long",
    settings: BacktestSettings | None = None,
    secondary_rule: Mapping[str, Any] | None = None,
    forward_horizon: int = 5,
    min_trades: int = 10,
    instrument: str = "",
    timeframe: str = "",
    prebuilt: FeatureBuild | None = None,
) -> dict[str, Any]:
    """Evaluate performance across an array of threshold values."""
    if not candles:
        return {"ok": False, "error": "No candles provided."}
    if not specs:
        return {"ok": False, "error": "At least one indicator spec is required."}
    if not thresholds:
        return {"ok": False, "error": "At least one threshold value is required."}

    build = prebuilt if prebuilt is not None else build_features(candles, specs)
    if not build.ok:
        return {"ok": False, "error": "; ".join(build.errors), "warnings": build.warnings}

    known_features = set(build.features) | set(PRICE_COLUMNS)
    if feature not in known_features:
        return {
            "ok": False,
            "error": f"Feature '{feature}' not found in available features: {sorted(known_features)}",
        }

    active_settings = settings or BacktestSettings()
    dir_sign = 1.0 if direction.lower() == "long" else -1.0
    n_bars = len(candles)

    rows: list[dict[str, Any]] = []
    signal_counts: list[int] = []

    for th in thresholds:
        threshold_val = float(th)
        base_cond: dict[str, Any] = {"left": feature, "operator": operator, "right": threshold_val}
        if secondary_rule:
            sec_conds = secondary_rule.get("conditions", [secondary_rule])
            rule: dict[str, Any] = {"operator": "AND", "conditions": [base_cond] + list(sec_conds)}
        else:
            rule = {"operator": "AND", "conditions": [base_cond]}

        long_rule = rule if direction.lower() == "long" else None
        short_rule = rule if direction.lower() == "short" else None

        # (1) Backtest evaluation
        outcome = run_once(
            candles=candles,
            specs=specs,
            long_rule=long_rule,
            short_rule=short_rule,
            settings=active_settings,
            instrument=instrument,
            timeframe=timeframe,
            verify_causality=False,
            prebuilt=build,
        )

        metrics = outcome.metrics if outcome.ok else {}
        trade_count = outcome.trade_count if outcome.ok else 0
        sig_count = outcome.signal_count if outcome.ok else 0
        signal_counts.append(sig_count)

        # Sample size tiering
        if trade_count >= 30:
            sample_flag = SampleSizeFlag.SUFFICIENT.value
        elif trade_count >= 10:
            sample_flag = SampleSizeFlag.MARGINAL.value
        else:
            sample_flag = SampleSizeFlag.INSUFFICIENT.value

        # (2) Pure statistical forward return (cost-free horizon evaluation)
        rule_signals = evaluate_series(rule, build.features, n_bars)
        for i in range(min(build.warmup_bars, n_bars)):
            rule_signals[i] = False
        sig_indices = [i for i, fired in enumerate(rule_signals) if fired]
        fwd_rets = forward_returns(candles, sig_indices, horizon=forward_horizon, direction=dir_sign)
        fwd_stats = forward_return_stats(fwd_rets)

        selectivity_pct = round((sig_count / max(1, n_bars)) * 100.0, 3)

        rows.append(
            {
                "threshold": threshold_val,
                "signal_count": sig_count,
                "trade_count": trade_count,
                "selectivity_pct": selectivity_pct,
                "win_rate_pct": metrics.get("win_rate_pct"),
                "expectancy_per_trade": metrics.get("expectancy_per_trade"),
                "profit_factor": metrics.get("profit_factor"),
                "total_return_pct": metrics.get("total_return_pct"),
                "max_drawdown_pct": metrics.get("max_drawdown_pct"),
                "sharpe_annualized": metrics.get("sharpe_annualized"),
                "sample_size_flag": sample_flag,
                "forward_stats": {
                    "horizon_bars": forward_horizon,
                    "mean_pct": fwd_stats.get("mean_pct"),
                    "median_pct": fwd_stats.get("median_pct"),
                    "win_pct": fwd_stats.get("win_pct"),
                    "n": fwd_stats.get("n"),
                },
            }
        )

    # Monotonicity check on signal count
    is_monotonic_decreasing = all(
        signal_counts[i] >= signal_counts[i + 1] for i in range(len(signal_counts) - 1)
    )
    is_monotonic_increasing = all(
        signal_counts[i] <= signal_counts[i + 1] for i in range(len(signal_counts) - 1)
    )
    monotonic = is_monotonic_decreasing or is_monotonic_increasing

    # Find optimal operating point (highest expectancy with sufficient or marginal sample)
    viable = [r for r in rows if r["trade_count"] >= min_trades and r["expectancy_per_trade"] is not None]
    best_row = max(viable, key=lambda r: float(r["expectancy_per_trade"] or 0.0)) if viable else None

    warnings: list[str] = []
    if not monotonic:
        warnings.append(
            "Signal frequency does not vary monotonically with threshold. "
            "Inspect rule structure for non-linear interactions."
        )
    insufficient_count = sum(1 for r in rows if r["sample_size_flag"] == SampleSizeFlag.INSUFFICIENT.value)
    if insufficient_count > len(rows) // 2:
        warnings.append(
            f"{insufficient_count} of {len(rows)} threshold levels have fewer than 10 trades. "
            "High win rates at extreme thresholds are likely sample noise."
        )
    if not viable:
        warnings.append(
            f"No threshold produced at least {min_trades} trades. Broaden the threshold range or date range."
        )

    return {
        "ok": True,
        "instrument": instrument,
        "timeframe": timeframe,
        "feature": feature,
        "operator": operator,
        "direction": direction,
        "forward_horizon": forward_horizon,
        "n_bars": n_bars,
        "monotonic": monotonic,
        "optimal_point": best_row,
        "rows": rows,
        "warnings": warnings,
    }


__all__ = ["sweep_selectivity"]
