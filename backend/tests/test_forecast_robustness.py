"""Forecast robustness regressions (P0-1/P0-2/P0-3, P1-1, P1-4).

Covers the fixes described in docs/FORECAST_ROBUSTNESS_REVIEW.md:
- P0-1/P0-2: a supplied session is the durable store of record; a failed insert
  is surfaced as persistence-failed + persisted=false instead of returning an id
  for a row that was never written.
- P0-3: a minute bucket already recorded (e.g. by another worker) is reused with
  no duplicate INSERT.
- P1-1: synthetic options defaults (available=False / data_quality=EMPTY) never
  produce EM-sized targets.
- P1-4: an all-empty MTF picture is not cached (a transient broker blip must not
  poison the next 30s of retries).

Hermetic: no network, no DB, no broker. The session is a minimal stub.
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.research.options_context import ResearchOptionsContext
from app.research.predictions import (
    PersistenceError,
    PredictionService,
    SnapshotService,
)
from app.research.trend_forecast import (
    ForecastDeadlineExceeded,
    TrendForecast1H,
    clear_forecast_idempotency,
)

BASE_TS = datetime(2026, 9, 9, 4, 30, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

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


def _ml_predictor(calls=None):
    """Predictor double returning a fully-numeric response (real ML path)."""
    resp = MagicMock()
    resp.bullish_pct = 55.0
    resp.neutral_pct = 20.0
    resp.bearish_pct = 25.0
    resp.predicted_bias = "BULLISH"
    resp.trend_strength = 62.0
    resp.confidence_score = 70.0
    resp.model_source = "heuristic_ensemble"
    resp.calibrated = False
    resp.model_version = "vtest"
    resp.horizon_minutes = 60
    resp.target_spec_version = "v1-atr-band"
    mp = MagicMock()

    async def _predict(**kw):
        if calls is not None:
            calls["n"] = calls.get("n", 0) + 1
        return resp

    mp.predict_probabilities = _predict
    return mp


def _real_forecaster(candles_by_tf, ml_predictor):
    """Forecaster with the real ML + cache paths (only the broker is doubled)."""
    ms = MagicMock()
    ms.get_candles = AsyncMock(
        side_effect=lambda symbol, timeframe=None, **kw: list(candles_by_tf.get(timeframe, []))
    )
    return TrendForecast1H(market_service=ms, ml_predictor=ml_predictor)


def _forecaster(candles_by_tf, ml_dict):
    ms = MagicMock()
    ms.get_candles = AsyncMock(
        side_effect=lambda symbol, timeframe=None, **kw: list(candles_by_tf.get(timeframe, []))
    )
    fc = TrendForecast1H(market_service=ms, ml_predictor=MagicMock())
    fc.get_ml_forecast = AsyncMock(return_value=dict(ml_dict) if ml_dict else None)
    return fc


class _FakeResult:
    def __init__(self, row=None):
        self._row = row

    def mappings(self):
        return self

    def first(self):
        return self._row

    def all(self):
        return [self._row] if self._row else []


class _FakeSession:
    """Minimal AsyncSession stand-in: records statements, can fail on a match."""

    def __init__(self, existing_row=None, fail_on=()):
        self.existing_row = existing_row
        self.fail_on = tuple(fail_on)
        self.executed = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        low = sql.lower()
        for needle in self.fail_on:
            if needle.lower() in low:
                raise RuntimeError(f"db-down:{needle}")
        head = sql.strip().split()[0].upper() if sql.strip() else ""
        self.executed.append((head, low))
        if head == "SELECT":
            return _FakeResult(self.existing_row)
        return _FakeResult(None)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    def inserts(self):
        return [e for e in self.executed if e[0] == "INSERT"]

    def selects(self):
        return [e for e in self.executed if e[0] == "SELECT"]


def _clear_stores():
    clear_forecast_idempotency()
    PredictionService._memory_predictions.clear()
    SnapshotService._memory_snapshots.clear()


# ---------------------------------------------------------------------------
# P0-1 / P0-2: durable persistence
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_forecast_persists_through_supplied_session():
    _clear_stores()
    session = _FakeSession()
    with patch.object(ResearchOptionsContext, "get_context",
                      new=AsyncMock(return_value=_healthy_options())), \
         patch("app.ml.sessions.classify_window", return_value=_settle_ok()):
        fc = _forecaster(_full_market(), _heuristic_ml())
        result = await fc.forecast(instrument="NIFTY 50", record=True, session=session)

    assert result["persisted"] is True
    assert result["prediction_id"] is not None
    assert result["snapshot_id"] is not None
    # snapshot + prediction rows were written through the caller's session.
    assert len(session.inserts()) == 2
    assert session.commits == 2
    # ...and the lookup guard ran before the inserts.
    assert len(session.selects()) == 1


@pytest.mark.asyncio
async def test_forecast_without_session_is_not_claimed_as_persisted():
    _clear_stores()
    with patch.object(ResearchOptionsContext, "get_context",
                      new=AsyncMock(return_value=_healthy_options())), \
         patch("app.ml.sessions.classify_window", return_value=_settle_ok()):
        fc = _forecaster(_full_market(), _heuristic_ml())
        result = await fc.forecast(instrument="NIFTY 50", record=True)

    # Memory-only recording still returns ids (legacy contract) but must not
    # advertise durable persistence.
    assert result["prediction_id"] is not None
    assert result["persisted"] is False


@pytest.mark.asyncio
async def test_forecast_db_write_failure_degrades_honestly():
    _clear_stores()
    session = _FakeSession(fail_on=("insert into research_snapshots",))
    with patch.object(ResearchOptionsContext, "get_context",
                      new=AsyncMock(return_value=_healthy_options())), \
         patch("app.ml.sessions.classify_window", return_value=_settle_ok()):
        fc = _forecaster(_full_market(), _heuristic_ml())
        result = await fc.forecast(instrument="NIFTY 50", record=True, session=session)

    assert result["persisted"] is False
    assert result["prediction_id"] is None
    assert result["snapshot_id"] is None  # never persist a prediction without one
    assert result["status"] == "DEGRADED"
    assert "persistence-failed:snapshot" in result["limitations"]
    # The failed snapshot must not stay mirrored in memory as if it were written.
    assert SnapshotService._memory_snapshots == {}
    assert len(session.inserts()) == 0


@pytest.mark.asyncio
async def test_prediction_write_failure_keeps_snapshot_and_reports_unpersisted():
    _clear_stores()
    session = _FakeSession(fail_on=("insert into research_predictions",))
    with patch.object(ResearchOptionsContext, "get_context",
                      new=AsyncMock(return_value=_healthy_options())), \
         patch("app.ml.sessions.classify_window", return_value=_settle_ok()):
        fc = _forecaster(_full_market(), _heuristic_ml())
        result = await fc.forecast(instrument="NIFTY 50", record=True, session=session)

    assert result["persisted"] is False
    assert result["prediction_id"] is None
    assert result["snapshot_id"] is not None  # kept for audit
    assert "persistence-failed:prediction" in result["limitations"]
    assert PredictionService._memory_predictions == {}


# ---------------------------------------------------------------------------
# P0-3: no duplicate rows for a minute bucket already recorded
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_minute_bucket_already_recorded_skips_writes():
    _clear_stores()
    existing = {"prediction_id": "forecast_1h_existing1", "snapshot_id": "snap_existing1"}
    session = _FakeSession(existing_row=existing)
    with patch.object(ResearchOptionsContext, "get_context",
                      new=AsyncMock(return_value=_healthy_options())), \
         patch("app.ml.sessions.classify_window", return_value=_settle_ok()):
        fc = _forecaster(_full_market(), _heuristic_ml())
        result = await fc.forecast(instrument="NIFTY 50", record=True, session=session)

    assert session.inserts() == []          # no duplicate immutable rows
    assert result["prediction_id"] == existing["prediction_id"]
    assert result["snapshot_id"] == existing["snapshot_id"]
    assert result["idempotent_replay"] is True
    assert result["persisted"] is True
    assert result["status"] == "RESEARCH"   # a reused record is not a degradation


# ---------------------------------------------------------------------------
# P1-1: synthetic options never size targets
# ---------------------------------------------------------------------------

def _minimal_mtf():
    return {
        "instrument": "NIFTY 50",
        "per_timeframe": {
            "1h": {"features": {
                "quant": {"supertrend_dir": "BULLISH", "rsi_14": 60.0, "atr_14": 50.0},
                "regime": "RANGING",
                "session": "EARLY",
            }},
        },
        "alignment": {"overall_bias": "BULLISH", "alignment_score": 100.0},
    }


def _ensemble(**kw):
    fc = TrendForecast1H.__new__(TrendForecast1H)
    return fc.ensemble_forecast(**kw)


def test_synthetic_options_produce_atr_only_targets(monkeypatch):
    monkeypatch.setenv("FORECAST_V2_MODEL", "logistic-v2")
    synthetic = dict(_healthy_options(), available=False, data_quality="EMPTY")
    res = _ensemble(mtf_features=_minimal_mtf(), indicator_outputs=[],
                    ml_forecast=_heuristic_ml(), options_ctx=synthetic,
                    current_price=25000.0, horizon="1h")
    # The EM that the synthetic atm_iv=15 / dte=1 would have produced is ignored.
    assert res["target_basis"] == "ATR-only"
    assert "em-unavailable-synthetic-options" in res["limitations"]
    assert "target_basis=ATR-only" in res["limitations"]


def test_live_options_still_use_em_targets(monkeypatch):
    monkeypatch.setenv("FORECAST_V2_MODEL", "logistic-v2")
    res = _ensemble(mtf_features=_minimal_mtf(), indicator_outputs=[],
                    ml_forecast=_heuristic_ml(), options_ctx=_healthy_options(),
                    current_price=25000.0, horizon="1h")
    assert res["target_basis"] == "ATR+EM"
    assert "em-unavailable-synthetic-options" not in res["limitations"]


# ---------------------------------------------------------------------------
# P1-4: an all-empty MTF picture is not cached
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_empty_mtf_candles_use_a_short_negative_cache(monkeypatch):
    from app.research.cache import MTF_TTL_S, NEGATIVE_TTL_S, TTLCache, make_mtf_key
    from app.research.trend_forecast import FORECAST_TIMEFRAMES

    monkeypatch.setenv("FORECAST_CACHE", "on")
    market = MagicMock()
    market.get_candles = AsyncMock(return_value=[])
    fc = TrendForecast1H(market_service=market, ml_predictor=MagicMock())
    now = [0.0]
    fc._mtf_cache = TTLCache(MTF_TTL_S, now_fn=lambda: now[0])

    await fc.fetch_multi_timeframe_candles("NIFTY 50")
    await fc.fetch_multi_timeframe_candles("NIFTY 50")
    # Coalesced onto the short negative entry (no second fan-out against a dead feed).
    assert market.get_candles.await_count == 7

    now[0] += NEGATIVE_TTL_S + 0.01
    await fc.fetch_multi_timeframe_candles("NIFTY 50")
    # Expired almost immediately, so a re-auth + Retry hits the broker again
    # instead of being served a poisoned 30s entry.
    assert market.get_candles.await_count == 14
    key = make_mtf_key("NIFTY 50", list(FORECAST_TIMEFRAMES))
    assert key in fc._mtf_cache._store  # stored, but on the short TTL


@pytest.mark.asyncio
async def test_non_empty_mtf_candles_are_still_cached(monkeypatch):
    monkeypatch.setenv("FORECAST_CACHE", "on")
    market = MagicMock()
    market.get_candles = AsyncMock(
        side_effect=lambda symbol, timeframe=None, **kw: list(_full_market().get(timeframe, []))
    )
    fc = TrendForecast1H(market_service=market, ml_predictor=MagicMock())

    await fc.fetch_multi_timeframe_candles("NIFTY 50")
    await fc.fetch_multi_timeframe_candles("NIFTY 50")

    assert market.get_candles.await_count == 7


# ---------------------------------------------------------------------------
# P1-2: end-to-end deadline + per-stage timeouts
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_forecast_deadline_raises_instead_of_hanging(monkeypatch):
    monkeypatch.setenv("FORECAST_DEADLINE_S", "0.05")
    market = MagicMock()

    async def _slow_candles(symbol, timeframe=None, **kw):
        await asyncio.sleep(2.0)
        return []

    market.get_candles = _slow_candles
    fc = TrendForecast1H(market_service=market, ml_predictor=MagicMock())

    started = time.monotonic()
    with pytest.raises(ForecastDeadlineExceeded):
        await fc.forecast(instrument="NIFTY 50", record=False)

    # Bounded by the budget (not the caller's 60s timeout) and never a verdict.
    assert time.monotonic() - started < 1.0


@pytest.mark.asyncio
async def test_forecast_deadline_disabled_keeps_legacy_path(monkeypatch):
    monkeypatch.setenv("FORECAST_DEADLINE_S", "0")
    with patch.object(ResearchOptionsContext, "get_context",
                      new=AsyncMock(return_value=_healthy_options())), \
         patch("app.ml.sessions.classify_window", return_value=_settle_ok()):
        fc = _forecaster(_full_market(), _heuristic_ml())
        result = await fc.forecast(instrument="NIFTY 50", record=False)
    assert result["forecast_version"] == "1h-v2"
    assert "latency_ms" in result


@pytest.mark.asyncio
async def test_options_stage_timeout_degrades_without_failing(monkeypatch):
    monkeypatch.setenv("FORECAST_STAGE_TIMEOUT_S", "0.05")
    monkeypatch.setenv("FORECAST_DEADLINE_S", "5")

    async def _slow_context(instrument):
        await asyncio.sleep(1.0)
        return _healthy_options()

    with patch.object(ResearchOptionsContext, "get_context", new=_slow_context), \
         patch("app.ml.sessions.classify_window", return_value=_settle_ok()):
        fc = _forecaster(_full_market(), _heuristic_ml())
        result = await fc.forecast(instrument="NIFTY 50", record=False)

    assert result["status"] == "DEGRADED"
    assert "options-unavailable-degraded" in result["limitations"]


@pytest.mark.asyncio
async def test_ml_stage_timeout_caps_confidence(monkeypatch):
    monkeypatch.setenv("FORECAST_STAGE_TIMEOUT_S", "0.05")
    monkeypatch.setenv("FORECAST_DEADLINE_S", "5")
    predictor = MagicMock()

    async def _slow_predict(**kw):
        await asyncio.sleep(1.0)
        return _heuristic_ml()

    predictor.predict_probabilities = _slow_predict
    market = MagicMock()
    market.get_candles = AsyncMock(
        side_effect=lambda symbol, timeframe=None, **kw: list(_full_market().get(timeframe, []))
    )
    fc = TrendForecast1H(market_service=market, ml_predictor=predictor)

    with patch.object(ResearchOptionsContext, "get_context",
                      new=AsyncMock(return_value=_healthy_options())), \
         patch("app.ml.sessions.classify_window", return_value=_settle_ok()):
        result = await fc.forecast(instrument="NIFTY 50", record=False)

    assert result["ml_forecast"] is None
    assert "ml-unavailable-confidence-capped-0.55" in result["limitations"]


# ---------------------------------------------------------------------------
# P1-5: single-flight coalescing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_mtf_misses_are_coalesced(monkeypatch):
    monkeypatch.setenv("FORECAST_CACHE", "on")
    market = MagicMock()
    calls = {"n": 0}

    async def _slow_fetch(symbol, timeframe=None, **kw):
        calls["n"] += 1
        await asyncio.sleep(0.05)  # both callers stay inside the same flight
        return list(_full_market().get(timeframe, []))

    market.get_candles = _slow_fetch
    fc = TrendForecast1H(market_service=market, ml_predictor=MagicMock())

    r1, r2 = await asyncio.gather(
        fc.fetch_multi_timeframe_candles("NIFTY 50"),
        fc.fetch_multi_timeframe_candles("NIFTY 50"),
    )

    assert calls["n"] == 7  # one shared fan-out, not two
    assert r1.get("1h") and r2.get("1h")


@pytest.mark.asyncio
async def test_concurrent_ml_misses_are_coalesced(monkeypatch):
    monkeypatch.setenv("FORECAST_CACHE", "on")
    predictor = MagicMock()
    calls = {"n": 0}

    async def _slow_predict(**kw):
        calls["n"] += 1
        await asyncio.sleep(0.05)
        resp = MagicMock()
        resp.bullish_pct = 55.0
        resp.neutral_pct = 20.0
        resp.bearish_pct = 25.0
        resp.predicted_bias = "BULLISH"
        resp.trend_strength = 62.0
        resp.confidence_score = 70.0
        resp.model_source = "heuristic_ensemble"
        resp.calibrated = False
        resp.model_version = "vtest"
        resp.horizon_minutes = 60
        resp.target_spec_version = "v1-atr-band"
        return resp

    predictor.predict_probabilities = _slow_predict
    fc = TrendForecast1H(market_service=MagicMock(), ml_predictor=predictor)

    out1, out2 = await asyncio.gather(
        fc.get_ml_forecast("NIFTY 50", 60),
        fc.get_ml_forecast("NIFTY 50", 60),
    )

    assert calls["n"] == 1  # one model call, shared
    assert out1 == out2


# ---------------------------------------------------------------------------
# P1-6: heavy layers are opt-in and never retained by the replay cache
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_heavy_layers_are_opt_in():
    _clear_stores()
    with patch.object(ResearchOptionsContext, "get_context",
                      new=AsyncMock(return_value=_healthy_options())), \
         patch("app.ml.sessions.classify_window", return_value=_settle_ok()):
        fc = _forecaster(_full_market(), _heuristic_ml())
        slim = await fc.forecast(instrument="NIFTY 50", record=False)
        debug = await fc.forecast(instrument="NIFTY 50", record=False, include_layers=True)

    assert "mtf_features" not in slim
    assert "indicator_outputs" not in slim
    assert "options_context" not in slim
    assert "explain" in slim  # the curated bundle stays: the UI renders it

    assert "mtf_features" in debug
    assert "indicator_outputs" in debug
    assert "options_context" in debug


@pytest.mark.asyncio
async def test_replay_cache_does_not_retain_heavy_layers():
    _clear_stores()
    with patch.object(ResearchOptionsContext, "get_context",
                      new=AsyncMock(return_value=_healthy_options())), \
         patch("app.ml.sessions.classify_window", return_value=_settle_ok()):
        fc = _forecaster(_full_market(), _heuristic_ml())
        first = await fc.forecast(instrument="NIFTY 50", record=True, include_layers=True)
        # Fresh forecaster, shared module-level replay map -> same minute bucket.
        fc2 = _forecaster(_full_market(), _heuristic_ml())
        replayed = await fc2.forecast(instrument="NIFTY 50", record=True, include_layers=True)

    assert "mtf_features" in first
    assert replayed["idempotent_replay"] is True
    assert replayed["prediction_id"] == first["prediction_id"]
    assert "mtf_features" not in replayed  # replay keeps only the slim reply
    _clear_stores()


# ---------------------------------------------------------------------------
# P1-3: per-call cache provenance reaches the response
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_response_cache_hit_reflects_real_provenance():
    _clear_stores()
    calls: dict = {}
    with patch.object(ResearchOptionsContext, "get_context",
                      new=AsyncMock(return_value=_healthy_options())), \
         patch("app.ml.sessions.classify_window", return_value=_settle_ok()):
        fc = _real_forecaster(_full_market(), _ml_predictor(calls))
        first = await fc.forecast(instrument="NIFTY 50", record=False)
        second = await fc.forecast(instrument="NIFTY 50", record=False)

    assert first["cache_hit"] == {"mtf": False, "options": False, "ml": False}
    assert second["cache_hit"] == {"mtf": True, "options": True, "ml": True}
    # The hits were real: one candle fan-out and one model call served both.
    assert calls["n"] == 1
    assert fc.market_service.get_candles.await_count == 7


# ---------------------------------------------------------------------------
# P1-7: the explain bundle is client-controllable
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_include_explain_false_trims_response_but_not_recording():
    _clear_stores()
    with patch.object(ResearchOptionsContext, "get_context",
                      new=AsyncMock(return_value=_healthy_options())), \
         patch("app.ml.sessions.classify_window", return_value=_settle_ok()):
        fc = _forecaster(_full_market(), _heuristic_ml())
        trimmed = await fc.forecast(instrument="NIFTY 50", record=True, include_explain=False)
        full = await fc.forecast(instrument="NIFTY 50", record=False, include_explain=True)

    assert "explain" not in trimmed
    assert isinstance(full.get("explain"), dict)
    # The recording keeps the bundle: auditability is not a client knob.
    pred = await PredictionService.get_prediction(trimmed["prediction_id"])
    assert pred is not None
    assert isinstance(pred.component_values.get("explain"), dict)


# ---------------------------------------------------------------------------
# P2-3: runtime counters make silent failures visible in monitoring
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_runtime_counters_track_persistence_failure():
    from app.research.trend_forecast import (
        forecast_runtime_metrics,
        reset_forecast_runtime_metrics,
    )

    reset_forecast_runtime_metrics()
    _clear_stores()
    session = _FakeSession(fail_on=("insert into research_snapshots",))
    try:
        with patch.object(ResearchOptionsContext, "get_context",
                          new=AsyncMock(return_value=_healthy_options())), \
             patch("app.ml.sessions.classify_window", return_value=_settle_ok()):
            fc = _forecaster(_full_market(), _heuristic_ml())
            result = await fc.forecast(instrument="NIFTY 50", record=True, session=session)

        runtime = forecast_runtime_metrics()
        assert result["persisted"] is False
        assert runtime["calls"] == 1
        assert runtime["persist_failures"] == 1
        assert runtime["last_persist_failures_at"] is not None
        assert runtime["degraded"] == 1
        assert runtime["latency_samples"] == 1
        assert runtime["latency_ms_p50"] is not None
    finally:
        reset_forecast_runtime_metrics()


@pytest.mark.asyncio
async def test_forecast_health_surfaces_fresh_runtime_failure():
    from app.api import monitoring as mon_api
    from app.research.trend_forecast import reset_forecast_runtime_metrics

    reset_forecast_runtime_metrics()
    _clear_stores()
    session = _FakeSession(fail_on=("insert into research_snapshots",))
    try:
        with patch.object(ResearchOptionsContext, "get_context",
                          new=AsyncMock(return_value=_healthy_options())), \
             patch("app.ml.sessions.classify_window", return_value=_settle_ok()):
            fc = _forecaster(_full_market(), _heuristic_ml())
            await fc.forecast(instrument="NIFTY 50", record=True, session=session)

        body = await mon_api.forecast_health(limit=50, instrument=None)
        assert body["runtime"]["persist_failures"] == 1
        assert any(r.startswith("persist_failures:1") for r in body["reasons"])
        assert body["degraded"] is True
    finally:
        reset_forecast_runtime_metrics()


def test_stale_runtime_failure_is_reported_as_historical():
    from app.api import monitoring as mon_api

    stale = (
        datetime.now(timezone.utc)
        - timedelta(seconds=mon_api.RUNTIME_FRESH_WINDOW_S + 60)
    ).isoformat()
    assert mon_api._fresh_runtime_failures(
        {"persist_failures": 3, "last_persist_failures_at": stale}
    ) == ["persist_failures:3(historical)"]
    # Zero-count entries never produce a reason; a count without a usable stamp
    # cannot be proven fresh, so it is reported as historical.
    assert mon_api._fresh_runtime_failures({"persist_failures": 0}) == []
    assert mon_api._fresh_runtime_failures({"deadline_exceeded": 2}) == [
        "deadline_exceeded:2(historical)"
    ]


# P0-2 service-level contract
# ---------------------------------------------------------------------------

class _FlexibleForecaster:
    def __init__(self):
        self.kwargs = None

    async def forecast(self, instrument="NIFTY 50", horizon="1h", record=False, **kwargs):
        self.kwargs = dict(kwargs)
        return {"instrument": instrument, "options_context": {"available": True}}


class _RigidForecaster:
    def __init__(self):
        self.called = False

    async def forecast(self, instrument, horizon, record):
        self.called = True
        return {"instrument": instrument}


@pytest.mark.asyncio
async def test_shadow_requests_layers_only_when_supported():
    """P1-6: the shadow runner still asks for the layers it persists."""
    from app.research.shadow import _accepts_kwarg, _call_forecast

    assert _accepts_kwarg(_FlexibleForecaster().forecast, "include_layers") is True
    assert _accepts_kwarg(_RigidForecaster().forecast, "include_layers") is False

    flexible = _FlexibleForecaster()
    await _call_forecast(flexible, instrument="NIFTY 50", horizon="1h", model="v1")
    assert flexible.kwargs.get("include_layers") is True

    # Rigid doubles keep working untouched (no unsupported kwarg forced on them).
    rigid = _RigidForecaster()
    out = await _call_forecast(rigid, instrument="NIFTY 50", horizon="1h", model="v1")
    assert rigid.called is True
    assert out["instrument"] == "NIFTY 50"


@pytest.mark.asyncio
async def test_record_prediction_strict_raises_and_drops_mirror():
    from app.research.enums import Direction, ForecastHorizon
    from app.research.models import ResearchPrediction

    session = _FakeSession(fail_on=("insert into research_predictions",))
    pred = ResearchPrediction(
        prediction_id="forecast_1h_stricttest",
        indicator_id="trend_forecast_1h",
        indicator_version="1.0.0",
        instrument="NIFTY 50",
        timeframe="1h",
        timestamp=BASE_TS,
        current_price=25000.0,
        direction=Direction.BULLISH,
        score=40.0,
        confidence=0.6,
        component_values={},
        forecast_horizon=ForecastHorizon.HORIZON_1H,
        horizon_candles=1,
    )
    PredictionService._memory_predictions.pop(pred.prediction_id, None)

    with pytest.raises(PersistenceError):
        await PredictionService.record_prediction(pred, session=session, strict=True)

    assert pred.prediction_id not in PredictionService._memory_predictions
