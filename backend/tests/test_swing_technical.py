"""
Unit tests for Swing Module Technical Feature Engine (v5.0 §7).
"""
import pytest
from app.swing.technical import (
    compute_ema,
    compute_sma,
    compute_atr,
    extract_swing_features,
)


def test_sma_and_ema_calculation():
    series = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0]
    sma5 = compute_sma(series, 5)
    # The 5th element (index 4) should be average of first 5: (10+11+12+13+14)/5 = 12.0
    assert sma5[4] == 12.0
    # Last element should be average of (15+16+17+18+19)/5 = 17.0
    assert sma5[-1] == 17.0

    ema5 = compute_ema(series, 5)
    assert not pytest.approx(ema5[-1]) == 0.0
    assert ema5[4] == 12.0
    assert ema5[-1] > 16.0


def test_atr_calculation():
    candles = [
        {"open": 100, "high": 105, "low": 95, "close": 100, "volume": 1000},
        {"open": 100, "high": 110, "low": 98, "close": 108, "volume": 1200},
        {"open": 108, "high": 112, "low": 104, "close": 105, "volume": 900},
        {"open": 105, "high": 107, "low": 101, "close": 103, "volume": 800},
    ]
    atr = compute_atr(candles, period=2)
    assert len(atr) == len(candles)
    assert atr[-1] > 0


def test_extract_swing_features():
    # Build 60 candles in a rising trend with tightening range
    candles = []
    base_price = 2000.0
    for i in range(60):
        c = base_price + i * 5.0
        # Contracting range: 30 for earlier, 18 for last 20, 6 for last 5
        if i < 40:
            spread = 30.0
        elif i < 55:
            spread = 20.0
        else:
            spread = 6.0
        candles.append({
            "timestamp": 1700000000 + i * 86400,
            "open": c - 2.0,
            "high": c + spread,
            "low": c - spread,
            "close": c,
            "volume": 100000 if i < 55 else 40000, # volume dry up
        })

    features = extract_swing_features(candles)
    assert features.close > 0
    assert features.price_above_ema20 is True
    assert features.price_above_sma50 is True
    assert features.range_contraction_ratio < 0.85
    assert features.atr_14 > 0
    assert features.recent_swing_high > 0
