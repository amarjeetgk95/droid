from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class CandleRecord(BaseModel):
    """Normalized time-series candle record for TimescaleDB/Hypertable storage."""
    timestamp: datetime
    symbol: str
    timeframe: str = "1m"
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: float | None = None
    open_interest: int | None = None


class HistoricalQuery(BaseModel):
    """Query parameters for historical time-series retrieval."""
    symbol: str
    timeframe: str = "5m"
    start_time: datetime | None = None
    end_time: datetime | None = None
    limit: int = 500


class SnapshotPayload(BaseModel):
    """Complete market state snapshot for persistence and warm restart."""
    timestamp: datetime
    version: str = "1.0"
    quotes: list[dict[str, Any]] = Field(default_factory=list)
    cards: list[dict[str, Any]] = Field(default_factory=list)
    status: dict[str, Any] | None = None
    breadth: dict[str, Any] | None = None
    subscriptions: list[str] = Field(default_factory=list)
