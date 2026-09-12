"""P1-3/4/5: power + calibration metrics + reference costs. Hermetic, no network."""

import math

from app.ml.calibration_metrics import (
    brier_score_3class,
    calibration_report,
    calibration_slope_intercept,
    ece_equal_width,
    log_loss_3class,
    reliability_table,
)
from app.research.validation.costs import (
    COSTS_VERSION,
    REFERENCE_COSTS_V1,
    apply_costs,
    scale_costs,
)
from app.research.validation.power import (
    ALPHA,
    BASELINE_RATE,
    MDE_ABSOLUTE,
    POWER,
    cell_status,
    required_n,
)


# ---------------------------------------------------------------------------
# P1-3 power
# ---------------------------------------------------------------------------

def test_power_defaults_preregistered():
    assert BASELINE_RATE == 0.38
    assert MDE_ABSOLUTE == 0.05
    assert ALPHA == 0.05
    assert POWER == 0.8


def test_power_known_value_baseline038_mde005():
    # One-sample two-sided proportion z-test:
    # n = [z_a*sqrt(p0(1-p0)) + z_b*sqrt(p1(1-p1))]^2 / mde^2, ceil.
    # p0=0.38, p1=0.43, z_a=1.95996, z_b=0.84162 -> 748.58 -> 749.
    assert required_n(0.38, 0.05, 0.05, 0.8) == 749


def test_power_monotonicity():
    base = required_n(0.38, 0.05)
    assert required_n(0.38, 0.10) < base  # larger MDE -> smaller n
    assert required_n(0.38, 0.025) > base  # smaller MDE -> larger n
    assert required_n(0.50, 0.05) > required_n(0.38, 0.05)  # max variance at 0.5
    assert required_n(0.38, 0.05, power=0.9) > base  # more power -> larger n
    assert required_n(0.38, 0.05, alpha=0.01) > base  # stricter alpha -> larger n


def test_cell_statuses():
    req = required_n(0.38, 0.05)
    assert cell_status(req, req) == "SUFFICIENT"
    assert cell_status(req + 100, req) == "SUFFICIENT"
    assert cell_status(req - 1, req) == "INSUFFICIENT"
    assert cell_status(0, req) == "INSUFFICIENT"
    # contradictory takes precedence even with sufficient n
    assert cell_status(10_000, req, True) == "CONTRADICTORY"
    assert cell_status(0, req, True) == "CONTRADICTORY"


# ---------------------------------------------------------------------------
# P1-4 calibration metrics
# ---------------------------------------------------------------------------

def test_brier_perfect_vs_uniform():
    y = [2, 0, 1, 2]
    perfect = [[0, 0, 1], [1, 0, 0], [0, 1, 0], [0, 0, 1]]
    uniform = [[1 / 3, 1 / 3, 1 / 3]] * 4
    assert brier_score_3class(y, perfect) == 0.0
    assert abs(brier_score_3class(y, uniform) - 2 / 3) < 1e-9
    assert brier_score_3class(y, perfect) < brier_score_3class(y, uniform)


def test_logloss_perfect_vs_uniform():
    y = [2, 0, 1]
    perfect = [[0, 0, 1], [1, 0, 0], [0, 1, 0]]
    uniform = [[1 / 3, 1 / 3, 1 / 3]] * 3
    assert log_loss_3class(y, perfect) < 1e-9
    assert abs(log_loss_3class(y, uniform) - math.log(3)) < 1e-9
    # eps clip keeps confident-wrong finite
    wrong = [[1, 0, 0], [0, 0, 1], [1, 0, 0]]
    assert math.isfinite(log_loss_3class(y, wrong))


def test_ece_perfect_zero_and_miscalibrated_positive():
    # perfect: confidence matches accuracy in every occupied bin
    y = [1, 1, 1, 1]
    pmax = [1.0, 1.0, 1.0, 1.0]
    out = ece_equal_width(y, pmax, 10)
    assert out["ece"] == 0.0
    assert out["n"] == 4 and len(out["bins"]) == 10
    # wildly overconfident: all wrong at 0.9 confidence -> ECE ~ 0.9
    out2 = ece_equal_width([0, 0, 0, 0], [0.9, 0.9, 0.9, 0.9], 10)
    assert out2["ece"] > 0.8
    # reliability table mirrors bins
    assert reliability_table([0, 0], [0.9, 0.9], 10) == ece_equal_width([0, 0], [0.9, 0.9], 10)["bins"]


def test_ece_multiclass_needs_ypred():
    import pytest as _pytest
    with _pytest.raises(ValueError):
        ece_equal_width([0, 1, 2], [0.5, 0.6, 0.7], 10)
    ok = ece_equal_width([0, 1, 2], [0.9, 0.9, 0.9], 10, y_pred_idx=[0, 1, 0])
    assert 0.0 <= ok["ece"] <= 1.0


def test_calibration_report_and_slope_direction():
    y = [2, 2, 0, 0, 1, 1]
    P = [[0.1, 0.1, 0.8], [0.2, 0.1, 0.7], [0.7, 0.2, 0.1],
         [0.6, 0.3, 0.1], [0.1, 0.8, 0.1], [0.2, 0.7, 0.1]]
    rep = calibration_report(y, P, 5)
    assert rep["n"] == 6
    assert 0.0 <= rep["brier"] < 0.6667  # better than uniform
    assert 0.0 <= rep["ece"] <= 1.0
    assert len(rep["bins"]) == 5
    assert set(rep["slopes_ovr"]) == {0, 1, 2}
    # binary slope: sensible confidence ordering -> positive slope
    fit = calibration_slope_intercept([1, 1, 1, 0, 0, 0], [0.9, 0.8, 0.7, 0.3, 0.2, 0.1])
    assert fit["slope"] > 0
    assert fit["n"] == 6 and "method" in fit


# ---------------------------------------------------------------------------
# P1-5 costs
# ---------------------------------------------------------------------------

def test_reference_costs_versioned():
    assert COSTS_VERSION == "ref-v1"
    assert REFERENCE_COSTS_V1["spread_bps"] == 2.0
    assert REFERENCE_COSTS_V1["slippage_bps"] == 1.0
    assert REFERENCE_COSTS_V1["statutory_pct"] == 0.001
    assert REFERENCE_COSTS_V1["brokerage_flat"] == 0


def test_costs_net_below_gross_and_2x_worse():
    gross = [0.01, 0.005, -0.002, 0.02]
    turnover = [1.0, 1.0, 1.0, 1.0]
    net_base = apply_costs(gross, turnover)
    net_2x = apply_costs(gross, turnover, scale_costs(REFERENCE_COSTS_V1, 2.0))
    assert len(net_base) == 4
    assert all(n < g for n, g in zip(net_base, gross))  # positive drag every trade
    assert sum(net_2x) < sum(net_base)  # 2x strictly worse
    # abstain (turnover 0) pays nothing
    assert apply_costs([0.01], [0.0]) == [0.01]
    # scale helper does not mutate base
    before = dict(REFERENCE_COSTS_V1)
    scaled = scale_costs(REFERENCE_COSTS_V1, 1.5)
    assert REFERENCE_COSTS_V1 == before
    assert scaled["spread_bps"] == before["spread_bps"] * 1.5
