"""Ablation Analysis (§8 in the build order).

Ablation systematically removes one indicator component at a time from a
multi-indicator strategy setup to measure its true marginal contribution.

Key questions answered:
1. Does this indicator actually add value, or is it decorative noise?
2. If we remove Indicator X, does Sharpe ratio increase (meaning X was hurting)?
3. What is the standalone performance of each component vs the ensemble?
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import structlog

from app.indicator_research.backtesting.models import BacktestSettings
from app.indicator_research.indicators.base import Candle
from app.indicator_research.indicators.registry import IndicatorRegistry
from app.indicator_research.research.features import IndicatorSpec
from app.indicator_research.research.runner import run_once

logger = structlog.get_logger(__name__)


def _filter_rule(rule: Mapping[str, Any] | None, excluded_outputs: set[str]) -> dict[str, Any] | None:
    """Recursively strip conditions that reference any excluded indicator outputs."""
    if rule is None:
        return None
    operator = rule.get("operator", "AND")
    conditions = rule.get("conditions", [])
    valid_conditions = []
    for cond in conditions:
        if "conditions" in cond:
            sub = _filter_rule(cond, excluded_outputs)
            if sub and sub.get("conditions"):
                valid_conditions.append(sub)
        else:
            left = cond.get("left")
            right = cond.get("right")
            if isinstance(left, str) and left in excluded_outputs:
                continue
            if isinstance(right, str) and right in excluded_outputs:
                continue
            valid_conditions.append(dict(cond))
    if not valid_conditions:
        return None
    return {"operator": operator, "conditions": valid_conditions}



def run_ablation_study(
    *,
    candles: Sequence[Candle],
    specs: Sequence[IndicatorSpec],
    long_rule: Mapping[str, Any] | None,
    short_rule: Mapping[str, Any] | None,
    settings: BacktestSettings,
    objective: str = "sharpe_annualized",
    instrument: str = "",
    timeframe: str = "",
) -> dict[str, Any]:
    """Execute ablation study across all components in the spec."""
    if not specs:
        return {"ok": False, "error": "At least one indicator spec is required."}
    if len(specs) < 2:
        return {
            "ok": False,
            "error": "Ablation study requires at least 2 indicators to measure component contributions.",
        }

    # (1) Full ensemble baseline
    full_outcome = run_once(
        candles=candles,
        specs=specs,
        long_rule=long_rule,
        short_rule=short_rule,
        settings=settings,
        instrument=instrument,
        timeframe=timeframe,
        verify_causality=False,
    )
    if not full_outcome.ok:
        return {"ok": False, "error": f"Full model run failed: {full_outcome.error}"}

    base_summary = full_outcome.to_summary()
    base_sharpe = float(base_summary.get("sharpe_annualized") or 0.0)
    base_return = float(base_summary.get("total_return_pct") or 0.0)
    base_win_rate = float(base_summary.get("win_rate_pct") or 0.0)
    base_expectancy = float(base_summary.get("expectancy_per_trade") or 0.0)

    ablations: list[dict[str, Any]] = []
    redundant_components: list[str] = []

    # (2) Leave-one-out testing
    for i, target_spec in enumerate(specs):
        indicator_id = target_spec.indicator_id
        meta = IndicatorRegistry.get(indicator_id)
        outputs = set(meta.metadata.output_names()) if meta else set()

        # Build subset with target removed
        sub_specs = [s for j, s in enumerate(specs) if j != i]
        sub_long = _filter_rule(long_rule, outputs)
        sub_short = _filter_rule(short_rule, outputs)

        sub_outcome = run_once(
            candles=candles,
            specs=sub_specs,
            long_rule=sub_long,
            short_rule=sub_short,
            settings=settings,
            instrument=instrument,
            timeframe=timeframe,
            verify_causality=False,
        )

        if not sub_outcome.ok:
            ablations.append(
                {
                    "excluded_indicator": indicator_id,
                    "role": target_spec.role,
                    "error": sub_outcome.error,
                    "marginal_sharpe_delta": 0.0,
                    "verdict": "ERROR",
                }
            )
            continue

        sub_summary = sub_outcome.to_summary()
        sub_sharpe = float(sub_summary.get("sharpe_annualized") or 0.0)
        sub_return = float(sub_summary.get("total_return_pct") or 0.0)
        sub_win_rate = float(sub_summary.get("win_rate_pct") or 0.0)
        sub_expectancy = float(sub_summary.get("expectancy_per_trade") or 0.0)

        delta_sharpe = round(base_sharpe - sub_sharpe, 4)
        delta_return = round(base_return - sub_return, 4)
        delta_win_rate = round(base_win_rate - sub_win_rate, 4)
        delta_expectancy = round(base_expectancy - sub_expectancy, 4)

        if delta_sharpe > 0.15:
            verdict = "CRITICAL_VALUE_ADD"
        elif delta_sharpe > 0.0:
            verdict = "MODERATE_VALUE_ADD"
        elif delta_sharpe == 0.0:
            verdict = "REDUNDANT"
            redundant_components.append(indicator_id)
        else:
            verdict = "HARMFUL_OVERFIT"
            redundant_components.append(indicator_id)

        ablations.append(
            {
                "excluded_indicator": indicator_id,
                "role": target_spec.role,
                "metrics_without_component": sub_summary,
                "delta_sharpe": delta_sharpe,
                "delta_return_pct": delta_return,
                "delta_win_rate_pct": delta_win_rate,
                "delta_expectancy": delta_expectancy,
                "verdict": verdict,
            }
        )

    warnings: list[str] = []
    if redundant_components:
        warnings.append(
            f"Indicators {redundant_components} produce non-positive marginal contribution to Sharpe. "
            "Consider pruning them to reduce model complexity and avoid overfitting."
        )

    return {
        "ok": True,
        "instrument": instrument,
        "timeframe": timeframe,
        "full_model": base_summary,
        "ablations": ablations,
        "redundant_components": redundant_components,
        "warnings": warnings,
    }


__all__ = ["run_ablation_study"]
