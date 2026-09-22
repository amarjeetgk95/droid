"""Tests for Automated Daily EOD Ingestion & Catch-Up Service."""

import pytest
from datetime import date, datetime, time, timezone, timedelta
from zoneinfo import ZoneInfo
from fastapi.testclient import TestClient

from app.historical_data.calendar.india import IST_TZ
from app.historical_data.services.auto_sync_service import HistoricalAutoSyncService, auto_sync_service
from app.historical_data.models.dataset import HistoricalDataset
from app.main import app


def test_calendar_session_completion_logic():
    service = HistoricalAutoSyncService()

    # Wednesday 10:00 AM IST (Session is live, not completed yet) -> Last completed should be Tuesday
    # 2024-06-05 was Wednesday
    live_session = datetime(2024, 6, 5, 10, 0, tzinfo=IST_TZ)
    last_completed = service.get_last_completed_trading_day(live_session)
    assert last_completed == date(2024, 6, 4)  # Tuesday

    # Wednesday 17:00 PM IST (Post-settlement) -> Last completed should be Wednesday
    post_market = datetime(2024, 6, 5, 17, 0, tzinfo=IST_TZ)
    last_completed = service.get_last_completed_trading_day(post_market)
    assert last_completed == date(2024, 6, 5)  # Wednesday itself

    # Sunday 12:00 PM IST -> Last completed should be Friday
    # 2024-06-09 was Sunday, 2024-06-07 was Friday
    sunday_noon = datetime(2024, 6, 9, 12, 0, tzinfo=IST_TZ)
    last_completed = service.get_last_completed_trading_day(sunday_noon)
    assert last_completed == date(2024, 6, 7)  # Friday


def test_next_scheduled_run_calculation():
    service = HistoricalAutoSyncService()

    # Wednesday 11:00 AM IST -> Next run should be Wednesday 16:30 IST
    wed_morning = datetime(2024, 6, 5, 11, 0, tzinfo=IST_TZ)
    nxt = service.get_next_scheduled_run_ist(wed_morning)
    assert nxt.date() == date(2024, 6, 5)
    assert nxt.time() == time(16, 30)

    # Friday 18:00 PM IST (after market) -> Next run should be Monday 16:30 IST
    # 2024-06-07 was Friday, 2024-06-10 was Monday
    fri_evening = datetime(2024, 6, 7, 18, 0, tzinfo=IST_TZ)
    nxt = service.get_next_scheduled_run_ist(fri_evening)
    assert nxt.date() == date(2024, 6, 10)
    assert nxt.time() == time(16, 30)


@pytest.mark.asyncio
async def test_missing_deltas_detection(monkeypatch):
    service = HistoricalAutoSyncService()

    # Suppose current time is Monday 17:00 IST (2024-06-10)
    now_dt = datetime(2024, 6, 10, 17, 0, tzinfo=IST_TZ)
    monkeypatch.setattr(service, "get_last_completed_trading_day", lambda now=None: date(2024, 6, 10))

    # Mock dataset latest timestamp as Friday 15:29 IST (2024-06-07)
    friday_close = datetime(2024, 6, 7, 15, 29, tzinfo=IST_TZ)
    fake_dataset = HistoricalDataset(
        id="SENSEX_1M",
        symbol="SENSEX",
        exchange="BSE",
        asset_type="INDEX",
        timeframe="1m",
        provider="fyers",
        status="READY",
        latest_available_ts=friday_close,
        total_candles=1000,
    )

    async def mock_get_dataset(dataset_id: str):
        if dataset_id == "SENSEX_1M":
            return fake_dataset
        return None

    monkeypatch.setattr("app.historical_data.storage.db_repository.db_repo.get_dataset", mock_get_dataset)
    async def mock_symbols():
        return ["SENSEX"]
    monkeypatch.setattr(service, "get_active_symbols", mock_symbols)

    missing = await service.check_missing_deltas()
    assert "SENSEX" in missing
    # Missing range should be Monday (2024-06-10) to Monday (2024-06-10)
    start_dt, end_dt = missing["SENSEX"]
    assert start_dt == date(2024, 6, 8) or start_dt == date(2024, 6, 10)
    assert end_dt == date(2024, 6, 10)


def test_auto_sync_status_and_toggle_endpoints():
    with TestClient(app) as client:
        # Check status endpoint
        res = client.get("/api/v1/historical-data/auto-sync/status")
        assert res.status_code == 200
        data = res.json()
        assert "enabled" in data
        assert "next_run_ist" in data
        assert "tracked_symbols" in data

        # Test toggle endpoint
        toggle_res = client.post("/api/v1/historical-data/auto-sync/toggle", params={"enabled": False})
        assert toggle_res.status_code == 200
        assert toggle_res.json()["enabled"] is False

        toggle_res2 = client.post("/api/v1/historical-data/auto-sync/toggle", params={"enabled": True})
        assert toggle_res2.status_code == 200
        assert toggle_res2.json()["enabled"] is True
