"""P0 contract tests for forecast 1h-v2 (MVIG-first).

Covers: valid v2 contract, bad-probability rejection, missing-snapshot
invalidity, late-session downgrade (mocked classify_window unsettleable),
missing-TF degradation, resampled-primary degradation, artifact mismatch,
and the snapshot round-trip on record=True.

Hermetic: MarketService and F&O are mocked, classify_window is patched —
no network, no broker, no DB (memory stores only).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.research.options_context import ResearchOptionsContext
from app.research.predictions import PredictionService, SnapshotService
from app.research.trend_forecast import (
    TrendForecast1H,
    score_to_probabilities_v2,
    validate_forecast_v2,
)

BASE_TS = datetime(2026, 9, 9, 4, 30, tzinfo=timezone.utc)  # 10:00 IST


def _make_candles(count: int, step_minutes: int, start_price: float = 25000.0,
                  drift: float = 1.5, end_ts: datetime = BASE_TS):
    """Ascending OHLCV series ending at end_ts (deterministic, PIT-clean)."""
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


def _fake_market(candles_by_tf):
    ms = MagicMock()
    ms.get_candles = AsyncMock(
        side_effect=lambda symbol, timeframe=None, **kw: list(candles_by_tf.get(timeframe, []))
    )
    return ms


def _heuristic_ml():
    return {
        "bullish_pct": 55.0,
        "neutral_pct": 20.0,
        "bearish_pct": 25.0,
        "predicted_bias": "BULLISH",
        "trend_strength": 62.0,
        "confidence_score": 70.0,
        "model_source": "heuristic_ensemble",
        "calibrated": False,
        "model_version": "XGBoost-LightGBM-Ensemble-v1.0-heuristic",
        "horizon_minutes": 60,
        "target_spec_version": "v1-atr-band",
    }


def _healthy_options():
    return {
        "instrument": "NIFTY 50",
        "available": True,
        "data_quality": "LIVE",
        "pcr_oi": 1.0,
        "pcr_vol": 1.0,
        "atm_iv": 15.0,
        "call_wall": None,
        "put_wall": None,
        "max_pain": None,
        "days_to_expiry": 1.0,
        "atm_theta": -10.0,
        "atm_gamma": 0.001,
        "atm_vega": 10.0,
    }


def _settle_ok():
    return {
        "universe": "nse",
        "settleable": True,
        "reason": "same-regular-session",
        "t_plus_h_utc": BASE_TS + timedelta(minutes=60),
        "session_close_utc": None,
    }


def _settle_cross_close():
    return {
        "universe": "nse",
        "settleable": False,
        "reason": "crosses-session-close",
        "t_plus_h_utc": BASE_TS + timedelta(minutes=60),
        "session_close_utc": None,
    }


def _forecaster(candles_by_tf, ml_dict):
    fc = TrendForecast1H(
        market_service=_fake_market(candles_by_tf),
        ml_predictor=MagicMock(),
    )
    fc.get_ml_forecast = AsyncMock(return_value=dict(ml_dict) if ml_dict else None)
    return fc


@pytest.fixture
def mock_options_healthy():
    with patch.object(
        ResearchOptionsContext, "get_context",
        new=AsyncMock(return_value=_healthy_options()),
    ):
        yield


# ---------------------------------------------------------------------------
# P0-1: contract
# ---------------------------------------------------------------------------

def _minimal_mtf():
    return {
        "instrument": "NIFTY 50",
        "per_timeframe": {
            "1h": {"features": {
                "quant": {"supertrend_dir": "BULLISH", "rsi_14": 60.0, "atr_14": 50.0},
                "regime": "TRENDING_UP",
                "session": "EARLY",
            }},
        },
        "alignment": {"overall_bias": "BULLISH", "alignment_score": 60.0},
    }


def test_valid_v2_contract():
    """ensemble_forecast keeps v1 keys and adds a valid v2 contract."""
    fc = TrendForecast1H.__new__(TrendForecast1H)
    result = fc.ensemble_forecast(
        mtf_features=_minimal_mtf(),
        indicator_outputs=[],
        ml_forecast=_heuristic_ml(),
        options_ctx=_healthy_options(),
        current_price=25000.0,
        horizon="1h",
    )
    # v1 keys intact for frontend compat
    assert result["direction"] in {"BULLISH", "BEARISH", "NEUTRAL"}
    assert -100.0 <= result["score"] <= 100.0
    assert set(result["layer_scores"]) == {"mtf_alignment", "indicators", "ml", "options", "structure"}
    assert "target_price" in result and "invalidation_price" in result
    # v2 keys present
    assert result["forecast_version"] == "1h-v2"
    assert result["status"] == "RESEARCH"
    probs = result["probabilities"]
    assert set(probs) == {"bullish", "neutral", "bearish"}
    assert abs(sum(probs.values()) - 1.0) < 1e-6
    assert all(0.0 <= v <= 1.0 for v in probs.values())
    assert result["confidence"] == max(probs.values())
    assert result["raw_confidence"] == max(probs.values())
    assert result["calibrated"] is False
    assert result["calibrator_version"] == "none-v0"
    assert result["weights_version"] == "forecast-v1"
    assert result["target_spec_version"] == "v2-atr-em-session"
    assert result["model_source"] == "heuristic_ensemble"
    assert isinstance(result["limitations"], list)
    assert result["prediction_id"] is None
    assert result["snapshot_id"] is None
    assert validate_forecast_v2(result) == []


def test_softmax_mapping_direction_aligned():
    """Interim T=40 softmax: argmax agrees with the ±20 direction cutoffs."""
    bull = score_to_probabilities_v2(60.0)
    assert bull["bullish"] == max(bull.values())
    bear = score_to_probabilities_v2(-60.0)
    assert bear["bearish"] == max(bear.values())
    flat = score_to_probabilities_v2(0.0)
    assert flat["neutral"] == max(flat.values())
    assert abs(sum(flat.values()) - 1.0) < 1e-9


def test_bad_probability_rejected():
    fc = TrendForecast1H.__new__(TrendForecast1H)
    result = fc.ensemble_forecast(
        mtf_features=_minimal_mtf(),
        indicator_outputs=[],
        ml_forecast=_heuristic_ml(),
        options_ctx=_healthy_options(),
        current_price=25000.0,
        horizon="1h",
    )
    bad = dict(result)
    bad["probabilities"] = {"bullish": 0.9, "neutral": 0.9, "bearish": 0.9}
    errors = validate_forecast_v2(bad)
    assert any("probabilities-sum" in e for e in errors)

    bad2 = dict(result)
    bad2["probabilities"] = {"bullish": 1.5, "neutral": -0.25, "bearish": -0.25}
    errors2 = validate_forecast_v2(bad2)
    assert any("out-of-range" in e for e in errors2)

    bad3 = dict(result)
    bad3["target_spec_version"] = ""
    assert any("missing-target_spec_version" in e for e in validate_forecast_v2(bad3))


def test_missing_snapshot_invalid():
    fc = TrendForecast1H.__new__(TrendForecast1H)
    result = fc.ensemble_forecast(
        mtf_features=_minimal_mtf(),
        indicator_outputs=[],
        ml_forecast=_heuristic_ml(),
        options_ctx=_healthy_options(),
        current_price=25000.0,
        horizon="1h",
    )
    persisted = dict(result, prediction_id="forecast_1h_abc123", snapshot_id=None)
    assert "prediction-without-snapshot" in validate_forecast_v2(persisted)
    assert "missing-snapshot-for-record" in validate_forecast_v2(persisted, record=True)
    # record=false without snapshot is fine
    assert validate_forecast_v2(result, record=False) == []


# ---------------------------------------------------------------------------
# P0-2: gates (full forecast path, mocked MarketService + F&O + settlement)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_healthy_path_research_status(mock_options_healthy):
    with patch("app.ml.sessions.classify_window", return_value=_settle_ok()):
        fc = _forecaster(_full_market(), _heuristic_ml())
        result = await fc.forecast(instrument="NIFTY 50", record=False)
    assert result["forecast_version"] == "1h-v2"
    assert result["status"] == "RESEARCH"
    assert result["settleable"] is True
    assert result["settle_reason"] == "same-regular-session"
    assert result["snapshot_id"] is None
    assert result["prediction_id"] is None
    assert result["explain"]["data_health"]["settleable"] is True
    assert validate_forecast_v2(result, record=False) == []


@pytest.mark.asyncio
async def test_late_session_downgrade(mock_options_healthy):
    """Unsettleable window: confidence capped at 0.45 + crosses-session-close
    limitation; never high-conviction."""
    with patch("app.ml.sessions.classify_window", return_value=_settle_cross_close()):
        fc = _forecaster(_full_market(), _heuristic_ml())
        result = await fc.forecast(instrument="NIFTY 50", record=False)
    assert result["settleable"] is False
    assert result["data_quality"] == "UNSETTLEABLE"
    assert result["status"] in ("ABSTAIN", "DEGRADED")
    assert result["confidence"] <= 0.45
    assert any("crosses-session-close" in lim for lim in result["limitations"])
    if result["status"] == "ABSTAIN":
        assert result["direction"] == "NEUTRAL"
    assert validate_forecast_v2(result, record=False) == []


@pytest.mark.asyncio
async def test_missing_tf_degraded(mock_options_healthy):
    """>=2 missing TFs (no 1m, so no resample rescue) -> DEGRADED."""
    thin = {"1h": _make_candles(60, 60), "5m": _make_candles(100, 5)}
    with patch("app.ml.sessions.classify_window", return_value=_settle_ok()):
        fc = _forecaster(thin, _heuristic_ml())
        result = await fc.forecast(instrument="NIFTY 50", record=False)
    assert result["status"] == "DEGRADED"
    assert result["data_quality"] == "DEGRADED"
    assert any(lim.startswith("missing-timeframes:") for lim in result["limitations"])
    assert validate_forecast_v2(result, record=False) == []


@pytest.mark.asyncio
async def test_resampled_primary_degraded(mock_options_healthy):
    """Primary 1h rebuilt from 1m resampling -> DEGRADED, still no 503."""
    only_1m = {"1m": _make_candles(400, 1)}
    with patch("app.ml.sessions.classify_window", return_value=_settle_ok()):
        fc = _forecaster(only_1m, _heuristic_ml())
        result = await fc.forecast(instrument="NIFTY 50", record=False)
    assert result["status"] == "DEGRADED"
    assert any("resampled-1h-from-1m" in lim for lim in result["limitations"])


@pytest.mark.asyncio
async def test_ml_missing_caps_confidence(mock_options_healthy):
    with patch("app.ml.sessions.classify_window", return_value=_settle_ok()):
        fc = _forecaster(_full_market(), None)
        result = await fc.forecast(instrument="NIFTY 50", record=False)
    assert result["confidence"] <= 0.55
    assert result["model_source"] == "unavailable"
    assert "ml-unavailable-confidence-capped-0.55" in result["limitations"]


@pytest.mark.asyncio
async def test_options_degraded(mock_options_healthy):
    degraded_ctx = dict(_healthy_options(), available=False, data_quality="EMPTY")
    with patch("app.ml.sessions.classify_window", return_value=_settle_ok()), patch.object(
        ResearchOptionsContext, "get_context",
        new=AsyncMock(return_value=degraded_ctx),
    ):
        fc = _forecaster(_full_market(), _heuristic_ml())
        result = await fc.forecast(instrument="NIFTY 50", record=False)
    assert result["status"] == "DEGRADED"
    assert "options-unavailable-degraded" in result["limitations"]


# ---------------------------------------------------------------------------
# P0-3: snapshot on persist
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_record_persists_snapshot_link(mock_options_healthy):
    PredictionService._memory_predictions.clear()
    SnapshotService._memory_snapshots.clear()
    with patch("app.ml.sessions.classify_window", return_value=_settle_ok()):
        fc = _forecaster(_full_market(), _heuristic_ml())
        result = await fc.forecast(instrument="NIFTY 50", record=True)
    assert result["prediction_id"] is not None
    assert result["snapshot_id"] is not None
    assert validate_forecast_v2(result, record=True) == []
    pred = await PredictionService.get_prediction(result["prediction_id"])
    assert pred is not None
    assert pred.snapshot_id == result["snapshot_id"]
    snap = await SnapshotService.get_snapshot(result["snapshot_id"])
    assert snap is not None
    assert snap.instrument == "NIFTY 50"
    assert snap.features["v2"]["settleable"] is True


@pytest.mark.asyncio
async def test_snapshot_failure_degrades_without_prediction(mock_options_healthy):
    with patch("app.ml.sessions.classify_window", return_value=_settle_ok()), patch.object(
        SnapshotService, "record_snapshot",
        new=AsyncMock(side_effect=RuntimeError("db down")),
    ):
        fc = _forecaster(_full_market(), _heuristic_ml())
        result = await fc.forecast(instrument="NIFTY 50", record=True)
    assert result["snapshot_id"] is None
    assert result["prediction_id"] is None  # never persist prediction without snapshot
    assert result["status"] == "DEGRADED"
    assert "snapshot-unavailable" in result["limitations"]


# ---------------------------------------------------------------------------
# P0-4: artifact validation + env flags
# ---------------------------------------------------------------------------

def test_artifact_mismatch_ensemble_without_h60_artifact():
    """An h60 ensemble claim with no matching h60 artifact triple is rejected
    (no silent h15 fallback)."""
    from app.research.trend_forecast import TrendForecaster
    ensemble_claim = dict(_heuristic_ml(),
                          model_source="xgboost_lightgbm_ensemble", calibrated=True)
    limitation = TrendForecaster.validate_ml_artifact(60, ensemble_claim)
    assert limitation is not None
    assert "artifact-mismatch-h60" in limitation


def test_artifact_check_passes_heuristic_and_none():
    from app.research.trend_forecast import TrendForecaster
    assert TrendForecaster.validate_ml_artifact(60, _heuristic_ml()) is None
    assert TrendForecaster.validate_ml_artifact(60, None) is None
    assert TrendForecaster.validate_ml_artifact(None, _heuristic_ml()) is None


@pytest.mark.asyncio
async def test_forecast_surface_artifact_mismatch(mock_options_healthy):
    ensemble_claim = dict(_heuristic_ml(),
                          model_source="xgboost_lightgbm_ensemble", calibrated=True)
    with patch("app.ml.sessions.classify_window", return_value=_settle_ok()):
        fc = _forecaster(_full_market(), ensemble_claim)
        result = await fc.forecast(instrument="NIFTY 50", record=False)
    assert result["ml_forecast"] is None
    assert any("artifact-mismatch-h60" in lim for lim in result["limitations"])
    assert result["confidence"] <= 0.55


@pytest.mark.asyncio
async def test_heuristic_flag_off_disables_heuristic(mock_options_healthy, monkeypatch):
    monkeypatch.setenv("FORECAST_ALLOW_HEURISTIC", "false")
    with patch("app.ml.sessions.classify_window", return_value=_settle_ok()):
        fc = _forecaster(_full_market(), _heuristic_ml())
        result = await fc.forecast(instrument="NIFTY 50", record=False)
    assert result["ml_forecast"] is None
    assert "heuristic-disabled-by-FORECAST_ALLOW_HEURISTIC" in result["limitations"]
