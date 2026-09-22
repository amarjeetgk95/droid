"""Dataset and Version Domain Models with Pipeline Lineage and Methodology Events."""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Literal
from pydantic import BaseModel, Field

DatasetStatus = Literal["INITIALIZED", "DOWNLOADING", "READY", "DEGRADED", "ERROR"]
QualityStatus = Literal["PASSED", "DEGRADED", "POISONED"]


class LineageMetadata(BaseModel):
    """Deep pipeline provenance metadata to guarantee auditability and prevent silent drift."""
    engine_version: str = "1.0.0"
    provider_id: str = "fyers"
    provider_api_version: str = "v3"
    calendar_version: str = "2026.1"
    normalizer_version: str = "1.0.0"
    validation_ruleset_version: str = "1.0.0"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MethodologyEvent(BaseModel):
    """Historical methodology or market microstructure shift (lot size, rebalance)."""
    event_date: str
    event_type: Literal["LOT_SIZE_CHANGE", "INDEX_REBALANCE", "EXPIRY_DAY_CHANGE", "TRADING_HOURS_CHANGE"]
    description: str
    details: Dict[str, Any] = Field(default_factory=dict)


class HistoricalDatasetVersion(BaseModel):
    """Immutable, versioned snapshot of a historical dataset."""
    version_id: str
    dataset_id: str
    version_tag: str
    start_time: datetime
    end_time: datetime
    row_count: int = 0
    checksum_sha256: str
    quality_score: float = 0.0
    quality_status: QualityStatus = "PASSED"
    parquet_path: str
    lineage: LineageMetadata = Field(default_factory=LineageMetadata)
    methodology_events: List[MethodologyEvent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class HistoricalDataset(BaseModel):
    """Dataset catalog entry defining a managed instrument and resolution."""
    id: str
    symbol: str
    exchange: str
    asset_type: str = "INDEX"
    timeframe: str = "1m"
    provider: str = "fyers"
    status: DatasetStatus = "INITIALIZED"
    current_version_id: Optional[str] = None
    earliest_available_ts: Optional[datetime] = None
    latest_available_ts: Optional[datetime] = None
    total_candles: int = 0
    latest_quality_score: float = 0.0
    storage_bytes: int = 0
    parquet_relative_path: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
