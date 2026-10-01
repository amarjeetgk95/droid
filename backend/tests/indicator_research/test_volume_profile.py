"""Tests for Anchored VWAP and Causal Volume Profile (Phase 2)."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from app.indicator_research.indicators.registry import IndicatorRegistry
from app.indicator_research.indicators.trend import VwapIndicator, VolumeProfileIndicator
from tests.indicator_research.conftest import synthetic_candles


def build_multiday_candles() -> list[dict[str, Any]]:
    """Generate 2 days of 5m candles (75 bars per day, 150 total) in IST."""
    candles: list[dict[str, Any]] = []
    # Day 1: 2026-01-05
    start_d1 = datetime(2026, 1, 5, 3, 45, tzinfo=timezone.utc)  # 09:15 IST
    price = 100.0
    for i in range(75):
        price += math.sin(i / 5.0) * 0.5 + 0.05
        candles.append({
            "timestamp": (start_d1 + timedelta(minutes=5 * i)).isoformat(),
            "open": price - 0.2,
            "high": price + 0.8,
            "low": price - 0.8,
            "close": price,
            "volume": 1000.0 + i * 10,
        })

    # Day 2: 2026-01-06 (new session)
    start_d2 = datetime(2026, 1, 6, 3, 45, tzinfo=timezone.utc)  # 09:15 IST
    price = 110.0
    for i in range(75):
        price += math.cos(i / 5.0) * 0.5 - 0.05
        candles.append({
            "timestamp": (start_d2 + timedelta(minutes=5 * i)).isoformat(),
            "open": price - 0.2,
            "high": price + 0.8,
            "low": price - 0.8,
            "close": price,
            "volume": 2000.0 + i * 10,
        })
    return candles


def test_anchored_vwap_session_reset():
    candles = build_multiday_candles()
    indicator = IndicatorRegistry.get("vwap")
    res = indicator.compute(candles, {"anchor": "session", "window": 0})

    assert "vwap" in res.outputs
    assert "distance_from_vwap" in res.outputs
    assert "vwap_slope" in res.outputs

    vwap = res.outputs["vwap"]
    dist = res.outputs["distance_from_vwap"]
    slope = res.outputs["vwap_slope"]

    assert len(vwap) == len(candles)
    # Day 1 end vs Day 2 start: VWAP must reset on Day 2 bar 0 (index 75)
    bar75 = candles[75]
    tp_75 = (bar75["high"] + bar75["low"] + bar75["close"]) / 3.0
    # On first bar of session, VWAP equals typical price of that bar
    assert math.isclose(vwap[75], tp_75, rel_tol=1e-5)

    # Check distance and slope are calculated
    for i in range(len(candles)):
        if vwap[i] is not None and candles[i]["close"] is not None:
            assert math.isclose(dist[i], candles[i]["close"] - vwap[i], abs_tol=1e-9)


def test_volume_profile_poc_and_value_area():
    candles = build_multiday_candles()
    indicator = IndicatorRegistry.get("volume_profile")
    res = indicator.compute(candles, {"anchor": "session", "value_area_pct": 0.70, "bin_size": 0.5})

    assert "poc" in res.outputs
    assert "vah" in res.outputs
    assert "val" in res.outputs
    assert "hvn" in res.outputs
    assert "lvn" in res.outputs

    poc = res.outputs["poc"]
    vah = res.outputs["vah"]
    val = res.outputs["val"]

    # In Day 1 (after a few bars), check VAH >= POC >= VAL
    for i in range(10, 75):
        if poc[i] is not None:
            assert vah[i] >= poc[i], f"Bar {i}: VAH ({vah[i]}) must be >= POC ({poc[i]})"
            assert val[i] <= poc[i], f"Bar {i}: VAL ({val[i]}) must be <= POC ({poc[i]})"

    # Day 2 should reset and anchor around Day 2 prices (~110)
    for i in range(85, 150):
        if poc[i] is not None:
            assert vah[i] >= poc[i] >= val[i]
            assert 105.0 <= poc[i] <= 115.0


def test_volume_profile_prefix_invariance():
    """Volume Profile must strictly satisfy causality and prefix-invariance."""
    candles = build_multiday_candles()
    indicator = IndicatorRegistry.get("volume_profile")
    cut = 60
    prefix_candles = candles[:cut]

    res_prefix = indicator.compute(prefix_candles, {"anchor": "session", "value_area_pct": 0.70, "bin_size": 0.5})
    res_full = indicator.compute(candles, {"anchor": "session", "value_area_pct": 0.70, "bin_size": 0.5})

    for out_name in ("poc", "vah", "val"):
        p_vals = res_prefix.outputs[out_name]
        f_vals = res_full.outputs[out_name][:cut]
        for idx, (p, f) in enumerate(zip(p_vals, f_vals)):
            if p is None:
                assert f is None
            else:
                assert f is not None
                assert math.isclose(p, f, abs_tol=1e-9), f"{out_name}[{idx}] diverged: {p} != {f}"
