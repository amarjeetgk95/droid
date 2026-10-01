"""Robustness and Sensitivity Analysis (§8 in the build order).

Evaluates whether an indicator configuration represents a robust edge or an overfit
artifact:
1. **Parameter Perturbation / Sensitivity**: Tests performance under small shifts
   in parameter values (+/- 10%, +/- 20% or +/- 1, 2 steps).
   - Broad plateaus indicate true structural edge.
   - Isolated sharp peaks ("cliffs") indicate overfit curve-fitting.
2. **Cost Stress Testing**: Tests strategy resilience under 1.5x, 2.0x, 3.0x slippage
   and commission loads to find the breakeven cost threshold.
"""

from __future__ import annotations

import copy
import math
from typing import Any, Mapping, Sequence

import structlog

from app.indicator_research.backtesting.models import BacktestSettings
from app.indicator_research.indicators.base import Candle
from app.indicator_research.indicators.registry import IndicatorRegistry
from app.indicator_research.research.features import IndicatorSpec
from app.indicator_research.research.runner import run_once

logger = structlog.get_logger(__name__)

DEFAULT_PERTURBATIONS = (-0.20, -0.10, 0.10, 0.20)
DEFAULT_COST_MULTIPLIERS = (1.0, 1.5, 2.0, 3.0)


def _perturb_param(val: Any, delta_pct: float, param_type: str, min_val: float | None, max_val: float | None) -> Any:
    if param_type == "integer":
        int_val = int(val)
        step = max(1, round(abs(int_val * delta_pct)))
        new_val = int_val + (step if delta_pct > 0 else -step)
        if min_val is not None:
            new_val = max(int(min_val), new_val)
        if max_val is not None:
            new_val = min(int(max_val), new_val)
        return new_val
    elif param_type == "number":
        float_val = float(val)
        new_val = round(float_val * (1.0 + delta_pct), 4)
        if min_val is not None:
            new_val = max(float(min_val), new_val)
        if max_val is not None:
            new_val = min(float(max_val), new_val)
        return new_val
    return val


def run_robustness_test(
    *,
    candles: Sequence[Candle],
    specs: Sequence[IndicatorSpec],
    long_rule: Mapping[str, Any] | None,
    short_rule: Mapping[str, Any] | None,
    settings: BacktestSettings,
    perturbation_pcts: Sequence[float] = DEFAULT_PERTURBATIONS,
    cost_multipliers: Sequence[float] = DEFAULT_COST_MULTIPLIERS,
    instrument: str = "",
    timeframe: str = "",
) -> dict[str, Any]:
    """Execute parameter perturbation and cost stress testing."""
    if not specs:
        return {"ok": False, "error": "At least one indicator spec is required."}
    if not candles:
        return {"ok": False, "error": "No candles provided."}

    # (1) Base Evaluation
    base_outcome = run_once(
        candles=candles,
        specs=specs,
        long_rule=long_rule,
        short_rule=short_rule,
        settings=settings,
        instrument=instrument,
        timeframe=timeframe,
        verify_causality=False,
    )
    if not base_outcome.ok:
        return {"ok": False, "error": f"Base run failed: {base_outcome.error}"}

    base_summary = base_outcome.to_summary()
    base_sharpe = float(base_summary.get("sharpe_annualized") or 0.0)
    base_expectancy = float(base_summary.get("expectancy_per_trade") or 0.0)
    base_profit = float(base_summary.get("net_profit") or 0.0)

    # (2) Parameter Perturbation Analysis
    primary_spec = specs[0]
    indicator = IndicatorRegistry.get(primary_spec.indicator_id)
    param_meta = {p.name: p for p in (indicator.parameters if indicator else [])}

    perturbation_results: list[dict[str, Any]] = []
    cliff_detected = False

    for param_name, current_val in primary_spec.params.items():
        spec_def = param_meta.get(param_name)
        if not spec_def or spec_def.type.value not in ("integer", "number"):
            continue

        for delta in perturbation_pcts:
            perturbed_val = _perturb_param(
                current_val,
                delta,
                spec_def.type.value,
                spec_def.min,
                spec_def.max,
            )
            if perturbed_val == current_val:
                continue

            perturbed_params = dict(primary_spec.params)
            perturbed_params[param_name] = perturbed_val
            perturbed_specs = [
                IndicatorSpec(primary_spec.indicator_id, perturbed_params, primary_spec.role)
            ] + list(specs[1:])

            outcome = run_once(
                candles=candles,
                specs=perturbed_specs,
                long_rule=long_rule,
                short_rule=short_rule,
                settings=settings,
                instrument=instrument,
                timeframe=timeframe,
                verify_causality=False,
            )
            if not outcome.ok:
                continue

            summary = outcome.to_summary()
            sharpe = float(summary.get("sharpe_annualized") or 0.0)
            expectancy = float(summary.get("expectancy_per_trade") or 0.0)

            # Cliff detection: single small perturbation causes performance collapse (> 50% drop or negative)
            if base_expectancy > 0 and (expectancy < 0 or (base_expectancy - expectancy) / base_expectancy > 0.50):
                cliff_detected = True

            perturbation_results.append(
                {
                    "parameter": param_name,
                    "delta_pct": delta,
                    "perturbed_value": perturbed_val,
                    "sharpe_annualized": sharpe,
                    "expectancy_per_trade": expectancy,
                    "total_return_pct": summary.get("total_return_pct"),
                    "win_rate_pct": summary.get("win_rate_pct"),
                    "trade_count": summary.get("trade_count"),
                }
            )

    # Stability score calculation
    if perturbation_results:
        positive_expectancy_count = sum(
            1 for r in perturbation_results if float(r.get("expectancy_per_trade") or 0.0) > 0
        )
        stability_score = round((positive_expectancy_count / len(perturbation_results)) * 100.0, 1)

        sharpes = [float(r.get("sharpe_annualized") or 0.0) for r in perturbation_results]
        mean_sharpe = sum(sharpes) / len(sharpes)
        std_sharpe = math.sqrt(sum((s - mean_sharpe) ** 2 for s in sharpes) / len(sharpes))
        cv = std_sharpe / max(0.1, abs(mean_sharpe))
        plateau_detected = cv < 0.40 and stability_score >= 70.0
    else:
        stability_score = 100.0
        plateau_detected = True

    # (3) Cost Stress Testing
    cost_stress_results: list[dict[str, Any]] = []
    breakeven_multiplier: float | None = None

    from dataclasses import replace

    for mult in cost_multipliers:
        stressed_costs = replace(
            settings.costs,
            slippage_bps=settings.costs.slippage_bps * mult,
            brokerage_bps=settings.costs.brokerage_bps * mult,
            exchange_bps=settings.costs.exchange_bps * mult,
        )
        stressed_settings = replace(settings, costs=stressed_costs)

        c_outcome = run_once(
            candles=candles,
            specs=specs,
            long_rule=long_rule,
            short_rule=short_rule,
            settings=stressed_settings,
            instrument=instrument,
            timeframe=timeframe,
            verify_causality=False,
        )
        if not c_outcome.ok:
            continue
        c_summary = c_outcome.to_summary()
        c_profit = float(c_summary.get("net_profit") or 0.0)

        cost_stress_results.append(
            {
                "multiplier": mult,
                "net_profit": c_profit,
                "total_return_pct": c_summary.get("total_return_pct"),
                "total_costs": c_summary.get("total_costs"),
                "profit_factor": c_summary.get("profit_factor"),
                "expectancy_per_trade": c_summary.get("expectancy_per_trade"),
            }
        )

        if base_profit > 0 and c_profit <= 0 and breakeven_multiplier is None:
            breakeven_multiplier = mult

    # Overall Verdict
    if stability_score >= 75.0 and not cliff_detected and (breakeven_multiplier is None or breakeven_multiplier > 1.5):
        verdict = "ROBUST"
    elif stability_score >= 50.0 and not cliff_detected:
        verdict = "MODERATELY_FRAGILE"
    else:
        verdict = "HIGHLY_FRAGILE"

    warnings: list[str] = []
    if cliff_detected:
        warnings.append(
            "Parameter cliff risk detected: a minor parameter shift causes performance to collapse by > 50%. "
            "High probability of in-sample curve fitting."
        )
    if breakeven_multiplier is not None and breakeven_multiplier <= 1.5:
        warnings.append(
            f"Strategy turns negative under a {breakeven_multiplier}x cost multiplier. "
            "Lacks sufficient profit buffer against real-world slippage."
        )

    return {
        "ok": True,
        "instrument": instrument,
        "timeframe": timeframe,
        "verdict": verdict,
        "stability_score_pct": stability_score,
        "plateau_detected": plateau_detected,
        "cliff_detected": cliff_detected,
        "breakeven_cost_multiplier": breakeven_multiplier,
        "base_metrics": base_summary,
        "perturbation_results": perturbation_results,
        "cost_stress_results": cost_stress_results,
        "warnings": warnings,
    }


__all__ = ["run_robustness_test"]
