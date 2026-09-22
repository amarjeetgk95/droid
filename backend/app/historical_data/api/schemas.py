"""Pydantic Request and Response Schemas for the Historical Data API."""

from __future__ import annotations
from datetime import date, datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class DownloadRequest(BaseModel):
    """Payload to trigger an asynchronous download job."""
    symbol: str = Field(..., json_schema_extra={"example": "SENSEX"})
    timeframe: str = Field("1m", json_schema_extra={"example": "1m"})
    range_from: date = Field(..., json_schema_extra={"example": "2025-09-22"})
    range_to: date = Field(..., json_schema_extra={"example": "2026-09-22"})
    force_refresh: bool = False


class RepairRequest(BaseModel):
    """Payload to initiate a gap repair."""
    gap_id: str


class DeriveRequest(BaseModel):
    """Payload to derive higher timeframes from an existing 1m dataset."""
    symbol: str = Field(..., json_schema_extra={"example": "SENSEX"})
    source_timeframe: str = Field("1m", json_schema_extra={"example": "1m"})
    target_timeframes: Optional[List[str]] = None


class CandlePageResponse(BaseModel):
    """Paginated candles response for Candle Inspector."""
    symbol: str
    timeframe: str
    version: str
    page: int
    page_size: int
    total_records: int
    total_pages: int
    candles: List[Dict[str, Any]]
