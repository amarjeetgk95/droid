"""Walk-forward validation.

The only honest way to answer "does this keep working?" is to fit on the past,
then trade the untouched future, repeatedly. This implements anchored
walk-forward folds:

    fold 0:  train [──────────]  purge  test [──]
    fold 1:  train [──────────────]  purge  test [──]
    fold 2:  train [──────────────────]  purge  test [──]

Train sets are anchored (they keep all history), test blocks never overlap, and
a purge gap is removed from the end of each train set so an indicator whose
lookback window reaches back N bars cannot straddle the boundary. There is no
shuffling anywhere: bar order is the one thing in a time series that must not be
randomised.

Two numbers matter in the report:

``in_sample_optimism``
    Mean best training objective minus mean test objective. This is the size of
    the lie the in-sample optimizer tells, measured rather than assumed.
``pooled_test``
    Metrics over every out-of-sample trade. Still a small sample — every fold
    contributes only its own test block — so the trade count is reported
    alongside it and folded results are never presented as accuracy.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

import structlog

from app.indicator_research.backtesting.models import BacktestSettings
from app.indicator_research.indicators.base import Candle
from app.indicator_research.research.features import IndicatorSpec
from app.indicator_research.research.optimizer import (
    OptimizationError,
    grid_combinations,
    parameter_space,
)
from app.indicator_research.research.runner import run_once

logger = structlog.get_logger(__name__)

DEFAULT_FOLDS = 5
#: Bars held back after each test block to stop indicator lookback bleeding
#: across the fold boundary.
DEFAULT_PURGE_BARS = 5


def _split_blocks(length: int, folds: int) -> list[tuple[int, int]]:
    """Contiguous ``[start, end)`` blocks, roughly equal, in chronological order."""
    size = length // (folds + 1)
    blocks: list[tuple[int, int]] = []
    for k in range(folds + 1):
        start = k * size
        end = length if k == folds else (k + 1) * size
        blocks.append((start, end))
    return blocks


def walk_forward(
    *,
    candles: Sequence[Candle],
    specs: Sequence[IndicatorSpec],
    long_rule: Mapping[str, Any] | None,
    short_rule: Mapping[str, Any] | None,
    settings: BacktestSettings,
    folds: int = DEFAULT_FOLDS,
    purge_bars: int = DEFAULT_PURGE_BARS,
    objective: str = "total_return_pct",
    max_combinations: int = 60,
    min_trades: int = 5,
    parameter_overrides: Mapping[str, Sequence[Any]] | None = None,
    instrument: str = "",
    timeframe: str = "",
) -> dict[str, Any]:
    """Anchored walk-forward with per-fold parameter selection."""
    if not specs:
        raise OptimizationError("At least one indicator is required for walk-forward.")
    if folds < 2:
        raise OptimizationError("Walk-forward needs at least 2 folds to mean anything.")
    if purge_bars < 0:
        raise OptimizationError("purge_bars cannot be negative.")

    length = len(candles)
    minimum_test = 30
    if length < (folds + 1) * minimum_test:
        raise OptimizationError(
            f"Walk-forward with {folds} folds needs at least "
            f"{(folds + 1) * minimum_test} bars; this range has {length}. "
            "Extend the date range or reduce the fold count."
        )

    primary = specs[0]
    space = parameter_space(primary.indicator_id, parameter_overrides)
    combos = grid_combinations(space)
    total_combinations = len(combos)
    if len(combos) > max_combinations:
        step = len(combos) / max_combinations
        combos = [combos[int(i * step)] for i in range(max_combinations)]

    blocks = _split_blocks(length, folds)
    fold_reports: list[dict[str, Any]] = []
    pooled_trades = 0
    pooled_net = 0.0
    train_objectives: list[float] = []
    test_objectives: list[float] = []

    for fold in range(folds):
        test_start, test_end = blocks[fold + 1]
        train_start, train_end = blocks[0][0], blocks[fold + 1][0]
        purged_train_end = max(train_end - purge_bars, train_start + 10)
        train_candles = candles[train_start:purged_train_end]
        test_candles = candles[test_start:test_end]
        if len(train_candles) < 30 or len(test_candles) < minimum_test:
            continue

        best: dict[str, Any] | None = None
        best_rank: float | None = None
        for combo in combos:
            combo_specs = [IndicatorSpec(primary.indicator_id, dict(combo), "primary")] + [
                IndicatorSpec(s.indicator_id, dict(s.params), s.role) for s in specs[1:]
            ]
            try:
                outcome = run_once(
                    candles=train_candles,
                    specs=combo_specs,
                    long_rule=long_rule,
                    short_rule=short_rule,
                    settings=settings,
                    instrument=instrument,
                    timeframe=timeframe,
                    verify_causality=False,
                    requested_start=f"fold{fold}-train",
                )
            except Exception as e:  # a single bad combo must not kill the fold
                logger.warning(
                    "walkforward_combo_failed", fold=fold, params=dict(combo), error=str(e)[:200]
                )
                continue
            if not outcome.ok or outcome.trade_count < min_trades:
                continue
            raw = outcome.metrics.get(objective)
            if raw is None:
                continue
            try:
                rank = float(raw)
            except (TypeError, ValueError):
                continue
            if math.isnan(rank):
                continue
            if best_rank is None or rank > best_rank:
                best_rank = rank
                best = {"params": dict(combo), "metrics": outcome.metrics}

        if best is None:
            fold_reports.append(
                {
                    "fold": fold,
                    "train_range": [train_start, purged_train_end],
                    "test_range": [test_start, test_end],
                    "train_bars": len(train_candles),
                    "test_bars": len(test_candles),
                    "purge_bars": purge_bars,
                    "skipped": True,
                    "skip_reason": (
                        f"No parameter combination produced at least {min_trades} trades "
                        "on the training block."
                    ),
                }
            )
            continue

        selected_specs = [
            IndicatorSpec(primary.indicator_id, dict(best["params"]), "primary")
        ] + [IndicatorSpec(s.indicator_id, dict(s.params), s.role) for s in specs[1:]]
        test_outcome = run_once(
            candles=test_candles,
            specs=selected_specs,
            long_rule=long_rule,
            short_rule=short_rule,
            settings=settings,
            instrument=instrument,
            timeframe=timeframe,
            verify_causality=False,
            requested_start=f"fold{fold}-test",
        )

        train_objectives.append(float(best["metrics"].get(objective) or 0.0))
        test_value = test_outcome.metrics.get(objective) if test_outcome.ok else None
        if test_value is not None:
            test_objectives.append(float(test_value))
        pooled_trades += test_outcome.trade_count
        pooled_net += float(test_outcome.metrics.get("net_profit") or 0.0)

        fold_reports.append(
            {
                "fold": fold,
                "train_range": [train_start, purged_train_end],
                "test_range": [test_start, test_end],
                "train_bars": len(train_candles),
                "test_bars": len(test_candles),
                "purge_bars": purge_bars,
                "selected_params": dict(best["params"]),
                "train_metrics": best["metrics"],
                "test_metrics": test_outcome.metrics if test_outcome.ok else None,
                "test_error": test_outcome.error if not test_outcome.ok else None,
                "test_trades": test_outcome.trade_count,
                "skipped": False,
            }
        )

    completed = [f for f in fold_reports if not f.get("skipped")]
    optimism: float | None = None
    if train_objectives and test_objectives and len(train_objectives) == len(test_objectives):
        mean_train = sum(train_objectives) / len(train_objectives)
        mean_test = sum(test_objectives) / len(test_objectives)
        optimism = round(mean_train - mean_test, 4)

    warnings: list[str] = []
    if len(completed) < folds:
        warnings.append(
            f"{folds - len(completed)} of {folds} folds were skipped; the out-of-sample "
            "evidence is correspondingly thinner."
        )
    if pooled_trades < 30:
        warnings.append(
            f"Only {pooled_trades} out-of-sample trades were produced. Treat the pooled "
            "figures as a sanity check, not a result."
        )
    if optimism is not None and optimism > 0:
        warnings.append(
            f"Average in-sample objective exceeded out-of-sample by {optimism}. That gap "
            "is the optimism the grid search introduced."
        )

    import hashlib

    oos_payload = f"{instrument}:{timeframe}:{primary.indicator_id}:{blocks}"
    oos_fingerprint = hashlib.sha256(oos_payload.encode("utf-8")).hexdigest()[:16]

    return {
        "instrument": instrument,
        "timeframe": timeframe,
        "indicator_id": primary.indicator_id,
        "objective": objective,
        "folds": folds,
        "folds_completed": len(completed),
        "purge_bars": purge_bars,
        "combinations_per_fold": len(combos),
        "combinations_total": total_combinations,
        "parameter_space": {k: v for k, v in space.items()},
        "fold_reports": fold_reports,
        "pooled": {
            "test_trades": pooled_trades,
            "test_net_profit": round(pooled_net, 2),
            "mean_train_objective": (
                round(sum(train_objectives) / len(train_objectives), 4)
                if train_objectives
                else None
            ),
            "mean_test_objective": (
                round(sum(test_objectives) / len(test_objectives), 4)
                if test_objectives
                else None
            ),
        },
        "in_sample_optimism": optimism,
        "oos_lock": {
            "oos_consumed": True,
            "oos_fingerprint": oos_fingerprint,
            "blocks_count": len(blocks),
        },
        "leakage_audit": {
            "chronological": True,
            "no_shuffle": True,
            "train_precedes_test": all(
                f["train_range"][1] <= f["test_range"][0] for f in completed
            ),
            "test_blocks_disjoint": all(
                completed[i]["test_range"][1] <= completed[i + 1]["test_range"][0]
                for i in range(len(completed) - 1)
            ),
            "purge_bars": purge_bars,
        },
        "warnings": warnings,
    }


__all__ = ["DEFAULT_FOLDS", "DEFAULT_PURGE_BARS", "walk_forward"]

