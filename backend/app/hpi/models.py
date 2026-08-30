"""HPI Pydantic schemas — selection, policies, estimates, deletion, coverage."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4
from pydantic import BaseModel, Field, field_validator

CoverageStatus = Literal["FULL", "PARTIAL", "MISSING", "DISABLED", "EMPTY"]
BudgetStatus = Literal["WITHIN_TARGET", "WARNING", "EXCEEDS_HARD"]
RangeType = Literal["last_30_days", "last_3_months", "older_than_6_months", "custom", "all_time"]


# ---------------------------------------------------------------------------
# §2 — Derivative selection
# ---------------------------------------------------------------------------
class DerivativeSelectionEntry(BaseModel):
    symbol: str
    enabled: bool = False
    data_categories: list[str] = Field(default_factory=list)

    @field_validator("symbol")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper().strip()


class DerivativeSelectionState(BaseModel):
    entries: list[DerivativeSelectionEntry] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# §11 — Retention policy
# ---------------------------------------------------------------------------
class RetentionPolicy(BaseModel):
    policy_id: str = Field(default_factory=lambda: uuid4().hex[:16])
    instrument: str
    derivative_category: str
    feature_group: str
    start_date: datetime | None = None
    end_date: datetime | None = None
    retention_days: int = Field(default=365, ge=1, le=3650)
    sampling_interval: str = "5m"
    enabled: bool = True
    auto_delete_enabled: bool = False
    protected: bool = False
    storage_priority: int = Field(default=3, ge=1, le=5)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RetentionPolicyUpdate(BaseModel):
    """Partial policy update — every field optional."""
    start_date: datetime | None = None
    end_date: datetime | None = None
    retention_days: int | None = Field(default=None, ge=1, le=3650)
    sampling_interval: str | None = None
    enabled: bool | None = None
    auto_delete_enabled: bool | None = None
    protected: bool | None = None
    storage_priority: int | None = Field(default=None, ge=1, le=5)


# ---------------------------------------------------------------------------
# §10 — Storage estimation
# ---------------------------------------------------------------------------
class StorageEstimate(BaseModel):
    current_storage_mb: float
    requested_addition_mb: float
    projected_storage_mb: float
    status: BudgetStatus
    blocked: bool = False
    alternatives: list[str] = Field(default_factory=list)
    breakdown: list["CategoryEstimate"] = Field(default_factory=list)


class CategoryEstimate(BaseModel):
    symbol: str
    category: str
    label: str
    estimated_records: int
    estimated_mb: float
    sampling_interval: str


# ---------------------------------------------------------------------------
# §16 — Import workflow
# ---------------------------------------------------------------------------
class ImportRequest(BaseModel):
    symbol: str
    categories: list[str] = Field(default_factory=list)
    start_date: datetime | None = None
    end_date: datetime | None = None
    retention_days: int | None = Field(default=None, ge=1, le=3650)
    sampling_interval: str = "5m"
    estimate_only: bool = False

    @field_validator("symbol")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper().strip()


class ImportPreview(StorageEstimate):
    symbol: str
    sampling_interval: str
    period_start: datetime
    period_end: datetime
    warnings: list[str] = Field(default_factory=list)


class ImportResult(BaseModel):
    symbol: str
    imported_categories: list[str]
    records_imported: int
    storage_added_mb: float
    total_storage_mb: float
    status: BudgetStatus
    sampling_interval: str
    period_start: datetime
    period_end: datetime


# ---------------------------------------------------------------------------
# §5 — Derivative data management card
# ---------------------------------------------------------------------------
class CategoryStats(BaseModel):
    category: str
    label: str
    enabled: bool
    records: int
    storage_mb: float
    oldest: datetime | None = None
    newest: datetime | None = None
    auto_delete_enabled: bool
    protected: bool
    retention_days: int | None = None


class DatasetCard(BaseModel):
    symbol: str
    display_name: str
    enabled: bool
    data_categories_enabled: list[str]
    historical_period_months: float | None = None
    sampling_interval: str | None = None
    records_stored: int
    storage_used_mb: float
    oldest_record: datetime | None = None
    newest_record: datetime | None = None
    protected: bool
    auto_delete_status: str  # "ON" | "OFF" | "PARTIAL"
    category_stats: list[CategoryStats] = Field(default_factory=list)


class StorageReport(BaseModel):
    current_storage_mb: float
    target_mb: float
    warning_mb: float
    hard_ceiling_mb: float
    status: BudgetStatus
    seeded: bool = False
    datasets: list[DatasetCard]


# ---------------------------------------------------------------------------
# §6 / §7 — Deletion
# ---------------------------------------------------------------------------
class DeleteRequest(BaseModel):
    symbol: str
    categories: list[str]
    range_type: RangeType = "custom"
    start_date: datetime | None = None
    end_date: datetime | None = None
    reason: str | None = None
    allow_protected: bool = False  # explicit opt-in required to delete protected data

    @field_validator("symbol")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper().strip()


class CategoryDeletePreview(BaseModel):
    category: str
    label: str
    records: int
    storage_mb: float


class DeletePreview(BaseModel):
    symbol: str
    categories: list[str]
    range_type: RangeType
    range_start: datetime
    range_end: datetime
    total_records: int
    total_storage_mb: float
    per_category: list[CategoryDeletePreview]
    analytical_impact: list[str]
    price_technical_impact: str
    protected_categories: list[str]
    confirmation_token: str


class DeleteConfirmRequest(BaseModel):
    confirmation_token: str
    reason: str | None = None


class DeleteResult(BaseModel):
    deleted: bool
    audit_ids: list[str]
    records_deleted: int
    storage_released_mb: float


# ---------------------------------------------------------------------------
# §14 — Deletion audit
# ---------------------------------------------------------------------------
class DeletionAuditEntry(BaseModel):
    deletion_id: str = Field(default_factory=lambda: uuid4().hex)
    user_id: str = "system"
    derivative: str
    dataset: str
    start_date: datetime
    end_date: datetime
    records_deleted: int
    storage_released_mb: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reason: str


# ---------------------------------------------------------------------------
# §9 / §15 — Coverage & engine output
# ---------------------------------------------------------------------------
class DatasetCoverage(BaseModel):
    category: str
    label: str
    status: CoverageStatus
    coverage_months: float
    records: int
    oldest: datetime | None = None
    newest: datetime | None = None
    deleted_ranges: list[list[str]] = Field(default_factory=list)


class CoverageReport(BaseModel):
    symbol: str
    derivative_enabled: bool
    overall: CoverageStatus
    historical_coverage_months: float
    datasets: list[DatasetCoverage]
    missing_datasets: list[str]
    deleted_ranges: list[str]


class HPISetup(BaseModel):
    signature: str
    similar_count: int
    bullish_pct: float
    neutral_pct: float
    bearish_pct: float
    avg_forward_move_pct: float
    similarity: float


class HPIAnalysis(BaseModel):
    symbol: str
    timeframe: str
    historical_coverage_months: float
    historical_coverage_label: str
    similar_setups: int
    confidence: float
    warnings: list[str]
    derivative_coverage: CoverageStatus
    missing_dataset: str | None = None
    coverage_report: CoverageReport
    setups: list[HPISetup]
    note: str | None = None
