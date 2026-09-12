"""Scheduler wiring tests (P3 follow-up). Fast, hermetic, no network/DB."""

from datetime import datetime, timezone

import pytest

from app.research import scheduler


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("FORECAST_SCHEDULER_ENABLED", raising=False)
    assert scheduler.scheduler_enabled() is False


def test_enabled_flag_variants(monkeypatch):
    for v in ("1", "true", "on", "yes", "ON"):
        monkeypatch.setenv("FORECAST_SCHEDULER_ENABLED", v)
        assert scheduler.scheduler_enabled() is True
    monkeypatch.setenv("FORECAST_SCHEDULER_ENABLED", "off")
    assert scheduler.scheduler_enabled() is False


def test_seconds_until_next_run_bounds():
    # 04:00 UTC = 09:30 IST (Saturday 2026-09-12) -> next :05 is 10:05 IST = 35 min.
    now = datetime(2026, 9, 12, 4, 0, tzinfo=timezone.utc)
    assert scheduler.seconds_until_next_run(now) == pytest.approx(35 * 60)
    # 04:36 UTC = 10:06 IST -> next 11:05 IST = 59 min.
    now2 = datetime(2026, 9, 12, 4, 36, tzinfo=timezone.utc)
    assert scheduler.seconds_until_next_run(now2) == pytest.approx(59 * 60)


@pytest.mark.asyncio
async def test_start_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("FORECAST_SCHEDULER_ENABLED", raising=False)
    assert await scheduler.start_forecast_scheduler() is False
    assert scheduler._task is None
    await scheduler.stop_forecast_scheduler()  # no-op, never raises


@pytest.mark.asyncio
async def test_run_once_never_raises(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("stage down")

    monkeypatch.setattr("app.research.shadow_scheduler.run_hourly_shadow", boom)
    out = await scheduler.run_once(instruments=["NIFTY 50"], session=object())
    assert "shadow" in out and "error" in out["shadow"]
    assert "settlement" in out  # session object without methods -> captured, not raised
