"""Unit Tests for Temporal Leakage and Point-in-Time Correctness.

Tests that any future data (candles, VIX, options) instantly triggers
TemporalLeakageError and fails closed.
"""
import pytest
from datetime import datetime, timezone

from app.ml.features.feature_extractor_v3 import extract_features_v3, TemporalLeakageError
from app.ml.features.schema import FEATURE_NAMES_V3
from app.ml.validation.leakage_checks import assert_no_lookahead_in_matrix


def test_feature_extractor_v3_valid_pit():
    t = 1700000000000  # Evaluation timestamp
    candles = [
        {"timestamp_ms": t - 120000, "open": 24900, "high": 24920, "low": 24890, "close": 24910, "volume": 1000},
        {"timestamp_ms": t - 60000, "open": 24910, "high": 24940, "low": 24905, "close": 24930, "volume": 1200},
        {"timestamp_ms": t, "open": 24930, "high": 24950, "low": 24925, "close": 24945, "volume": 1500},
    ]
    vix = {"timestamp_ms": t, "ltp": 14.5}
    opts = {"timestamp_ms": t, "pcr": 1.15, "atm_iv": 13.8}

    vec = extract_features_v3(
        instrument="NIFTY",
        feature_timestamp_ms=t,
        candles_1m=candles,
        indicators={"vwap": 24920, "ema20": 24910, "ema50": 24880, "ema200": 24800, "supertrend_direction": "BULLISH"},
        options_analytics=opts,
        vix_quote=vix,
    )
    assert len(vec.features) == len(FEATURE_NAMES_V3)
    assert vec.feature_timestamp == t
    assert vec.validate_pit() is True
    assert vec.feature_dict["ret_1m"] > 0


def test_feature_extractor_v3_rejects_future_candle():
    t = 1700000000000
    future_candles = [
        {"timestamp_ms": t - 60000, "open": 24900, "high": 24920, "low": 24890, "close": 24910, "volume": 1000},
        {"timestamp_ms": t, "open": 24910, "high": 24930, "low": 24900, "close": 24925, "volume": 1200},
        {"timestamp_ms": t + 60000, "open": 24925, "high": 24960, "low": 24920, "close": 24955, "volume": 1400},  # LEAKAGE!
    ]
    with pytest.raises(TemporalLeakageError, match="Leakage detected: candle timestamp"):
        extract_features_v3(
            instrument="NIFTY",
            feature_timestamp_ms=t,
            candles_1m=future_candles,
        )


def test_feature_extractor_v3_rejects_future_vix():
    t = 1700000000000
    candles = [
        {"timestamp_ms": t, "open": 24910, "high": 24930, "low": 24900, "close": 24925, "volume": 1200},
    ]
    future_vix = {"timestamp_ms": t + 5000, "ltp": 16.0}  # LEAKAGE!
    with pytest.raises(TemporalLeakageError, match="Leakage detected: VIX timestamp"):
        extract_features_v3(
            instrument="NIFTY",
            feature_timestamp_ms=t,
            candles_1m=candles,
            vix_quote=future_vix,
        )


def test_assert_no_lookahead_in_matrix():
    valid_ts = [1000, 2000, 3000, 3000, 4000]
    assert assert_no_lookahead_in_matrix(valid_ts) is True

    shuffled_ts = [1000, 3000, 2000, 4000]
    with pytest.raises(TemporalLeakageError, match="Non-chronological ordering detected"):
        assert_no_lookahead_in_matrix(shuffled_ts)
