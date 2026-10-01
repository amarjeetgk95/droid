"""Unit and causality tests for Order Flow & Microstructure indicators (Phase 4).

Validates:
- CVD (Cumulative Volume Delta)
- Absorption Detector
- DPFI (DROID Predictive Flow Index v1)
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from app.indicator_research.indicators.registry import IndicatorRegistry


def build_order_flow_candles(count: int = 100) -> list[dict[str, Any]]:
    """Build synthetic candles equipped with trade volume and order book depth."""
    start = datetime(2026, 1, 5, 3, 45, tzinfo=timezone.utc)  # 09:15 IST
    candles: list[dict[str, Any]] = []
    price = 100.0

    for i in range(count):
        # Generate wave with aggressor imbalance
        sin_val = math.sin(i / 8.0)
        price += sin_val * 0.4 + 0.02
        tot_vol = 1000.0 + i * 5

        # When sin_val > 0, more buying; when sin_val < 0, more selling
        buy_frac = 0.5 + 0.3 * sin_val
        buy_vol = tot_vol * buy_frac
        sell_vol = tot_vol * (1.0 - buy_frac)

        # Depth queue
        bid_p = price - 0.05
        ask_p = price + 0.05
        bid_q = 500.0 + 300.0 * sin_val
        ask_q = 500.0 - 300.0 * sin_val

        candles.append({
            "timestamp": (start + timedelta(minutes=5 * i)).isoformat(),
            "open": price - 0.1,
            "high": price + 0.5,
            "low": price - 0.5,
            "close": price,
            "volume": tot_vol,
            "buy_volume": buy_vol,
            "sell_volume": sell_vol,
            "bid_price": bid_p,
            "ask_price": ask_p,
            "bid_qty": max(50.0, bid_q),
            "ask_qty": max(50.0, ask_q),
        })

    return candles


def test_cvd_calculation():
    candles = build_order_flow_candles(60)
    indicator = IndicatorRegistry.get("cvd")
    res = indicator.compute(candles, {"anchor": "session"})

    assert "delta" in res.outputs
    assert "cvd" in res.outputs

    deltas = res.outputs["delta"]
    cvds = res.outputs["cvd"]

    assert len(deltas) == 60
    assert len(cvds) == 60

    # First bar CVD equals first bar delta
    assert math.isclose(cvds[0], deltas[0], abs_tol=1e-9)

    # CVD accumulates bar deltas
    running = 0.0
    for i in range(len(candles)):
        running += deltas[i]
        assert math.isclose(cvds[i], running, abs_tol=1e-9)


def test_absorption_detector():
    candles = build_order_flow_candles(80)
    indicator = IndicatorRegistry.get("absorption")
    res = indicator.compute(candles, {"window": 5, "aggression_threshold": 0.60, "progress_threshold_atr": 0.50})

    assert "bullish_absorption_score" in res.outputs
    assert "bearish_absorption_score" in res.outputs
    assert "absorption_detected" in res.outputs

    bull = res.outputs["bullish_absorption_score"]
    bear = res.outputs["bearish_absorption_score"]
    flag = res.outputs["absorption_detected"]

    valid_bull = [v for v in bull if v is not None]
    valid_bear = [v for v in bear if v is not None]

    assert len(valid_bull) > 50
    assert len(valid_bear) > 50
    assert all(0.0 <= v <= 100.0 for v in valid_bull)
    assert all(0.0 <= v <= 100.0 for v in valid_bear)
    assert any(f in (0.0, 1.0) for f in flag if f is not None)


def test_dpfi_calculation():
    candles = build_order_flow_candles(100)
    indicator = IndicatorRegistry.get("dpfi")
    res = indicator.compute(candles, {"depth_levels": 5, "decay": 0.85, "norm_window": 50})

    assert "dpfi" in res.outputs
    assert "ofi" in res.outputs
    assert "depth_imbalance" in res.outputs
    assert "microprice" in res.outputs
    assert "trade_imbalance" in res.outputs
    assert "pressure_acceleration" in res.outputs

    dpfi = res.outputs["dpfi"]
    valid_dpfi = [v for v in dpfi if v is not None]

    assert len(valid_dpfi) > 80
    # DPFI is bounded to [-1.0, +1.0]
    assert all(-1.0 <= v <= 1.0 for v in valid_dpfi)


@pytest.mark.parametrize("indicator_id", ["cvd", "absorption", "dpfi"])
def test_order_flow_prefix_invariance(indicator_id):
    """Causality: verify order flow indicators never peek into future bars."""
    candles = build_order_flow_candles(80)
    indicator = IndicatorRegistry.get(indicator_id)
    cut = 50

    prefix_res = indicator.compute(candles[:cut])
    full_res = indicator.compute(candles)

    for out_name in indicator.metadata.output_names():
        p_vals = prefix_res.outputs[out_name]
        f_vals = full_res.outputs[out_name][:cut]
        for idx, (p, f) in enumerate(zip(p_vals, f_vals)):
            if p is None:
                assert f is None
            else:
                assert f is not None
                assert math.isclose(p, f, abs_tol=1e-9), f"{indicator_id}.{out_name}[{idx}] diverged: {p} != {f}"


def test_order_flow_missing_data_returns_none_cleanly():
    """When trades/depth are absent (pure OHLCV), outputs must gracefully be None."""
    pure_ohlcv_candles = [
        {"timestamp": "2026-01-05T09:15:00+05:30", "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1000},
        {"timestamp": "2026-01-05T09:20:00+05:30", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 1200},
    ]
    for ind_id in ["cvd", "absorption", "dpfi"]:
        indicator = IndicatorRegistry.get(ind_id)
        res = indicator.compute(pure_ohlcv_candles)
        # All outputs should be None because depth/trade data is absent
        for name, vals in res.outputs.items():
            assert all(v is None for v in vals), f"{ind_id}.{name} should be None on pure OHLCV"
