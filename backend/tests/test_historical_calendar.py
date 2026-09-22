"""Tests for Indian Market Calendar and 15:29 Bar Boundary Rules."""

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo
from app.historical_data.calendar.india import (
    IndianMarketCalendar,
    REGULAR_SESSION_START,
    FINAL_1M_BAR_START,
    IST_TZ,
)


def test_calendar_trading_day_detection():
    cal = IndianMarketCalendar()

    # Normal trading day (e.g. Wednesday 2024-06-05)
    wed = date(2024, 6, 5)
    assert cal.is_trading_day(wed) is True
    assert cal.is_holiday(wed) is False
    assert cal.is_weekend(wed) is False

    # Weekend (Saturday 2024-06-08)
    sat = date(2024, 6, 8)
    assert cal.is_trading_day(sat) is False
    assert cal.is_weekend(sat) is True

    # Republic Day Holiday (Friday 2024-01-26)
    rep_day = date(2024, 1, 26)
    assert cal.is_trading_day(rep_day) is False
    assert cal.is_holiday(rep_day) is True


def test_expected_candles_1529_rule():
    """Verify that a regular trading session has exactly 375 1-minute bars ending at 15:29."""
    cal = IndianMarketCalendar()
    normal_day = date(2024, 6, 5)

    # 1m resolution
    expected_1m = cal.get_expected_candles(normal_day, "1m")
    assert expected_1m == 375

    # 5m resolution: 375 / 5 = 75
    assert cal.get_expected_candles(normal_day, "5m") == 75

    # 15m resolution: 375 / 15 = 25
    assert cal.get_expected_candles(normal_day, "15m") == 25

    # Daily: 1
    assert cal.get_expected_candles(normal_day, "1D") == 1

    # Timestamps verification: first bar 09:15, last bar 15:29
    timestamps = cal.get_expected_1m_timestamps(normal_day)
    assert len(timestamps) == 375
    assert timestamps[0].time() == REGULAR_SESSION_START
    assert timestamps[-1].time() == FINAL_1M_BAR_START
    assert time(15, 30) not in [ts.time() for ts in timestamps]


def test_special_session_muhurat_trading():
    """Verify Diwali Muhurat trading session produces exact expected bars (60 for 1-hour)."""
    cal = IndianMarketCalendar()

    # Diwali 2024: Nov 1, 2024 (18:00 to 19:00 = 60 minutes)
    muhurat_day = date(2024, 11, 1)
    assert cal.is_special_session(muhurat_day) is True
    assert cal.is_trading_day(muhurat_day) is True

    expected = cal.get_expected_candles(muhurat_day, "1m")
    assert expected == 60

    ts = cal.get_expected_1m_timestamps(muhurat_day)
    assert len(ts) == 60
    assert ts[0].time() == time(18, 0)
    assert ts[-1].time() == time(18, 59)


def test_disaster_recovery_saturday_sessions():
    """Verify SEBI DR Saturday split sessions (Jan 20, 2024: 45m + 60m = 105 bars)."""
    cal = IndianMarketCalendar()
    dr_day = date(2024, 1, 20)

    assert cal.is_special_session(dr_day) is True
    assert cal.is_trading_day(dr_day) is True

    # 09:15-10:00 (45) + 11:30-12:30 (60) = 105
    expected = cal.get_expected_candles(dr_day, "1m")
    assert expected == 105
