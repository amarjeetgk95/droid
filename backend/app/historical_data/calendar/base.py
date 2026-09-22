"""Abstract base class for exchange calendars."""

from abc import ABC, abstractmethod
from datetime import date, time, datetime
from typing import List, Tuple, Optional


class MarketCalendar(ABC):
    """Defines the market calendar interface for trading day and session resolution."""

    @abstractmethod
    def is_trading_day(self, target_date: date) -> bool:
        """Check if target_date is a trading day on this exchange."""
        pass

    @abstractmethod
    def is_holiday(self, target_date: date) -> bool:
        """Check if target_date is an official exchange holiday."""
        pass

    @abstractmethod
    def is_special_session(self, target_date: date) -> bool:
        """Check if target_date has non-standard session hours (e.g. Muhurat, DR)."""
        pass

    @abstractmethod
    def get_session_intervals(self, target_date: date) -> List[Tuple[time, time]]:
        """Return list of (open_inclusive, close_exclusive) session times for the day."""
        pass

    @abstractmethod
    def get_expected_candles(self, target_date: date, timeframe: str) -> int:
        """Calculate the exact number of expected candles for a specific date and resolution.
        
        For example:
        - 1m on standard day: 375 candles (09:15 to 15:29 inclusive)
        - 1m on 1-hour Muhurat session: 60 candles
        - 1m on holiday/weekend: 0 candles
        """
        pass

    @abstractmethod
    def get_trading_days(self, start_date: date, end_date: date) -> List[date]:
        """Return sorted list of all trading dates between start_date and end_date inclusive."""
        pass
