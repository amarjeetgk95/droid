"""Abstract Base Class for Historical Data Providers."""

from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Optional, Dict, Any, List, Tuple
import polars as pl


class HistoricalDataProvider(ABC):
    """Abstract interface for historical market data acquisition."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique identifier for this provider (e.g. 'fyers')."""
        pass

    @abstractmethod
    async def fetch_candles(
        self,
        symbol: str,
        timeframe: str,
        start_date: date,
        end_date: date,
    ) -> pl.DataFrame:
        """Fetch and normalize historical candles for symbol, timeframe and date range.
        
        Must return a Polars DataFrame conforming to CANDLE_POLARS_SCHEMA.
        """
        pass

    @abstractmethod
    async def get_available_range(
        self,
        symbol: str,
        timeframe: str,
    ) -> Tuple[Optional[date], Optional[date]]:
        """Probe the earliest and latest available date for this instrument and resolution."""
        pass

    @abstractmethod
    def resolve_provider_symbol(self, canonical_symbol: str) -> str:
        """Translate canonical platform symbol (e.g. 'SENSEX') to provider symbol ('BSE:SENSEX-INDEX')."""
        pass
