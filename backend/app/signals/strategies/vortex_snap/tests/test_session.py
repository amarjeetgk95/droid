"""
Unit tests for Market Session Model (§4).
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import pytest

from app.signals.strategies.vortex_snap.session import MarketSessionModel
from app.signals.strategies.vortex_snap.types import SessionPhase
from app.signals.strategies.vortex_snap.config import SessionConfig


def make_ist_timestamp(year: int, month: int, day: int, hour: int, minute: int) -> int:
    """Create epoch millisecond timestamp for given IST time."""
    tz = ZoneInfo("Asia/Kolkata")
    dt = datetime(year, month, day, hour, minute, 0, tzinfo=tz)
    return int(dt.timestamp() * 1000)


class TestMarketSessionModel:
    def setup_method(self):
        self.model = MarketSessionModel()

    def test_pre_open_phase(self):
        # 2026-09-21 is a Monday, 09:05 IST
        ts = make_ist_timestamp(2026, 9, 21, 9, 5)
        info = self.model.evaluate(ts)
        assert info.session_phase == SessionPhase.PRE_OPEN
        assert not info.is_trading_allowed
        assert info.is_no_trade_window

    def test_market_open_phase(self):
        # Monday 09:18 IST (within initial 5-min noise window)
        ts = make_ist_timestamp(2026, 9, 21, 9, 18)
        info = self.model.evaluate(ts)
        assert info.session_phase == SessionPhase.MARKET_OPEN
        # 09:15-09:20 is configured no-trade window
        assert not info.is_trading_allowed
        assert info.is_no_trade_window
        assert info.minutes_from_open == 3.0

    def test_opening_range_phase(self):
        # Monday 09:30 IST
        ts = make_ist_timestamp(2026, 9, 21, 9, 30)
        info = self.model.evaluate(ts)
        assert info.session_phase == SessionPhase.OPENING_RANGE
        assert info.is_trading_allowed
        assert not info.is_no_trade_window
        assert info.minutes_from_open == 15.0

    def test_normal_intraday_phase(self):
        # Monday 11:30 IST
        ts = make_ist_timestamp(2026, 9, 21, 11, 30)
        info = self.model.evaluate(ts)
        assert info.session_phase == SessionPhase.NORMAL_INTRADAY
        assert info.is_trading_allowed
        assert not info.is_no_trade_window
        assert info.minutes_from_open == 135.0
        assert info.minutes_to_close == 240.0

    def test_late_session_phase(self):
        # Monday 15:00 IST
        ts = make_ist_timestamp(2026, 9, 21, 15, 0)
        info = self.model.evaluate(ts)
        assert info.session_phase == SessionPhase.LATE_SESSION
        assert info.is_trading_allowed
        assert not info.is_forced_square_off

    def test_forced_square_off_window(self):
        # Monday 15:20 IST
        ts = make_ist_timestamp(2026, 9, 21, 15, 20)
        info = self.model.evaluate(ts)
        assert info.session_phase == SessionPhase.FORCED_SQUARE_OFF
        assert not info.is_trading_allowed
        assert info.is_forced_square_off
        assert info.is_no_trade_window

    def test_market_closed_after_hours(self):
        # Monday 16:30 IST
        ts = make_ist_timestamp(2026, 9, 21, 16, 30)
        info = self.model.evaluate(ts)
        assert info.session_phase == SessionPhase.CLOSED
        assert not info.is_trading_allowed

    def test_weekend_handling(self):
        # 2026-09-20 is Sunday, 11:00 IST
        ts = make_ist_timestamp(2026, 9, 20, 11, 0)
        info = self.model.evaluate(ts)
        assert info.session_phase == SessionPhase.CLOSED
        assert not info.is_trading_allowed
        assert info.day_of_week == 6  # Sunday
