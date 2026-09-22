"""Quality Report and Validation Gating domain models."""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Literal
from pydantic import BaseModel, Field
from app.historical_data.models.dataset import QualityStatus


class QualityGateResult(BaseModel):
    """Outcome of Tier 1 Hard-Gating checks."""
    hard_gates_passed: bool
    violations: List[str] = Field(default_factory=list)
    details: Dict[str, Any] = Field(default_factory=dict)


class DimensionalScores(BaseModel):
    """Tier 2 Dimensional Scores (0-100 scale)."""
    completeness_score: float = 100.0
    temporal_continuity_score: float = 100.0
    sanity_score: float = 100.0
    composite_score: float = 100.0


class HistoricalQualityReport(BaseModel):
    """Full quality assessment report generated post-ingestion."""
    report_id: str
    dataset_id: str
    version_id: Optional[str] = None
    quality_score: float = 100.0
    status: QualityStatus = "PASSED"
    hard_gates_passed: bool = True
    dimensional_scores: DimensionalScores = Field(default_factory=DimensionalScores)
    total_rows: int = 0
    valid_rows: int = 0
    invalid_rows: int = 0
    duplicate_rows: int = 0
    missing_candles: int = 0
    ohlc_violations: int = 0
    details: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
