from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field


class DetectedPatternModel(BaseModel):
    """Institutional price action pattern."""
    pattern_type: str
    name: str
    bias: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    confidence: float
    timeframe: str
    trigger_price: float
    invalidation_level: float
    target_level: float
    description: str


class HistoricalShiftPoint(BaseModel):
    """Daily historical shift point for options & futures positioning."""
    date: str
    pcr_oi: float
    pcr_volume: float
    max_pain_strike: float
    atm_iv: float
    futures_basis: float
    spot_close: float


class HistoricalShiftsResponse(BaseModel):
    """Multi-day shift progression for options sentiment and structure."""
    symbol: str
    shifts: list[HistoricalShiftPoint]


class DaySeasonality(BaseModel):
    """Day of week return and volatility behavior."""
    day_name: str
    avg_return_pct: float
    win_rate_pct: float
    avg_range_pts: float
    volatility_pct: float


class SeasonalityResponse(BaseModel):
    """Weekly seasonality breakdown for Indian indices."""
    symbol: str
    days: list[DaySeasonality]
    best_day_for_buyers: str
    best_day_for_sellers: str


class WatchlistItem(BaseModel):
    """Tracked asset in user watchlist with real-time indicators."""
    symbol: str
    display_name: str
    ltp: float
    change: float
    change_percent: float
    volume: int
    open_interest: int | None = None
    active_pattern: str | None = None
    regime_state: str | None = None


# ============================================================
# Pattern Outcomes (Historical Intelligence v2)
# ============================================================
class PatternOutcomeRecord(BaseModel):
    """Single pattern detection with outcome tracking."""
    id: str
    symbol: str
    pattern_type: str
    pattern_name: str
    bias: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    confidence: float
    timeframe: str
    trigger_price: float
    invalidation_level: float
    target_level: float
    detection_timestamp: datetime
    regime_state: Optional[str] = None
    outcome_1d: Optional[float] = None
    outcome_3d: Optional[float] = None
    outcome_5d: Optional[float] = None
    hit_target_before_invalidation: Optional[bool] = None
    outcome_labeled_at: Optional[datetime] = None
    outcome_source: Optional[str] = None


class PatternHitRate(BaseModel):
    """Aggregated hit-rate statistics per pattern."""
    symbol: str
    pattern_type: str
    pattern_name: str
    bias: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    timeframe: str
    sample_count: int
    avg_return_1d: Optional[float] = None
    stddev_return_1d: Optional[float] = None
    avg_return_3d: Optional[float] = None
    avg_return_5d: Optional[float] = None
    hit_target_rate: Optional[float] = None
    directional_accuracy: Optional[float] = None
    first_detection: Optional[datetime] = None
    last_detection: Optional[datetime] = None


class PatternHitRateResponse(BaseModel):
    """Hit-rate response for a symbol across all patterns."""
    symbol: str
    hit_rates: list[PatternHitRate]
    total_patterns_tracked: int
    total_labeled_outcomes: int


class PatternOutcomesRequest(BaseModel):
    """Request to label outcomes for unlabeled patterns (on-demand)."""
    symbol: str
    pattern_types: Optional[list[str]] = None
    timeframe: Optional[str] = None
