"""P3-3 cache + SLO + idempotency tests (pure + integration, hermetic).

Covers app.research.cache.TTLCache (TTL via monotonic, max 200 keys,
pure) and TrendForecaster additive integration:
- FORECAST_CACHE=on/off default on
- MTF/ML instance caches hit within TTL
- forecast() records latency_ms + cache_hit + idempotent_replay
- minute-bucket idempotency replays same prediction_id (record=True)
"""

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.research.cache import (
    ML_CACHE,
    MTF_CACHE,
    OPTIONS_CACHE,
    TTLCache,
    cache_enabled,
    clear_all,
    make_ml_key,
    make_mtf_key,
    make_options_key,
)
from app.research.options_context import ResearchOptionsContext
from app.research.predictions import PredictionService, SnapshotService
from app.research import trend_forecast as tf_mod
from app.research.trend_forecast import TrendForecast1H, clear_forecast_idempotency

BASE_TS = datetime(2026, 9, 9, 4, 30, tzinfo=timezone.utc)


def _make_candles(count, step_minutes, start_price=25000.0, drift=1.5, end_ts=BASE_TS):
    start = end_ts - timedelta(minutes=step_minutes * (count - 1))
    out = []
    for i in range(count):
        price = start_price + i * drift
        out.append({
            "open": price - 0.8,
            "high": price + 1.2,
            "low": price - 1.2,
            "close": price,
            "volume": 1000.0 + i * 5.0,
            "timestamp": (start + timedelta(minutes=step_minutes * i)).isoformat(),
        })
    return out


def _full_market():
    return {
        "1m": _make_candles(200, 1),
        "5m": _make_candles(100, 5),
        "15m": _make_candles(60, 15),
        "30m": _make_candles(40, 30),
        "1h": _make_candles(60, 60),
        "4h": _make_candles(20, 240),
        "1D": _make_candles(10, 1440),
    }


def _heuristic_ml():
    return {
        "bullish_pct": 55.0, "neutral_pct": 20.0, "bearish_pct": 25.0,
        "predicted_bias": "BULLISH", "trend_strength": 62.0,
        "confidence_score": 70.0, "model_source": "heuristic_ensemble",
        "calibrated": False,
        "model_version": "XGBoost-LightGBM-Ensemble-v1.0-heuristic",
        "horizon_minutes": 60, "target_spec_version": "v1-atr-band",
    }


def _healthy_options():
    return {
        "instrument": "NIFTY 50", "available": True, "data_quality": "LIVE",
        "pcr_oi": 1.0, "pcr_vol": 1.0, "atm_iv": 15.0,
        "call_wall": None, "put_wall": None, "max_pain": None,
        "days_to_expiry": 1.0, "atm_theta": -10.0,
        "atm_gamma": 0.001, "atm_vega": 10.0,
    }


def _settle_ok():
    return {"universe": "nse", "settleable": True, "reason": "same-regular-session",
            "t_plus_h_utc": BASE_TS + timedelta(minutes=60), "session_close_utc": None}


# --- pure TTLCache ---

def test_ttl_expiry_via_monotonic():
    now = [1000.0]
    c = TTLCache(30.0, max_keys=200, now_fn=lambda: now[0])
    c.set("k", "v")
    assert c.get("k") == "v"
    now[0] += 30.01
    assert c.get("k") is None


def test_max_200_keys_fifo():
    now = [0.0]
    c = TTLCache(60.0, max_keys=200, now_fn=lambda: now[0])
    for i in range(205):
        c.set(f"k{i}", i)
    assert len(c) == 200
    assert c.get("k0") is None
    assert c.get("k204") == 204


def test_cache_enabled_default_on(monkeypatch):
    monkeypatch.delenv("FORECAST_CACHE", raising=False)
    assert cache_enabled() is True
    for off in ("off", "false", "0", "no", "OFF"):
        monkeypatch.setenv("FORECAST_CACHE", off)
        assert cache_enabled() is False
    monkeypatch.setenv("FORECAST_CACHE", "on")
    assert cache_enabled() is True


def test_key_helpers():
    assert make_mtf_key("NIFTY 50", ["1h", "1m"])[0] == "mtf"
    assert make_options_key("NIFTY 50")[0] == "options"
    assert make_ml_key("NIFTY 50", 60)[0] == "ml"
    assert make_ml_key("NIFTY 50", 60) != make_ml_key("NIFTY 50", 15)


def test_module_caches_have_p33_ttls():
    assert MTF_CACHE.ttl_seconds == 30.0
    assert OPTIONS_CACHE.ttl_seconds == 60.0
    assert ML_CACHE.ttl_seconds == 15.0
    clear_all()


# --- integration: MTF + ML instance caches ---

@pytest.mark.asyncio
async def test_mtf_cache_hit_avoids_second_fetch(monkeypatch):
    monkeypatch.setenv("FORECAST_CACHE", "on")
    market = MagicMock()
    market.get_candles = AsyncMock(side_effect=lambda symbol, timeframe=None, **kw: list(_full_market().get(timeframe, [])))
    fc = TrendForecast1H(market_service=market, ml_predictor=MagicMock())
    r1 = await fc.fetch_multi_timeframe_candles("NIFTY 50")
    assert r1.get("1h")
    calls_after_first = market.get_candles.await_count
    assert calls_after_first == 7
    r2 = await fc.fetch_multi_timeframe_candles("NIFTY 50")
    assert r2.get("1h")
    # Second call served from 30s TTL cache: no new backend calls.
    assert market.get_candles.await_count == calls_after_first
    assert getattr(fc, "_last_mtf_cache_hit", False) is True


@pytest.mark.asyncio
async def test_cache_off_disables_mtf_cache(monkeypatch):
    monkeypatch.setenv("FORECAST_CACHE", "off")
    market = MagicMock()
    market.get_candles = AsyncMock(side_effect=lambda symbol, timeframe=None, **kw: list(_full_market().get(timeframe, [])))
    fc = TrendForecast1H(market_service=market, ml_predictor=MagicMock())
    await fc.fetch_multi_timeframe_candles("NIFTY 50")
    await fc.fetch_multi_timeframe_candles("NIFTY 50")
    assert market.get_candles.await_count == 14


@pytest.mark.asyncio
async def test_ml_cache_hit(monkeypatch):
    monkeypatch.setenv("FORECAST_CACHE", "on")
    mp = MagicMock()
    resp = MagicMock()
    resp.bullish_pct = 55.0; resp.neutral_pct = 20.0; resp.bearish_pct = 25.0
    resp.predicted_bias = "BULLISH"; resp.trend_strength = 62.0
    resp.confidence_score = 70.0; resp.model_source = "heuristic_ensemble"
    resp.calibrated = False
    resp.model_version = "vtest"; resp.horizon_minutes = 60
    resp.target_spec_version = "v1-atr-band"
    mp.predict_probabilities = AsyncMock(return_value=resp)
    fc = TrendForecast1H(market_service=MagicMock(), ml_predictor=mp)
    # Ensure instance cache present (TrendForecaster.__init__ creates it).
    assert fc._ml_cache is not None
    out1 = await fc.get_ml_forecast("NIFTY 50", 60)
    assert out1 is not None
    out2 = await fc.get_ml_forecast("NIFTY 50", 60)
    assert out2 == out1
    assert mp.predict_probabilities.await_count == 1
    assert getattr(fc, "_last_ml_cache_hit", False) is True


# --- integration: SLO latency + idempotency ---

def _forecaster(candles_by_tf, ml_dict):
    ms = MagicMock()
    ms.get_candles = AsyncMock(
        side_effect=lambda symbol, timeframe=None, **kw: list(candles_by_tf.get(timeframe, []))
    )
    fc = TrendForecast1H(market_service=ms, ml_predictor=MagicMock())
    fc.get_ml_forecast = AsyncMock(return_value=dict(ml_dict) if ml_dict else None)
    return fc


@pytest.mark.asyncio
async def test_forecast_records_latency_and_cache_hit(monkeypatch):
    monkeypatch.setenv("FORECAST_CACHE", "on")
    clear_forecast_idempotency()
    PredictionService._memory_predictions.clear()
    SnapshotService._memory_snapshots.clear()
    with patch.object(ResearchOptionsContext, "get_context", new=AsyncMock(return_value=_healthy_options())), \
         patch("app.ml.sessions.classify_window", return_value=_settle_ok()):
        fc = _forecaster(_full_market(), _heuristic_ml())
        # Bypass instance ML cache (get_ml_forecast mocked) — MTF/options still cached.
        result = await fc.forecast(instrument="NIFTY 50", record=False)
    assert isinstance(result.get("latency_ms"), (int, float))
    assert result["latency_ms"] >= 0.0
    assert isinstance(result.get("cache_hit"), dict)
    assert set(result["cache_hit"]) == {"mtf", "options", "ml"}


@pytest.mark.asyncio
async def test_minute_bucket_idempotency_replays_same_id(monkeypatch):
    monkeypatch.setenv("FORECAST_CACHE", "on")
    clear_forecast_idempotency()
    PredictionService._memory_predictions.clear()
    SnapshotService._memory_snapshots.clear()
    with patch.object(ResearchOptionsContext, "get_context", new=AsyncMock(return_value=_healthy_options())), \
         patch("app.ml.sessions.classify_window", return_value=_settle_ok()):
        fc = _forecaster(_full_market(), _heuristic_ml())
        # Use real get_ml_forecast path? _forecaster mocks it; idempotency still applies
        # on record=True success. Call twice within the same minute bucket.
        r1 = await fc.forecast(instrument="NIFTY 50", record=True)
        # Second forecaster with fresh instance caches but shared module idempotency.
        fc2 = _forecaster(_full_market(), _heuristic_ml())
        r2 = await fc2.forecast(instrument="NIFTY 50", record=True)
    assert r1["prediction_id"] is not None
    assert r2["prediction_id"] == r1["prediction_id"]
    assert r2.get("idempotent_replay") is True
    assert r1.get("latency_ms") is not None and r2.get("latency_ms") is not None
    # Only one persisted prediction for the bucket (duplicate dropped).
    assert len(PredictionService._memory_predictions) == 1
    clear_forecast_idempotency()
