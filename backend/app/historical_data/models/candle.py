"""Canonical Normalized Candle Schema and Polars mappings."""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
import polars as pl

# Canonical Polars Schema for Historical Parquet Storage
CANDLE_POLARS_SCHEMA = {
    "timestamp": pl.Datetime("ms", "UTC"),
    "symbol": pl.Utf8,
    "exchange": pl.Utf8,
    "asset_type": pl.Utf8,
    "timeframe": pl.Utf8,
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Float64,
    "provider": pl.Utf8,
    "ingestion_job_id": pl.Utf8,
    "data_version": pl.Utf8,
}


class NormalizedHistoricalCandle(BaseModel):
    """Canonical model for validated historical candles."""

    timestamp: datetime = Field(..., description="Start of bar interval in UTC")
    symbol: str
    exchange: str
    asset_type: str = "INDEX"  # INDEX, EQUITY, FUTURES, OPTIONS
    timeframe: str = "1m"
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    provider: str = "fyers"
    ingestion_job_id: str = ""
    data_version: str = "v1"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "exchange": self.exchange,
            "asset_type": self.asset_type,
            "timeframe": self.timeframe,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "provider": self.provider,
            "ingestion_job_id": self.ingestion_job_id,
            "data_version": self.data_version,
        }
