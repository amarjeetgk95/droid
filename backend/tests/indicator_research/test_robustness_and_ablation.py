import pytest

from app.indicator_research.backtesting.models import BacktestSettings
from app.indicator_research.research.ablation import run_ablation_study
from app.indicator_research.research.features import IndicatorSpec
from app.indicator_research.research.robustness import run_robustness_test


def test_robustness_perturbation_and_cost_stress(candles):
    specs = [IndicatorSpec("fisher", {"length": 9, "signal_length": 1}, "primary")]
    long_rule = {
        "operator": "AND",
        "conditions": [{"left": "fisher", "operator": "crosses_above", "right": -1.5}],
    }
    short_rule = {
        "operator": "AND",
        "conditions": [{"left": "fisher", "operator": "crosses_below", "right": 1.5}],
    }

    result = run_robustness_test(
        candles=candles,
        specs=specs,
        long_rule=long_rule,
        short_rule=short_rule,
        settings=BacktestSettings(),
        perturbation_pcts=[-0.20, -0.10, 0.10, 0.20],
        cost_multipliers=[1.0, 1.5, 2.0],
        instrument="NIFTY",
        timeframe="5m",
    )

    assert result["ok"] is True
    assert "verdict" in result
    assert result["verdict"] in ("ROBUST", "MODERATELY_FRAGILE", "HIGHLY_FRAGILE")
    assert "stability_score_pct" in result
    assert "cost_stress_results" in result
    assert len(result["cost_stress_results"]) == 3
    # First cost stress multiplier is 1.0
    assert result["cost_stress_results"][0]["multiplier"] == 1.0


def test_ablation_multi_indicator_contribution(candles):
    specs = [
        IndicatorSpec("fisher", {"length": 9, "signal_length": 1}, "primary"),
        IndicatorSpec("ebsw", {"hp_period": 48, "ssf_period": 10}, "overlay"),
    ]
    long_rule = {
        "operator": "AND",
        "conditions": [
            {"left": "fisher", "operator": "crosses_above", "right": -1.5},
            {"left": "ebsw", "operator": "turns_up"},
        ],
    }
    short_rule = {
        "operator": "AND",
        "conditions": [
            {"left": "fisher", "operator": "crosses_below", "right": 1.5},
            {"left": "ebsw", "operator": "turns_down"},
        ],
    }

    result = run_ablation_study(
        candles=candles,
        specs=specs,
        long_rule=long_rule,
        short_rule=short_rule,
        settings=BacktestSettings(),
        instrument="NIFTY",
        timeframe="5m",
    )

    assert result["ok"] is True
    assert "full_model" in result
    assert "ablations" in result
    assert len(result["ablations"]) == 2

    # Check each excluded indicator output
    excluded_ids = {a["excluded_indicator"] for a in result["ablations"]}
    assert excluded_ids == {"fisher", "ebsw"}
    for a in result["ablations"]:
        assert "delta_sharpe" in a
        assert "verdict" in a
        assert a["verdict"] in (
            "CRITICAL_VALUE_ADD",
            "MODERATE_VALUE_ADD",
            "REDUNDANT",
            "HARMFUL_OVERFIT",
            "ERROR",
        )
