"""Parameter optimization (§10 in the build order).

A grid search is a machine for finding the best-looking number in a sample. That
is useful and dangerous in equal measure, so this module:

- labels every result ``in_sample_only`` and never calls a grid winner "best
  parameters" without that qualifier;
- reports how many combinations were searched, because the maximum of 500
  samples of noise looks impressive and means nothing;
- requires a minimum trade count before a row can be ranked, so a 2-trade
  fluke cannot top the table;
- refuses work above an explicit compute budget instead of hanging a request;
- points the user at walk-forward, which is the only way to tell a fitted
  pattern from a real one.
"""

from __future__ import annotations

import itertools
import math
from typing import Any, Mapping, Sequence

import structlog

from app.indicator_research.backtesting.models import BacktestSettings
from app.indicator_research.indicators.base import Candle
from app.indicator_research.indicators.registry import IndicatorRegistry
from app.indicator_research.research.features import IndicatorSpec
from app.indicator_research.research.runner import run_once

logger = structlog.get_logger(__name__)

#: Metric keys the optimizer is allowed to rank by.
OBJECTIVE_WHITELIST: tuple[str, ...] = (
    "total_return_pct",
    "net_profit",
    "profit_factor",
    "expectancy_per_trade",
    "sharpe_annualized",
    "sortino_annualized",
    "calmar",
    "win_rate_pct",
    "max_drawdown_pct",
    "payoff_ratio",
    "avg_mfe_pct",
)

#: Objectives where a smaller value is better.
MINIMIZE_OBJECTIVES: frozenset[str] = frozenset({"max_drawdown_pct"})

DEFAULT_MAX_COMBINATIONS = 200
DEFAULT_MIN_TRADES = 5
#: Refuse a request whose estimated bar evaluations exceed this budget.
DEFAULT_WORK_BUDGET = 40_000_000


class OptimizationError(ValueError):
    """Raised when an optimization request cannot be honoured as asked."""


def parameter_space(
    indicator_id: str, overrides: Mapping[str, Sequence[Any]] | None = None
) -> dict[str, list[Any]]:
    """Grid axes for an indicator's declared parameters.

    Each axis defaults to a small, evenly spread set centred on the indicator's
    own default, so a user can press "optimize" without designing a grid and
    still get a sensible search. ``overrides`` replaces individual axes.
    """
    indicator = IndicatorRegistry.get_or_raise(indicator_id)
    space: dict[str, list[Any]] = {}
    for spec in indicator.parameters:
        override = (overrides or {}).get(spec.name)
        if override:
            space[spec.name] = list(override)
            continue
        if spec.type.value == "integer":
            default = int(spec.default)
            lo = int(spec.min) if spec.min is not None else max(2, default // 2)
            hi = int(spec.max) if spec.max is not None else default * 2
            candidates = {
                max(lo, int(default * 0.5)),
                max(lo, int(default * 0.75)),
                default,
                min(hi, int(default * 1.5)),
                min(hi, int(default * 2.0)),
            }
            space[spec.name] = sorted(candidates)
        elif spec.type.value == "number":
            default = float(spec.default)
            lo = float(spec.min) if spec.min is not None else default * 0.5
            hi = float(spec.max) if spec.max is not None else default * 2.0
            space[spec.name] = sorted(
                {
                    round(max(lo, default * 0.5), 6),
                    round(default, 6),
                    round(min(hi, default * 1.5), 6),
                }
            )
        elif spec.type.value == "choice" and spec.options:
            space[spec.name] = list(spec.options)
    return space


def grid_combinations(space: Mapping[str, Sequence[Any]]) -> list[dict[str, Any]]:
    """Full cartesian product of the parameter axes."""
    if not space:
        return [{}]
    names = sorted(space)
    return [
        dict(zip(names, values))
        for values in itertools.product(*(list(space[name]) for name in names))
    ]


def random_combinations(
    space: Mapping[str, Sequence[Any]], n_samples: int = DEFAULT_MAX_COMBINATIONS, seed: int = 42
) -> list[dict[str, Any]]:
    """Randomly sample parameter combinations without replacement."""
    import random

    combos = grid_combinations(space)
    if len(combos) <= n_samples:
        return combos
    rng = random.Random(seed)
    return rng.sample(combos, n_samples)


def expected_max_null_sharpe(trials: int) -> float:
    """Expected maximum Sharpe ratio of N false discoveries under the null hypothesis."""
    if trials <= 1:
        return 0.0
    euler_gamma = 0.5772156649
    log_n = math.log(trials)
    term = math.sqrt(2.0 * log_n)
    correction = (math.log(math.pi) + euler_gamma) / (2.0 * term)
    return max(0.0, term - correction)


def multiple_testing_penalty(best_sharpe: float | None, trials_evaluated: int) -> dict[str, Any]:
    """Deflated Sharpe Ratio / Multiple-testing haircut (Bailey & López de Prado, 2014)."""
    if best_sharpe is None or trials_evaluated <= 1:
        return {
            "trials_evaluated": trials_evaluated,
            "expected_max_null_sharpe": 0.0,
            "haircut_pct": 0.0,
            "adjusted_sharpe": best_sharpe,
            "overfitting_risk": "LOW" if trials_evaluated <= 5 else "MODERATE",
        }
    e_max = expected_max_null_sharpe(trials_evaluated)
    haircut_pct = min(100.0, max(0.0, (e_max / max(0.001, abs(best_sharpe))) * 100.0))
    haircut_factor = max(0.0, 1.0 - (e_max / (abs(best_sharpe) + e_max)))
    adj_sharpe = round(best_sharpe * haircut_factor, 4) if best_sharpe > 0 else best_sharpe
    risk = "HIGH" if trials_evaluated >= 50 or haircut_pct > 60 else ("MODERATE" if trials_evaluated >= 10 else "LOW")
    return {
        "trials_evaluated": trials_evaluated,
        "expected_max_null_sharpe": round(e_max, 4),
        "haircut_pct": round(haircut_pct, 2),
        "adjusted_sharpe": adj_sharpe,
        "overfitting_risk": risk,
    }



def _rank_value(metrics: Mapping[str, Any], objective: str) -> float | None:
    raw = metrics.get(objective)
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if math.isnan(value):
        return None
    return -value if objective in MINIMIZE_OBJECTIVES else value


def optimize(
    *,
    candles: Sequence[Candle],
    specs: Sequence[IndicatorSpec],
    long_rule: Mapping[str, Any] | None,
    short_rule: Mapping[str, Any] | None,
    settings: BacktestSettings,
    objective: str = "total_return_pct",
    search_mode: str = "grid",
    seed: int = 42,
    max_combinations: int = DEFAULT_MAX_COMBINATIONS,
    min_trades: int = DEFAULT_MIN_TRADES,
    parameter_overrides: Mapping[str, Sequence[Any]] | None = None,
    work_budget: int = DEFAULT_WORK_BUDGET,
    instrument: str = "",
    timeframe: str = "",
) -> dict[str, Any]:
    """Grid or Random search over the primary indicator's parameters."""
    if not specs:
        raise OptimizationError("At least one indicator is required to optimize.")
    if objective not in OBJECTIVE_WHITELIST:
        raise OptimizationError(
            f"objective must be one of {list(OBJECTIVE_WHITELIST)}, got '{objective}'"
        )
    if not candles:
        raise OptimizationError("No candles were supplied.")

    primary = specs[0]
    space = parameter_space(primary.indicator_id, parameter_overrides)

    if search_mode == "random":
        combos = random_combinations(space, n_samples=max_combinations, seed=seed)
        total_combinations = len(grid_combinations(space))
    else:
        all_combos = grid_combinations(space)
        total_combinations = len(all_combos)
        if max_combinations < total_combinations:
            step = total_combinations / max_combinations
            combos = [all_combos[int(i * step)] for i in range(max_combinations)]
        else:
            combos = all_combos

    estimated = len(combos) * len(candles)
    if estimated > work_budget:
        raise OptimizationError(
            f"This optimization would evaluate about {estimated:,} bars "
            f"({len(combos)} combinations × {len(candles)} bars), above the "
            f"{work_budget:,} budget. Shorten the date range, reduce the grid, or "
            "use a coarser timeframe."
        )

    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for combo in combos:
        combo_specs = [IndicatorSpec(primary.indicator_id, dict(combo), "primary")] + [
            IndicatorSpec(s.indicator_id, dict(s.params), s.role) for s in specs[1:]
        ]
        outcome = run_once(
            candles=candles,
            specs=combo_specs,
            long_rule=long_rule,
            short_rule=short_rule,
            settings=settings,
            instrument=instrument,
            timeframe=timeframe,
            verify_causality=False,
        )
        if not outcome.ok:
            failures.append({"params": dict(combo), "error": outcome.error})
            continue
        row = {"params": dict(combo), **outcome.to_summary()}
        row["insufficient_trades"] = outcome.trade_count < min_trades
        row["_rank"] = _rank_value(outcome.metrics, objective)
        rows.append(row)

    rankable = [r for r in rows if r["_rank"] is not None and not r["insufficient_trades"]]
    rankable.sort(key=lambda r: r["_rank"], reverse=True)
    for row in rows:
        row.pop("_rank", None)

    ordered = rankable + [r for r in rows if r not in rankable]
    best_item = ordered[0] if ordered else None

    # Multiple testing penalty accounting
    best_sharpe = float(best_item.get("sharpe_annualized")) if (best_item and best_item.get("sharpe_annualized") is not None) else None
    penalty = multiple_testing_penalty(best_sharpe, len(combos))

    warnings: list[str] = []
    if total_combinations > 1:
        warnings.append(
            f"Searched {len(combos)} of {total_combinations} parameter combinations via {search_mode} search. "
            "The best of many attempts on one sample is expected to look better than "
            "it is."
        )
    if penalty.get("overfitting_risk") == "HIGH":
        warnings.append(
            f"High multiple testing overfitting risk: evaluated {len(combos)} trials. "
            f"Expected null max Sharpe is {penalty['expected_max_null_sharpe']}, implying a {penalty['haircut_pct']}% haircut."
        )
    if not rankable:
        warnings.append(
            f"No combination produced at least {min_trades} trades, so nothing could "
            "be ranked. Loosen the signal rule or extend the date range."
        )
    warnings.append(
        "In-sample only. Run a walk-forward test before treating any of these "
        "parameters as evidence."
    )

    return {
        "instrument": instrument,
        "timeframe": timeframe,
        "indicator_id": primary.indicator_id,
        "objective": objective,
        "objective_direction": "minimize" if objective in MINIMIZE_OBJECTIVES else "maximize",
        "search_mode": search_mode,
        "parameter_space": {k: v for k, v in space.items()},
        "combinations_total": total_combinations,
        "combinations_evaluated": len(combos),
        "trials_evaluated": len(combos),
        "truncated": len(combos) < total_combinations,
        "min_trades": min_trades,
        "rows": ordered,
        "best": best_item,
        "multiple_testing_penalty": penalty,
        "failures": failures[:10],
        "in_sample_only": True,
        "causality_verified": False,
        "warnings": warnings,
    }


__all__ = [
    "DEFAULT_MAX_COMBINATIONS",
    "DEFAULT_MIN_TRADES",
    "MINIMIZE_OBJECTIVES",
    "OBJECTIVE_WHITELIST",
    "OptimizationError",
    "expected_max_null_sharpe",
    "grid_combinations",
    "multiple_testing_penalty",
    "optimize",
    "parameter_space",
    "random_combinations",
]

