import pytest

from app.indicator_research.backtesting.models import BacktestSettings
from app.indicator_research.research.features import IndicatorSpec
from app.indicator_research.research.optimizer import (
    expected_max_null_sharpe,
    multiple_testing_penalty,
    optimize,
    parameter_space,
    random_combinations,
)


def test_random_combinations_sampling():
    space = parameter_space("fisher")
    combos = random_combinations(space, n_samples=3, seed=123)
    assert len(combos) <= 3
    # Deterministic with same seed
    combos2 = random_combinations(space, n_samples=3, seed=123)
    assert combos == combos2


def test_expected_max_null_sharpe_math():
    assert expected_max_null_sharpe(1) == 0.0
    # Expected null max increases monotonically with trials
    s10 = expected_max_null_sharpe(10)
    s100 = expected_max_null_sharpe(100)
    s1000 = expected_max_null_sharpe(1000)
    assert 0.0 < s10 < s100 < s1000


def test_multiple_testing_penalty_accounting():
    penalty = multiple_testing_penalty(best_sharpe=2.0, trials_evaluated=100)
    assert penalty["trials_evaluated"] == 100
    assert penalty["haircut_pct"] > 0.0
    assert penalty["adjusted_sharpe"] < 2.0
    assert penalty["overfitting_risk"] == "HIGH"


def test_optimizer_random_search_execution(candles):
    specs = [IndicatorSpec("fisher", {"length": 9, "signal_length": 1}, "primary")]
    long_rule = {
        "operator": "AND",
        "conditions": [{"left": "fisher", "operator": "crosses_above", "right": -1.5}],
    }
    short_rule = {
        "operator": "AND",
        "conditions": [{"left": "fisher", "operator": "crosses_below", "right": 1.5}],
    }

    result = optimize(
        candles=candles,
        specs=specs,
        long_rule=long_rule,
        short_rule=short_rule,
        settings=BacktestSettings(),
        search_mode="random",
        seed=42,
        max_combinations=5,
        min_trades=1,
    )

    assert result["search_mode"] == "random"
    assert result["combinations_evaluated"] <= 5
    assert "multiple_testing_penalty" in result
    assert result["multiple_testing_penalty"]["trials_evaluated"] == result["combinations_evaluated"]
