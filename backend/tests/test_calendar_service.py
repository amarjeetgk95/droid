from datetime import date
from app.services.calendar_service import ExchangeCalendarService


class TestCalendarService:
    def setup_method(self):
        self.cal = ExchangeCalendarService()

    def test_weekend_not_trading_day(self):
        # 2026-08-29 is Saturday, 2026-08-30 is Sunday
        assert not self.cal.is_trading_day(date(2026, 8, 29))
        assert not self.cal.is_trading_day(date(2026, 8, 30))

    def test_official_holiday(self):
        # Republic Day 2026-01-26 is Monday
        republic_day = date(2026, 1, 26)
        assert self.cal.is_holiday(republic_day)
        assert not self.cal.is_trading_day(republic_day)
        assert self.cal.get_holiday_name(republic_day) == "Republic Day"

    def test_regular_trading_day(self):
        # 2026-08-28 is Friday
        friday = date(2026, 8, 28)
        assert not self.cal.is_holiday(friday)
        assert not self.cal.is_weekend(friday)
        assert self.cal.is_trading_day(friday)

    def test_previous_and_next_trading_day(self):
        # From Monday 2026-01-26 (Holiday), previous trading day is Friday 2026-01-23
        prev_day = self.cal.previous_trading_day(date(2026, 1, 26))
        assert prev_day == date(2026, 1, 23)

        # Next trading day after Friday 2026-01-23 when Monday is Holiday is Tuesday 2026-01-27
        next_day = self.cal.next_trading_day(date(2026, 1, 23))
        assert next_day == date(2026, 1, 27)

    def test_expiry_adjustment_on_holiday(self):
        # If an expiry falls on a holiday (e.g. 2024-08-15 Thursday Independence Day)
        # It must adjust backwards to Wednesday 2024-08-14
        adjusted = self.cal.adjust_expiry_if_holiday(date(2024, 8, 15))
        assert adjusted == date(2024, 8, 14)
        assert self.cal.is_trading_day(adjusted)

    def test_session_info(self):
        friday = date(2026, 8, 28)
        info = self.cal.get_session_info(friday)
        assert info.is_trading_day is True
        assert info.is_holiday is False
        assert info.market_open is not None
        assert info.market_close is not None
        assert info.market_open.hour == 9 and info.market_open.minute == 15
        assert info.market_close.hour == 15 and info.market_close.minute == 30
