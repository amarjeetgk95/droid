"""Automated pytest test suite verifying Fisher-9 and MACD against Golden Fixture and A10R.

Reference: A10R, A8, Acceptance Criteria 32.
"""

import json
from pathlib import Path

import pytest
from app.signals.strategies.fisher_macd.fisher import calculate_fisher_point
from app.signals.strategies.fisher_macd.macd import calculate_macd
from app.signals.strategies.fisher_macd.atr import calculate_atr_series

FIXTURE = Path(__file__).resolve().parents[1] / "app" / "signals" / "strategies" / "fisher_macd" / "fixtures" / "fisher9_golden_fixture.json"
if not FIXTURE.exists():
    FIXTURE = Path(__file__).resolve().parents[2] / "research" / "fixtures" / "fisher9_golden_fixture.json"


def _load_fixture():
    assert FIXTURE.exists(), "Golden fixture file must exist"
    with open(FIXTURE, "r") as f:
        return json.load(f)


def test_fisher9_matches_golden_fixture():
    data = _load_fixture()
    meta = data["metadata"]
    bars = data["bars"]

    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    closes = [b["close"] for b in bars]

    points = calculate_fisher_point(
        highs=highs,
        lows=lows,
        period=meta["period"],
        price_source=meta["source"],
        closes=closes,
    )

    assert len(points) == len(bars)
    assert len(points) == meta["bar_count"]

    for point, bar in zip(points, bars):
        assert point.bar_index == bar["bar_index"]
        expected_raw = bar["raw"]
        expected_fisher = bar["fisher"]
        expected_trigger = bar["trigger"]

        if expected_raw is None:
            # Bars before `period` must emit None, never a seeded zero.
            assert point.raw is None
            assert point.fisher is None
            assert point.trigger is None
        else:
            assert point.raw == pytest.approx(expected_raw, abs=1e-9)
            assert point.fisher == pytest.approx(expected_fisher, abs=1e-9)
            assert point.trigger == pytest.approx(expected_trigger, abs=1e-9)


def test_macd_seeds_from_sma_not_zero():
    """A10R: MACD must seed its EMAs from an SMA, not start at zero."""
    prices = [100.0 + i for i in range(40)]
    series = calculate_macd(prices, fast=12, slow=26, signal=9)

    assert len(series) == len(prices)

    # MACD line is valid from slow-1 onwards; before that it is the warmup window.
    assert series[24].macd is None
    assert series[25].macd is not None

    # On a unit-slope ramp, fast EMA(12) lags price by (12-1)/2 = 5.5 and the
    # freshly seeded slow EMA sits at its SMA, so MACD(25) must be ~+7.0 -
    # proof the EMAs were honestly seeded rather than started at zero.
    assert series[25].macd == pytest.approx(7.0, abs=0.05)

    # Signal line seeds from the SMA of the first 9 valid MACD values,
    # so it appears at bar 25+9-1 = 33.
    assert series[32].signal is None
    assert series[33].signal is not None


def _atr_value(point):
    """Unwrap one ATR series entry.

    The implementation intermittently returns ``ATRPoint`` objects versus bare
    floats across revisions; the test pins the numeric contract, not the shape.
    """
    return point.atr if hasattr(point, "atr") else point


def test_atr_seeds_with_wilder_smoothing():
    """A10R: ATR must seed with a simple mean over the first `period` bars."""
    highs = [101.0 + i for i in range(30)]
    lows = [99.0 + i for i in range(30)]
    closes = [100.0 + i for i in range(30)]

    series = calculate_atr_series(highs, lows, closes, period=14)

    assert len(series) == 30
    # Warmup window emits None.
    assert _atr_value(series[12]) is None

    # Every bar here has a true range of 2.0, so Wilder ATR must seed at 2.0
    # and stay there exactly.
    assert _atr_value(series[13]) == pytest.approx(2.0, abs=1e-6)
    assert _atr_value(series[-1]) == pytest.approx(2.0, abs=1e-6)
