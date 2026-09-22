"""Data Gap Ledger domain models."""

from __future__ import annotations
from datetime import date, datetime, timezone
from typing import Optional, Dict, Any, List, Literal
from pydantic import BaseModel, Field

GapStatus = Literal[
    "OPEN",
    "REPAIRING",
    "RESOLVED",
    "UNREPAIRABLE_UPSTREAM_OMISSION",
    "EXCHANGE_HALT_VERIFIED",
]


class DataGap(BaseModel):
    """Represents missing trading session bars detected by the Quality Engine."""
    gap_id: str
    dataset_id: str
    trading_date: date
    expected_candles: int
    actual_candles: int
    missing_candles: int
    first_missing_ts: Optional[datetime] = None
    last_missing_ts: Optional[datetime] = None
    status: GapStatus = "OPEN"
    repair_attempts: int = 0
    last_repair_attempt: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
