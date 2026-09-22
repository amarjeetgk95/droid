"""Historical Ingestion Job and Chunk domain models."""

from __future__ import annotations
from datetime import date, datetime, timezone
from typing import Optional, Dict, Any, List, Literal
from pydantic import BaseModel, Field

JobStatus = Literal["QUEUED", "RUNNING", "PARTIAL", "COMPLETED", "FAILED", "CANCELLED"]
ChunkStatus = Literal["PENDING", "DOWNLOADING", "COMPLETED", "FAILED", "RETRYING"]


class HistoricalDownloadChunk(BaseModel):
    """An individual slice of a larger date range query (e.g. 100-day window)."""
    chunk_id: str
    job_id: str
    chunk_index: int
    range_from: date
    range_to: date
    status: ChunkStatus = "PENDING"
    rows_fetched: int = 0
    retries: int = 0
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class HistoricalDownloadJob(BaseModel):
    """A user or scheduler initiated batch download job."""
    job_id: str
    dataset_id: str
    symbol: str
    timeframe: str = "1m"
    provider: str = "fyers"
    range_from: date
    range_to: date
    status: JobStatus = "QUEUED"
    progress_pct: float = 0.0
    total_chunks: int = 0
    completed_chunks: int = 0
    rows_downloaded: int = 0
    rows_valid: int = 0
    rows_rejected: int = 0
    retry_count: int = 0
    error_message: Optional[str] = None
    chunks: List[HistoricalDownloadChunk] = Field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
