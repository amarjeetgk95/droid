"""Tactical-bias SWR cache honesty: staleness metadata + max-age refusal.

Hermetic — the engine is mocked; nothing touches providers or the DB.
"""
import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.api import research as research_api


def _payload(**extra):
    base = {
        "instrument": "NIFTY 50",
        "direction": "NEUTRAL",
        "score": 0.0,
        "confidence": 0.3,
        "limitations": [],
    }
    base.update(extra)
    return base


def _seed(key, age_s, payload=None):
    research_api._tactical_bias_cache[key] = (time.monotonic() - age_s, payload or _payload())


def _cleanup(key):
    research_api._tactical_bias_cache.pop(key, None)
    task = research_api._tactical_bias_tasks.pop(key, None)
    if task and not task.done():
        task.cancel()
    research_api._tactical_bias_locks.pop(key, None)


async def _call(horizon="1m"):
    return await research_api.get_tactical_bias(
        horizon=horizon,
        instrument="NIFTY 50",
        record=False,
        include_layers=False,
        include_explain=True,
        session=None,
    )


async def _call_record(horizon="1m"):
    return await research_api.get_tactical_bias(
        horizon=horizon,
        instrument="NIFTY 50",
        record=True,
        include_layers=False,
        include_explain=True,
        session=None,
    )


def test_stamp_marks_fresh_payload():
    stamped = research_api._stamp_tactical_bias(_payload(), 0.0)
    assert stamped["stale"] is False
    assert stamped["cache_age_s"] == 0.0
    assert "served-stale-cache" not in stamped["limitations"]


def test_stamp_marks_stale_and_never_mutates_cache_entry():
    cached = _payload()
    stamped = research_api._stamp_tactical_bias(cached, research_api.TACTICAL_BIAS_FRESH_TTL + 1)
    assert stamped["stale"] is True
    assert "served-stale-cache" in stamped["limitations"]
    assert "stale" not in cached and "cache_age_s" not in cached

    deduped = research_api._stamp_tactical_bias(
        _payload(limitations=["served-stale-cache"]),
        research_api.TACTICAL_BIAS_FRESH_TTL + 1,
    )
    assert deduped["limitations"].count("served-stale-cache") == 1


async def test_fresh_cache_served_with_metadata():
    key = "NIFTY 50:1m:False:True"
    _seed(key, 1.0)
    try:
        res = await _call()
        assert res["stale"] is False
        assert res["cache_age_s"] < research_api.TACTICAL_BIAS_FRESH_TTL
    finally:
        _cleanup(key)


async def test_aging_cache_served_stale_and_refresh_triggered():
    key = "NIFTY 50:5m:False:True"
    _seed(key, research_api.TACTICAL_BIAS_FRESH_TTL + 1)
    engine = AsyncMock(side_effect=RuntimeError("feed down"))
    try:
        with patch("app.research.trend_forecast.tactical_horizon_engine.forecast", new=engine):
            res = await _call(horizon="5m")
            await asyncio.sleep(0.05)
        assert res["stale"] is True
        assert res["cache_age_s"] >= research_api.TACTICAL_BIAS_FRESH_TTL
        assert "served-stale-cache" in res["limitations"]
        assert engine.await_count == 1
    finally:
        _cleanup(key)


async def test_payload_past_max_age_is_never_served():
    key = "NIFTY 50:15m:False:True"
    _seed(key, research_api.TACTICAL_BIAS_MAX_AGE + 1)
    engine = AsyncMock(side_effect=RuntimeError("feed down"))
    try:
        with patch("app.research.trend_forecast.tactical_horizon_engine.forecast", new=engine):
            with pytest.raises(HTTPException) as exc:
                await _call(horizon="15m")
        assert exc.value.status_code == 500
        assert engine.await_count == 1
    finally:
        _cleanup(key)


async def test_deadline_past_max_age_returns_503():
    from app.research.trend_forecast import ForecastDeadlineExceeded

    key = "NIFTY 50:1h:False:True"
    _seed(key, research_api.TACTICAL_BIAS_MAX_AGE + 1)
    engine = AsyncMock(side_effect=ForecastDeadlineExceeded("slow"))
    try:
        with patch("app.research.trend_forecast.tactical_horizon_engine.forecast", new=engine):
            with pytest.raises(HTTPException) as exc:
                await _call(horizon="1h")
        assert exc.value.status_code == 503
    finally:
        _cleanup(key)


# ---------------------------------------------------------------------------
# record=true ("Generate forecast") honours the regenerate + persist promise
# ---------------------------------------------------------------------------

async def test_record_true_forces_regeneration_on_stale_cache():
    """A stale cache hit must not serve stale data to a manual regeneration:
    the engine runs synchronously and the response is fresh."""
    key = "NIFTY 50:30m:False:True"
    _seed(key, research_api.TACTICAL_BIAS_FRESH_TTL + 1)
    engine = AsyncMock(
        return_value=_payload(direction="BULLISH", persisted=True, limitations=[])
    )
    try:
        with patch("app.research.trend_forecast.tactical_horizon_engine.forecast", new=engine):
            res = await _call_record(horizon="30m")
        assert engine.await_count == 1  # inline, not a background task
        assert res["stale"] is False
        assert "served-stale-cache" not in res["limitations"]
        assert res["generated_at"]
    finally:
        _cleanup(key)


async def test_record_true_serves_fresh_persisted_cache():
    """A fresh cache entry that already persisted is not recomputed."""
    key = "NIFTY 50:5m:False:True"
    _seed(key, 1.0, payload=_payload(persisted=True))
    engine = AsyncMock(side_effect=AssertionError("must not regenerate"))
    try:
        with patch("app.research.trend_forecast.tactical_horizon_engine.forecast", new=engine):
            res = await _call_record(horizon="5m")
        assert engine.await_count == 0
        assert res["stale"] is False
    finally:
        _cleanup(key)


async def test_record_true_regenerates_fresh_unpersisted_cache():
    """A fresh cache entry from a record=false read persisted nothing, so a
    manual regeneration must redo the run to actually persist it."""
    key = "NIFTY 50:15m:False:True"
    _seed(key, 1.0, payload=_payload())
    engine = AsyncMock(
        return_value=_payload(direction="BULLISH", persisted=True, limitations=[])
    )
    try:
        with patch("app.research.trend_forecast.tactical_horizon_engine.forecast", new=engine):
            res = await _call_record(horizon="15m")
        assert engine.await_count == 1
        assert res["stale"] is False
    finally:
        _cleanup(key)


# ---------------------------------------------------------------------------
# Prewarm: fresh hits nearing expiry re-arm the cache for the next tick
# ---------------------------------------------------------------------------

async def test_fresh_hit_past_prewarm_arms_background_refresh():
    key = "NIFTY 50:1m:False:True"
    _seed(key, research_api.TACTICAL_BIAS_PREWARM_AFTER_S + 1)
    engine = AsyncMock(side_effect=RuntimeError("feed down"))
    try:
        with patch("app.research.trend_forecast.tactical_horizon_engine.forecast", new=engine):
            res = await _call()
            await asyncio.sleep(0.05)
        assert res["stale"] is False  # still served fresh...
        assert engine.await_count == 1  # ...but the cache is re-armed behind it
    finally:
        _cleanup(key)


async def test_fresh_hit_before_prewarm_skips_background_refresh():
    key = "NIFTY 50:1m:False:True"
    _seed(key, 1.0)
    engine = AsyncMock(side_effect=RuntimeError("feed down"))
    try:
        with patch("app.research.trend_forecast.tactical_horizon_engine.forecast", new=engine):
            res = await _call()
            await asyncio.sleep(0.05)
        assert res["stale"] is False
        assert engine.await_count == 0
    finally:
        _cleanup(key)
