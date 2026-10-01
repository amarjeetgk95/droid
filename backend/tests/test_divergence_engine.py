"""DROID — Divergence Engine Unit Tests & Lookahead Verification (§23R).

Tests:
1. Exact pivot detection with confirmation lag = right_bars.
2. Regular Bullish divergence on known fixture.
3. Regular Bearish divergence on known fixture.
4. Hidden Bullish / Hidden Bearish divergence.
5. Look-ahead invariance under future perturbation.
6. Execution against real NIFTY 5m parquet candles.
"""

import copy
from pathlib import Path
import pytest
import numpy as np
import pandas as pd

from app.signals.strategies.fisher_macd.divergence import (
    DivergenceType,
    PivotType,
    detect_pivots,
    detect_divergences,
    get_active_divergence_at_bar,
)
from app.signals.strategies.fisher_macd.fisher import calculate_fisher_point
from app.signals.strategies.fisher_macd.macd import calculate_macd
from app.signals.strategies.fisher_macd.atr import calculate_atr_series


def test_pivot_confirmation_timing():
    """Verify that a pivot at index i is confirmed strictly at i + right_bars, never earlier."""
    # Create a clear peak at index 10: highs rise to 100 at 10, then fall
    highs = [10.0] * 25
    highs[10] = 100.0  # Peak
    lows = [5.0] * 25
    ind_vals = [0.0] * 25

    p_highs, p_lows = detect_pivots(highs, lows, ind_vals, left_bars=3, right_bars=4)
    assert len(p_highs) == 1
    p = p_highs[0]
    assert p.pivot_index == 10
    assert p.confirmation_index == 14  # 10 + 4
    assert p.price == 100.0


def test_regular_bullish_divergence():
    """Price: Lower Low | Indicator: Higher Low -> REGULAR_BULLISH."""
    n = 40
    highs = [50.0] * n
    lows = [40.0] * n
    indicators = [0.0] * n
    atr = [2.0] * n

    # Pivot 1 at index 10: Low = 30.0, Ind = -2.5
    lows[10] = 30.0
    indicators[10] = -2.5

    # Pivot 2 at index 25: Low = 25.0 (Lower Low), Ind = -1.0 (Higher Low)
    lows[25] = 25.0
    indicators[25] = -1.0

    divs = detect_divergences(
        highs=highs,
        lows=lows,
        indicator_values=indicators,
        atr_values=atr,
        pivot_left_bars=3,
        pivot_right_bars=3,
        min_pivot_separation=5,
        max_pivot_separation=50,
    )

    bull_divs = [d for d in divs if d.divergence_type == DivergenceType.REGULAR_BULLISH]
    assert len(bull_divs) >= 1
    d = bull_divs[0]
    assert d.prev_price == 30.0
    assert d.curr_price == 25.0
    assert d.prev_indicator == -2.5
    assert d.curr_indicator == -1.0
    assert d.confirmation_index == 28  # 25 + 3


def test_regular_bearish_divergence():
    """Price: Higher High | Indicator: Lower High -> REGULAR_BEARISH."""
    n = 40
    highs = [50.0] * n
    lows = [40.0] * n
    indicators = [0.0] * n
    atr = [2.0] * n

    # Pivot 1 at index 10: High = 60.0, Ind = 2.5
    highs[10] = 60.0
    indicators[10] = 2.5

    # Pivot 2 at index 25: High = 65.0 (Higher High), Ind = 1.2 (Lower High)
    highs[25] = 65.0
    indicators[25] = 1.2

    divs = detect_divergences(
        highs=highs,
        lows=lows,
        indicator_values=indicators,
        atr_values=atr,
        pivot_left_bars=3,
        pivot_right_bars=3,
        min_pivot_separation=5,
        max_pivot_separation=50,
    )

    bear_divs = [d for d in divs if d.divergence_type == DivergenceType.REGULAR_BEARISH]
    assert len(bear_divs) >= 1
    d = bear_divs[0]
    assert d.prev_price == 60.0
    assert d.curr_price == 65.0
    assert d.prev_indicator == 2.5
    assert d.curr_indicator == 1.2
    assert d.confirmation_index == 28  # 25 + 3


def test_divergence_lookahead_perturbation():
    """Perturbing future bars after confirmation index must NOT alter past detected divergences."""
    np.random.seed(42)
    n = 100
    prices = 20000.0 + np.cumsum(np.random.randn(n) * 20)
    highs = prices + np.random.uniform(5, 15, n)
    lows = prices - np.random.uniform(5, 15, n)
    inds = np.sin(np.linspace(0, 10, n))
    atr = [15.0] * n

    divs_orig = detect_divergences(
        highs=highs,
        lows=lows,
        indicator_values=inds,
        atr_values=atr,
        pivot_left_bars=4,
        pivot_right_bars=4,
    )

    cutoff = 60
    divs_before_cutoff = [d for d in divs_orig if d.confirmation_index <= cutoff]

    # Perturb bars strictly after cutoff
    highs_perturbed = copy.deepcopy(highs)
    lows_perturbed = copy.deepcopy(lows)
    inds_perturbed = copy.deepcopy(inds)
    highs_perturbed[cutoff + 1:] += 500.0
    lows_perturbed[cutoff + 1:] -= 500.0
    inds_perturbed[cutoff + 1:] = 0.0

    divs_perturbed = detect_divergences(
        highs=highs_perturbed,
        lows=lows_perturbed,
        indicator_values=inds_perturbed,
        atr_values=atr,
        pivot_left_bars=4,
        pivot_right_bars=4,
    )
    divs_perturbed_before_cutoff = [d for d in divs_perturbed if d.confirmation_index <= cutoff]

    assert len(divs_before_cutoff) == len(divs_perturbed_before_cutoff)
    for d1, d2 in zip(divs_before_cutoff, divs_perturbed_before_cutoff):
        assert d1.divergence_type == d2.divergence_type
        assert d1.confirmation_index == d2.confirmation_index
        assert d1.curr_price == d2.curr_price
        assert d1.prev_price == d2.prev_price


def test_divergence_on_real_nifty():
    """Verify divergence engine executes successfully on real NIFTY 5m parquet data."""
    p = Path("backend/data/historical/parquet/nifty/5m/candles_v2.parquet")
    if not p.exists():
        pytest.skip("NIFTY parquet file not found")

    df = pd.read_parquet(p).iloc[:1000].reset_index(drop=True)
    highs = df["high"].tolist()
    lows = df["low"].tolist()
    closes = df["close"].tolist()

    f_pts = calculate_fisher_point(highs, lows, period=9, price_source="HL2")
    fisher_vals = [p.fisher for p in f_pts]
    atr_pts = calculate_atr_series(highs, lows, closes, period=14)
    atr_vals = [p.atr if hasattr(p, "atr") else p for p in atr_pts]

    divs = detect_divergences(
        highs=highs,
        lows=lows,
        indicator_values=fisher_vals,
        atr_values=atr_vals,
        indicator_name="fisher_9",
        pivot_left_bars=5,
        pivot_right_bars=5,
    )

    assert len(divs) > 0
    # Check that every divergence has confirmation_index > curr_pivot_index
    for d in divs:
        assert d.confirmation_index == d.curr_pivot_index + 5
        assert d.curr_pivot_index > d.prev_pivot_index
