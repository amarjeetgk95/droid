from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from typing import NamedTuple

IST = ZoneInfo("Asia/Kolkata")


class TradingSessionInfo(NamedTuple):
    is_trading_day: bool
    is_holiday: bool
    is_weekend: bool
    holiday_name: str | None
    is_special_session: bool
    market_open: datetime | None
    market_close: datetime | None


class ExchangeCalendarService:
    """Official NSE Exchange Calendar Service.
    
    Adheres strictly to Section 17 of the platform spec.
    Handles official exchange holidays, market hours, special trading sessions,
    and automatic expiry adjustment rules.
    """

    # Official NSE Trading Holidays (Sample covering 2024-2027)
    NSE_HOLIDAYS: dict[date, str] = {
        # 2024
        date(2024, 1, 22): "Special Holiday (Ayodhya Pran Pratishtha)",
        date(2024, 1, 26): "Republic Day",
        date(2024, 3, 8): "Maha Shivratri",
        date(2024, 3, 25): "Holi",
        date(2024, 3, 29): "Good Friday",
        date(2024, 4, 11): "Id-Ul-Fitr",
        date(2024, 4, 17): "Ram Navami",
        date(2024, 5, 1): "Maharashtra Day",
        date(2024, 5, 20): "General Elections",
        date(2024, 6, 17): "Bakri Id",
        date(2024, 7, 17): "Muharram",
        date(2024, 8, 15): "Independence Day",
        date(2024, 10, 2): "Mahatma Gandhi Jayanti",
        date(2024, 11, 1): "Diwali Laxmi Pujan",
        date(2024, 11, 15): "Gurunanak Jayanti",
        date(2024, 11, 20): "Maharashtra Assembly Elections",
        date(2024, 12, 25): "Christmas",
        # 2025
        date(2025, 2, 26): "Maha Shivratri",
        date(2025, 3, 14): "Holi",
        date(2025, 3, 31): "Id-Ul-Fitr",
        date(2025, 4, 10): "Mahavir Jayanti",
        date(2025, 4, 14): "Dr. Baba Saheb Ambedkar Jayanti",
        date(2025, 4, 18): "Good Friday",
        date(2025, 5, 1): "Maharashtra Day",
        date(2025, 8, 15): "Independence Day",
        date(2025, 8, 27): "Ganesh Chaturthi",
        date(2025, 10, 2): "Mahatma Gandhi Jayanti / Dussehra",
        date(2025, 10, 21): "Diwali Laxmi Pujan",
        date(2025, 10, 22): "Diwali Balipratipada",
        date(2025, 11, 5): "Gurunanak Jayanti",
        date(2025, 12, 25): "Christmas",
        # 2026
        date(2026, 1, 26): "Republic Day",
        date(2026, 3, 3): "Holi",
        date(2026, 3, 20): "Id-Ul-Fitr",
        date(2026, 4, 3): "Good Friday",
        date(2026, 4, 14): "Dr. Baba Saheb Ambedkar Jayanti",
        date(2026, 5, 1): "Maharashtra Day",
        date(2026, 8, 15): "Independence Day",
        date(2026, 10, 2): "Mahatma Gandhi Jayanti",
        date(2026, 10, 20): "Dussehra",
        date(2026, 11, 8): "Diwali Laxmi Pujan",
        date(2026, 11, 24): "Gurunanak Jayanti",
        date(2026, 12, 25): "Christmas",
        # 2027
        date(2027, 1, 26): "Republic Day",
        date(2027, 3, 22): "Holi",
        date(2027, 3, 26): "Good Friday",
        date(2027, 4, 14): "Dr. Ambedkar Jayanti",
        date(2027, 5, 1): "Maharashtra Day",
        date(2027, 8, 15): "Independence Day",
        date(2027, 10, 2): "Mahatma Gandhi Jayanti",
        date(2027, 12, 25): "Christmas",
    }

    # Special trading sessions (e.g. Diwali Muhurat Trading: 18:15 to 19:15)
    SPECIAL_SESSIONS: dict[date, tuple[time, time, str]] = {
        date(2024, 11, 1): (time(18, 0), time(19, 0), "Diwali Muhurat Trading"),
        date(2025, 10, 21): (time(18, 15), time(19, 15), "Diwali Muhurat Trading"),
        date(2026, 11, 8): (time(18, 15), time(19, 15), "Diwali Muhurat Trading"),
    }

    REGULAR_OPEN = time(9, 15)
    REGULAR_CLOSE = time(15, 30)

    def is_weekend(self, target_date: date) -> bool:
        """Check if date falls on Saturday (5) or Sunday (6)."""
        return target_date.weekday() >= 5

    def is_holiday(self, target_date: date) -> bool:
        """Check if date is an official exchange holiday."""
        # Note: If it's a special session day (like Muhurat), it's treated as a special trading session
        if target_date in self.SPECIAL_SESSIONS:
            return False
        return target_date in self.NSE_HOLIDAYS

    def is_trading_day(self, target_date: date) -> bool:
        """Determine whether the exchange is open for trading on target_date."""
        if target_date in self.SPECIAL_SESSIONS:
            return True
        if self.is_weekend(target_date):
            return False
        return not self.is_holiday(target_date)

    def get_holiday_name(self, target_date: date) -> str | None:
        """Get the holiday description if target_date is a holiday."""
        return self.NSE_HOLIDAYS.get(target_date)

    def get_session_info(self, target_date: date) -> TradingSessionInfo:
        """Get complete trading session information for a given date."""
        is_wknd = self.is_weekend(target_date)
        is_hol = self.is_holiday(target_date)
        hol_name = self.get_holiday_name(target_date)
        is_special = target_date in self.SPECIAL_SESSIONS
        is_trade = self.is_trading_day(target_date)

        if not is_trade:
            return TradingSessionInfo(
                is_trading_day=False,
                is_holiday=is_hol,
                is_weekend=is_wknd,
                holiday_name=hol_name,
                is_special_session=False,
                market_open=None,
                market_close=None,
            )

        if is_special:
            open_t, close_t, name = self.SPECIAL_SESSIONS[target_date]
            mkt_open = datetime.combine(target_date, open_t, tzinfo=IST)
            mkt_close = datetime.combine(target_date, close_t, tzinfo=IST)
            return TradingSessionInfo(
                is_trading_day=True,
                is_holiday=False,
                is_weekend=is_wknd,
                holiday_name=name,
                is_special_session=True,
                market_open=mkt_open,
                market_close=mkt_close,
            )

        mkt_open = datetime.combine(target_date, self.REGULAR_OPEN, tzinfo=IST)
        mkt_close = datetime.combine(target_date, self.REGULAR_CLOSE, tzinfo=IST)
        return TradingSessionInfo(
            is_trading_day=True,
            is_holiday=False,
            is_weekend=is_wknd,
            holiday_name=None,
            is_special_session=False,
            market_open=mkt_open,
            market_close=mkt_close,
        )

    def previous_trading_day(self, target_date: date) -> date:
        """Find the preceding valid exchange trading day."""
        curr = target_date - timedelta(days=1)
        while not self.is_trading_day(curr):
            curr -= timedelta(days=1)
        return curr

    def next_trading_day(self, target_date: date) -> date:
        """Find the succeeding valid exchange trading day."""
        curr = target_date + timedelta(days=1)
        while not self.is_trading_day(curr):
            curr += timedelta(days=1)
        return curr

    def adjust_expiry_if_holiday(self, expiry_date: date) -> date:
        """Adjust contract expiry date backwards if scheduled expiry falls on holiday/weekend.
        
        NSE standard rule: If expiry day is a holiday, the contract expires on the
        immediately preceding trading day.
        """
        curr = expiry_date
        while not self.is_trading_day(curr):
            curr -= timedelta(days=1)
        return curr

    def is_market_open_now(self) -> bool:
        """Check if NSE is currently in trading hours (IST 9:15-15:30 on trading day)."""
        now_ist = datetime.now(IST)
        today = now_ist.date()
        if not self.is_trading_day(today):
            return False
        info = self.get_session_info(today)
        if not info.market_open or not info.market_close:
            return False
        return info.market_open <= now_ist <= info.market_close


calendar_service = ExchangeCalendarService()
