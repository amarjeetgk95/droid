"""Unit tests for the Research Feature Layer (§12)."""

import pytest
from datetime import datetime, timezone, timedelta

from app.research.enums import MarketSession
from app.research.features import FeatureLayer, classify_session_ist


def test_session_classification_ist():
    """Verify market session classification for Indian market hours (IST = UTC + 5:30)."""
    # 09:20 IST = 03:50 UTC (OPENING)
    dt_open = datetime(2026, 9, 7, 3, 50, tzinfo=timezone.utc)
    assert classify_session_ist(dt_open) == MarketSession.OPENING

    # 10:30 IST = 05:00 UTC (EARLY)
    dt_early = datetime(2026, 9, 7, 5, 0, tzinfo=timezone.utc)
    assert classify_session_ist(dt_early) == MarketSession.EARLY

    # 12:30 IST = 07:00 UTC (MID)
    dt_mid = datetime(2026, 9, 7, 7, 0, tzinfo=timezone.utc)
    assert classify_session_ist(dt_mid) == MarketSession.MID

    # 14:15 IST = 08:45 UTC (LATE)
    dt_late = datetime(2026, 9, 7, 8, 45, tzinfo=timezone.utc)
    assert classify_session_ist(dt_late) == MarketSession.LATE

    # 15:15 IST = 09:45 UTC (CLOSING)
    dt_closing = datetime(2026, 9, 7, 9, 45, tzinfo=timezone.utc)
    assert classify_session_ist(dt_closing) == MarketSession.CLOSING

    # 18:00 IST = 12:30 UTC (CLOSED)
    dt_closed = datetime(2026, 9, 7, 12, 30, tzinfo=timezone.utc)
    assert classify_session_ist(dt_closed) == MarketSession.CLOSED


def test_feature_layer_computation():
    """Test comprehensive feature computation."""
    now = datetime(2026, 9, 7, 6, 0, tzinfo=timezone.utc)
    candles = []
    for i in range(40):
        candles.append({
            "open": 24000.0 + i,
            "high": 24005.0 + i,
            "low": 23995.0 + i,
            "close": 24002.0 + i,
            "volume": 2000.0,
            "timestamp": (now + timedelta(minutes=5 * i)).isoformat(),
        })

    opts = {
        "available": True,
        "pcr_oi": 1.15,
        "atm_iv": 14.8,
        "call_wall": 24500.0,
        "put_wall": 23500.0,
    }

    features = FeatureLayer.compute_features(
        instrument="NIFTY 50",
        timeframe="5m",
        candles=candles,
        options_ctx=opts,
    )

    assert "quant" in features
    assert "momentum_dynamics" in features
    assert "volume_dynamics" in features
    assert "regime" in features
    assert "options" in features

    quant = features["quant"]
    assert "rsi_14" in quant
    assert "atr_14" in quant
    assert "adx" in quant
    assert "vwap" in quant
    assert "supertrend_dir" in quant
