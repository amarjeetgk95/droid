"""Indicator comparison (§11, §40).

What this actually compares
---------------------------
An indicator with no signal rule produces no trades, so a "comparison of
indicators" is necessarily a comparison of *(indicator, rule set, exit rules,
costs, execution model)*. Two indicators evaluated under different rules are
different strategies, and the report says so on every row by carrying the rule
summary next to the metrics.

The one rule-level concession is that when a shared rule set references a
feature an indicator does not define, that row is reported as *not comparable*
with the reason, rather than silently evaluated against a half-populated
feature map.

§40 also warns against assuming combinations help. The ``combinations`` block
tests that directly: it runs the single-indicator baselines and then the
stacked rule set through the identical harness so the arithmetic is visible.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

import structlog

from app.indicator_research.backtesting.models import BacktestSettings
from app.indicator_research.indicators.base import Candle
from app.indicator_research.indicators.helpers import PRICE_COLUMNS
from app.indicator_research.indicators.registry import IndicatorRegistry
from app.indicator_research.research.features import (
    IndicatorSpec,
    build_features,
    default_rule_set,
)
from app.indicator_research.research.runner import run_once
from app.indicator_research.signals.rules import (
    describe_rule,
    normalize_rule,
    unknown_features,
)

logger = structlog.get_logger(__name__)


def _needs_atr(settings: BacktestSettings) -> bool:
    exit_settings = settings.exits
    return "atr" in (exit_settings.stop_mode, exit_settings.target_mode)


def compare_indicators(
    *,
    candles: Sequence[Candle],
    indicator_ids: Sequence[str],
    settings: BacktestSettings,
    long_rule: Mapping[str, Any] | None = None,
    short_rule: Mapping[str, Any] | None = None,
    use_default_rules: bool = True,
    objective: str = "total_return_pct",
    instrument: str = "",
    timeframe: str = "",
) -> dict[str, Any]:
    """Run several indicators through one harness and tabulate the results."""
    if not indicator_ids:
        raise ValueError("At least two indicators are needed for a comparison.")

    rows: list[dict[str, Any]] = []
    for indicator_id in indicator_ids:
        indicator = IndicatorRegistry.get(indicator_id)
        if indicator is None:
            rows.append(
                {
                    "indicator_id": indicator_id,
                    "comparable": False,
                    "reason": f"Indicator '{indicator_id}' is not registered.",
                }
            )
            continue

        specs = [IndicatorSpec(indicator_id, {}, "primary")]
        if _needs_atr(settings) and indicator_id != "atr":
            specs.append(IndicatorSpec("atr", {}, "overlay"))

        row_long = long_rule
        row_short = short_rule
        rule_source = "shared"
        if row_long is None and row_short is None:
            if not use_default_rules:
                rows.append(
                    {
                        "indicator_id": indicator_id,
                        "name": indicator.name,
                        "comparable": False,
                        "reason": (
                            "No rules supplied and default rules are disabled, so there "
                            "is nothing to trade."
                        ),
                    }
                )
                continue
            defaults = default_rule_set(indicator_id)
            if not defaults:
                rows.append(
                    {
                        "indicator_id": indicator_id,
                        "name": indicator.name,
                        "comparable": False,
                        "reason": (
                            f"'{indicator.name}' ships no default signal rule (it has no "
                            "directional content on its own) and no shared rule was given."
                        ),
                    }
                )
                continue
            row_long = defaults.get("long")
            row_short = defaults.get("short")
            rule_source = "indicator_default"

        # Feature availability: a shared rule that references a feature this
        # indicator does not produce cannot be evaluated honestly.
        probe = build_features(candles[: min(len(candles), 200)], specs)
        if not probe.ok:
            rows.append(
                {
                    "indicator_id": indicator_id,
                    "name": indicator.name,
                    "comparable": False,
                    "reason": "; ".join(probe.errors),
                }
            )
            continue
        known = set(probe.features) | set(PRICE_COLUMNS)
        missing = _missing_features(row_long, row_short, known)
        if missing:
            rows.append(
                {
                    "indicator_id": indicator_id,
                    "name": indicator.name,
                    "comparable": False,
                    "reason": (
                        f"Rule references feature(s) {sorted(missing)} that this "
                        "indicator does not produce."
                    ),
                }
            )
            continue

        outcome = run_once(
            candles=candles,
            specs=specs,
            long_rule=row_long,
            short_rule=row_short,
            settings=settings,
            instrument=instrument,
            timeframe=timeframe,
        )
        row: dict[str, Any] = {
            "indicator_id": indicator_id,
            "name": indicator.name,
            "category": indicator.category.value,
            "output_type": indicator.metadata.output_type.value,
            "comparable": outcome.ok,
            "rule_source": rule_source,
            "long_rule": describe_rule(normalize_rule(row_long)),
            "short_rule": describe_rule(normalize_rule(row_short)),
            "reason": outcome.error,
        }
        row.update(outcome.to_summary())
        rank = outcome.metrics.get(objective) if outcome.ok else None
        try:
            row["_rank"] = None if rank is None else float(rank)
        except (TypeError, ValueError):
            row["_rank"] = None
        rows.append(row)

    comparable = [r for r in rows if r.get("comparable")]
    comparable.sort(
        key=lambda r: (r.get("_rank") is not None, r.get("_rank") or float("-inf")),
        reverse=True,
    )
    ordered = comparable + [r for r in rows if not r.get("comparable")]
    for row in ordered:
        row.pop("_rank", None)

    warnings: list[str] = []
    if len(comparable) < 2:
        warnings.append(
            "Fewer than two indicators produced a comparable result, so nothing can be "
            "ranked."
        )
    warnings.append(
        "Rows are (indicator + signal rule + execution settings) bundles. A difference "
        "in rule wording is as capable of explaining a difference in results as the "
        "indicator is."
    )
    if any(r.get("rule_source") == "indicator_default" for r in comparable):
        warnings.append(
            "Some rows used each indicator's own default rule, which is convenient but "
            "not a like-for-like comparison. Share one rule set to isolate the indicator."
        )

    return {
        "instrument": instrument,
        "timeframe": timeframe,
        "objective": objective,
        "rows": ordered,
        "comparable_count": len(comparable),
        "warnings": warnings,
        "in_sample_only": True,
        "note": (
            "Ranking here is descriptive. A higher in-sample objective is not evidence "
            "that one indicator is better; it is evidence that one configuration fitted "
            "this sample better."
        ),
    }


def _missing_features(
    long_rule: Mapping[str, Any] | None,
    short_rule: Mapping[str, Any] | None,
    known: set[str],
) -> set[str]:
    """Features referenced by either rule that are not in ``known``."""
    missing: set[str] = set()
    for rule in (long_rule, short_rule):
        missing.update(unknown_features(rule, known))
    return missing


def compare_rule_sets(
    *,
    candles: Sequence[Candle],
    indicator_id: str,
    rule_sets: Sequence[Mapping[str, Any]],
    settings: BacktestSettings,
    objective: str = "total_return_pct",
    instrument: str = "",
    timeframe: str = "",
) -> dict[str, Any]:
    """Compare several signal definitions for one indicator.

    This is the honest complement to :func:`compare_indicators`: hold the
    indicator fixed, vary the rule, and see how much of the result was the
    signal definition.
    """
    rows: list[dict[str, Any]] = []
    specs = [IndicatorSpec(indicator_id, {}, "primary")]
    if _needs_atr(settings) and indicator_id != "atr":
        specs.append(IndicatorSpec("atr", {}, "overlay"))

    for index, rule_set in enumerate(rule_sets):
        long_rule = rule_set.get("long")
        short_rule = rule_set.get("short")
        try:
            normalized_long = normalize_rule(long_rule)
            normalized_short = normalize_rule(short_rule)
        except Exception as e:
            rows.append(
                {
                    "rule_index": index,
                    "label": rule_set.get("label") or f"rule set {index + 1}",
                    "comparable": False,
                    "reason": str(e),
                }
            )
            continue
        outcome = run_once(
            candles=candles,
            specs=specs,
            long_rule=normalized_long,
            short_rule=normalized_short,
            settings=settings,
            instrument=instrument,
            timeframe=timeframe,
        )
        row = {
            "rule_index": index,
            "label": rule_set.get("label") or f"rule set {index + 1}",
            "comparable": outcome.ok,
            "long_rule": describe_rule(normalized_long),
            "short_rule": describe_rule(normalized_short),
            "reason": outcome.error,
            "rule_causal": outcome.validation.get("repaint_free"),
            "no_lookahead": outcome.validation.get("no_lookahead"),
        }
        row.update(outcome.to_summary())
        rank = outcome.metrics.get(objective) if outcome.ok else None
        try:
            row["_rank"] = None if rank is None else float(rank)
        except (TypeError, ValueError):
            row["_rank"] = None
        rows.append(row)

    rows.sort(
        key=lambda r: (r.get("_rank") is not None, r.get("_rank") or float("-inf")),
        reverse=True,
    )
    for row in rows:
        row.pop("_rank", None)

    return {
        "indicator_id": indicator_id,
        "instrument": instrument,
        "timeframe": timeframe,
        "objective": objective,
        "rows": rows,
        "spread": _spread(rows, objective),
        "note": (
            "Same indicator, different signal definitions. If the spread is large, the "
            "rule wording is doing more work than the indicator."
        ),
    }


def _spread(rows: Sequence[Mapping[str, Any]], objective: str) -> dict[str, Any]:
    values: list[float] = []
    for row in rows:
        if not row.get("comparable"):
            continue
        raw = row.get(objective)
        if raw is None:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if not math.isnan(value):
            values.append(value)
    if not values:
        return {"min": None, "max": None, "spread": None, "n": 0}
    return {
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "spread": round(max(values) - min(values), 4),
        "n": len(values),
    }


__all__ = ["compare_indicators", "compare_rule_sets"]
