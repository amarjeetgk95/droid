"""Promotion gate: re-enabling a strategy requires Gate-G2 PASSED."""

from app.quant.validation.promotion_gate import (
    evaluate_strategy_promotion,
    is_strategy_promotable,
)


def _good_metrics(**over):
    m = {
        "strategy_key": "ORB",
        "total_trades": 120,
        "net_expectancy_pct": 0.0015,
        "profit_factor": 1.35,
        "max_drawdown_pct": 0.08,
        "deflated_sharpe_ratio": 0.62,
        "cost_survival_max_multiplier": 2.0,
        "sensitivity_pass_count": 3,
    }
    m.update(over)
    return m


def test_passed_when_robust():
    d = evaluate_strategy_promotion("ORB", _good_metrics())
    assert d.verdict == "PASSED"
    assert is_strategy_promotable(_good_metrics()) is True


def test_failed_on_low_dsr():
    d = evaluate_strategy_promotion("ORB", _good_metrics(deflated_sharpe_ratio=0.10))
    assert d.verdict == "FAILED"
    assert any("Deflated Sharpe" in r for r in d.reasons)
    assert is_strategy_promotable(_good_metrics(deflated_sharpe_ratio=0.10)) is False


def test_inconclusive_when_underpowered():
    d = evaluate_strategy_promotion("ORB", _good_metrics(total_trades=12))
    assert d.verdict == "INCONCLUSIVE"
    assert is_strategy_promotable(_good_metrics(total_trades=12)) is False


def test_failed_fail_closed_on_missing():
    d = evaluate_strategy_promotion("ORB", {"strategy_key": "ORB"})
    assert d.verdict == "FAILED"


def test_freeze_keepers_are_enabled_and_rest_disabled():
    from app.signals.strategies import STRATEGY_ENABLED

    assert STRATEGY_ENABLED["ORB"] is True
    assert STRATEGY_ENABLED["VOLATILITY_BREAKOUT"] is True
    assert STRATEGY_ENABLED["VWAP_SCALP"] is True
    for name in (
        "REGIME_ADAPTIVE_TREND",
        "TREND_PULLBACK",
        "MEAN_REVERSION",
        "GAMMA_SQUEEZE",
        "LIQUIDITY_SWEEP_RECLAIM",
        "MICRO_MOMENTUM",
        "MOMENTUM_REACCELERATION",
        "GAMMA_SPIKE",
    ):
        assert STRATEGY_ENABLED.get(name) is False, name
