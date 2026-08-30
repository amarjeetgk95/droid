from typing import Literal
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
