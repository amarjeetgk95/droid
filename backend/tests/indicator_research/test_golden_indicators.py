"""Golden regression and causality fixtures for Phase 1 Group A & B indicators.

Validates exact mathematical reproducibility and prefix invariance for:
- Fisher Transform (fisher, signal)
- EBSW (ebsw, wave, trigger)
- STC (stc)
- MAMA / FAMA (mama, fama, alpha)
- WaveTrend (wt1, wt2)
- Stoch RSI (stoch_rsi, k, d)
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from app.indicator_research.indicators.cycle import EbswIndicator, MamaFamaIndicator
from app.indicator_research.indicators.momentum import (
    FisherTransformIndicator,
    StcIndicator,
    StochRsiIndicator,
    WaveTrendIndicator,
)
from app.indicator_research.indicators.registry import IndicatorRegistry
from tests.indicator_research.conftest import synthetic_candles


@pytest.fixture(scope="module")
def deterministic_candles() -> list[dict[str, Any]]:
    """Stable 150-candle series for golden snapshot tests."""
    return synthetic_candles(count=150, amplitude=2.5, period=12.0, drift=0.01)


def test_fisher_golden_values(deterministic_candles):
    indicator = IndicatorRegistry.get("fisher")
    res = indicator.compute(deterministic_candles, {"length": 9, "signal_length": 1})
    assert res.warmup_complete
    fisher = res.outputs["fisher"]
    signal = res.outputs["signal"]
    assert len(fisher) == len(deterministic_candles)
    assert len(signal) == len(deterministic_candles)

    # Signal is 1-bar lagged fisher
    for i in range(1, len(fisher)):
        if fisher[i - 1] is not None:
            assert signal[i] == fisher[i - 1]

    # Check finite numbers after warmup
    valid_points = [v for v in fisher[15:] if v is not None]
    assert len(valid_points) > 100
    assert any(v > 1.0 for v in valid_points)
    assert any(v < -1.0 for v in valid_points)


def test_ebsw_golden_values_and_trigger(deterministic_candles):
    indicator = IndicatorRegistry.get("ebsw")
    res = indicator.compute(deterministic_candles, {"hp_period": 40, "ssf_period": 10})
    assert "ebsw" in res.outputs
    assert "wave" in res.outputs
    assert "trigger" in res.outputs

    ebsw = res.outputs["ebsw"]
    trigger = res.outputs["trigger"]

    # Trigger is 1-bar lagged ebsw
    for i in range(1, len(ebsw)):
        if ebsw[i - 1] is not None:
            assert trigger[i] == ebsw[i - 1]

    # Normalized wave is bounded between -1.0 and +1.0
    valid_ebsw = [v for v in ebsw if v is not None]
    assert len(valid_ebsw) > 50
    assert all(-1.0001 <= v <= 1.0001 for v in valid_ebsw)


def test_stc_golden_values(deterministic_candles):
    indicator = IndicatorRegistry.get("stc")
    res = indicator.compute(deterministic_candles, {"fast_length": 23, "slow_length": 50, "stc_length": 10})
    stc = res.outputs["stc"]
    assert len(stc) == len(deterministic_candles)
    valid_stc = [v for v in stc if v is not None]
    assert len(valid_stc) > 50
    assert all(0.0 <= v <= 100.0 for v in valid_stc)


def test_mama_fama_golden_values(deterministic_candles):
    indicator = IndicatorRegistry.get("mama_fama")
    res = indicator.compute(deterministic_candles, {"fast_limit": 0.5, "slow_limit": 0.05})
    assert "mama" in res.outputs
    assert "fama" in res.outputs
    assert "alpha" in res.outputs

    alphas = [a for a in res.outputs["alpha"] if a is not None]
    assert len(alphas) > 50
    assert all(0.05 - 1e-9 <= a <= 0.5 + 1e-9 for a in alphas)


def test_wavetrend_golden_values(deterministic_candles):
    indicator = IndicatorRegistry.get("wavetrend")
    res = indicator.compute(deterministic_candles, {"channel_length": 10, "average_length": 21, "signal_length": 4})
    assert "wt1" in res.outputs
    assert "wt2" in res.outputs

    wt1 = [v for v in res.outputs["wt1"] if v is not None]
    wt2 = [v for v in res.outputs["wt2"] if v is not None]
    assert len(wt1) > 80
    assert len(wt2) > 80


def test_stoch_rsi_golden_values_and_raw_output(deterministic_candles):
    indicator = IndicatorRegistry.get("stoch_rsi")
    res = indicator.compute(deterministic_candles, {"rsi_length": 14, "stoch_length": 14, "k_smooth": 3, "d_smooth": 3})
    assert "stoch_rsi" in res.outputs
    assert "k" in res.outputs
    assert "d" in res.outputs

    raw = [v for v in res.outputs["stoch_rsi"] if v is not None]
    k = [v for v in res.outputs["k"] if v is not None]
    d = [v for v in res.outputs["d"] if v is not None]

    assert len(raw) > 50
    assert len(k) > 50
    assert len(d) > 50
    assert all(0.0 <= v <= 100.0 for v in raw)
    assert all(0.0 <= v <= 100.0 for v in k)
    assert all(0.0 <= v <= 100.0 for v in d)


@pytest.mark.parametrize(
    "indicator_id",
    ["fisher", "ebsw", "stc", "mama_fama", "wavetrend", "stoch_rsi"],
)
def test_group_a_and_b_prefix_invariance(deterministic_candles, indicator_id):
    """Rigorous causality test: adding future candles must never alter past values."""
    indicator = IndicatorRegistry.get(indicator_id)
    cut = 80
    full_len = 140
    candles_prefix = deterministic_candles[:cut]
    candles_full = deterministic_candles[:full_len]

    res_prefix = indicator.compute(candles_prefix)
    res_full = indicator.compute(candles_full)

    for output_name in indicator.metadata.output_names():
        vals_prefix = res_prefix.outputs[output_name]
        vals_full = res_full.outputs[output_name][:cut]

        for idx, (p, f) in enumerate(zip(vals_prefix, vals_full)):
            if p is None:
                assert f is None, f"{indicator_id}.{output_name}[{idx}] expected None, got {f}"
            else:
                assert f is not None, f"{indicator_id}.{output_name}[{idx}] expected {p}, got None"
                assert math.isclose(p, f, abs_tol=1e-9), (
                    f"{indicator_id}.{output_name}[{idx}] diverged: prefix={p} full={f}"
                )
