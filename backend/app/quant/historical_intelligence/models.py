"""
Domain Models for Historical Intelligence Engine — §5, §17, §25, §26, §32
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Literal, Any


# ── Versioning Metadata (§32) ─────────────────────────────────────────
ENGINE_VERSION = "2.1.0"
FEATURE_VERSION = "1.2.0"
SIMILARITY_VERSION = "1.4.0"
OUTCOME_VERSION = "1.3.0"
SR_VERSION = "1.2.0"


class SessionPhase(str, Enum):
    PRE_MARKET = "PRE_MARKET"
    MARKET_OPEN = "MARKET_OPEN"          # 09:15 - 09:45
    EARLY_SESSION = "EARLY_SESSION"      # 09:45 - 11:30
    MID_SESSION = "MID_SESSION"          # 11:30 - 13:30
    AFTERNOON = "AFTERNOON"              # 13:30 - 15:00
    CLOSING_PHASE = "CLOSING_PHASE"      # 15:00 - 15:30
    POST_MARKET = "POST_MARKET"
    PERPETUAL = "PERPETUAL"              # 24x7 crypto


class MarketRegime(str, Enum):
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    RANGING = "RANGING"
    BREAKOUT = "BREAKOUT"
    MEAN_REVERSION = "MEAN_REVERSION"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    VOLATILITY_EXPANSION = "VOLATILITY_EXPANSION"
    VOLATILITY_COMPRESSION = "VOLATILITY_COMPRESSION"


@dataclass(slots=True, frozen=True)
class CandleData:
    timestamp_utc: int      # Milliseconds UTC
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str = "primary"


@dataclass(slots=True)
class NormalizedFeatures:
    """Normalized structural features for similarity matching (§8, §9)."""
    # Price Returns (Normalized to baseline %)
    normalized_returns: list[float]
    log_returns: list[float]
    total_return_pct: float
    high_low_range_pct: float
    
    # Candle Structure
    avg_body_pct: float
    avg_upper_wick_pct: float
    avg_lower_wick_pct: float
    body_to_range_ratio: float
    consecutive_bullish: int
    consecutive_bearish: int
    
    # Volatility
    atr: float
    atr_percentile: float
    volatility_zscore: float
    is_expanding: bool
    is_compressing: bool
    
    # Trend
    ema_slope_short: float
    ema_slope_medium: float
    trend_direction: Literal["UP", "DOWN", "FLAT"]
    trend_strength: float   # 0.0 - 1.0
    
    # Volume
    relative_volume: float
    volume_zscore: float
    volume_trend: float
    
    # Location
    dist_from_vwap_pct: float
    dist_from_day_high_pct: float
    dist_from_day_low_pct: float
    dist_from_pdc_pct: float


@dataclass(slots=True)
class HistoricalAnalogMatch:
    """Historical matching pattern occurrence (§14, §17)."""
    symbol: str
    timeframe: str
    pattern_start_ts: int
    pattern_end_ts: int
    matched_regime: MarketRegime
    session_phase: SessionPhase
    similarity_score: float             # 0.0 - 1.0
    price_similarity: float
    shape_similarity: float
    volatility_similarity: float
    volume_similarity: float
    trend_similarity: float
    
    # Forward Outcomes (evaluated from T+1 to T+H with NO lookahead)
    forward_candles_count: int
    forward_returns: list[float]        # % price evolution
    mfe_pct: float                      # Maximum Favorable Excursion %
    mae_pct: float                      # Maximum Adverse Excursion %
    target_hit: bool
    stop_hit: bool
    time_to_target_bars: int | None
    session_end_return_pct: float


@dataclass(slots=True)
class AnalogAnalyticsSummary:
    """Aggregated empirical distribution of historical analogs (§17, §19, §20)."""
    symbol: str
    timeframe: str
    pattern_window_size: int
    lookback_days: int
    total_candidates_scanned: int
    valid_analogs_found: int
    sample_confidence: Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT_SAMPLE"]
    
    # Probabilities
    raw_bullish_prob: float
    raw_bearish_prob: float
    raw_neutral_prob: float
    weighted_bullish_prob: float
    weighted_bearish_prob: float
    target_hit_probability: float
    stop_hit_probability: float
    
    # Empirical Targets & MFE Distribution
    median_mfe_pct: float
    mean_mfe_pct: float
    p25_mfe_pct: float
    p75_mfe_pct: float
    p90_mfe_pct: float
    expected_target_price: float | None
    
    # Empirical Stop Loss & MAE Distribution
    median_mae_pct: float
    p75_mae_pct: float
    p90_mae_pct: float
    max_mae_pct: float
    empirical_stop_price: float | None
    
    # Timing & Risk/Reward
    avg_time_to_target_bars: float | None
    empirical_risk_reward: float
    
    # Composite Score
    historical_intelligence_score: float  # 0 - 100
    top_analogs: list[HistoricalAnalogMatch] = field(default_factory=list)


@dataclass(slots=True)
class SupportResistanceZone:
    """Empirical S/R zone with volume & OI weighting (§26, §27, §28)."""
    zone_id: str
    zone_type: Literal["SUPPORT", "RESISTANCE", "PIVOT"]
    zone_center: float
    zone_low: float
    zone_high: float
    zone_width: float
    touch_count: int
    volume_strength: float      # 0.0 - 1.0 (from Volume Profile HVN/POC)
    oi_strength: float          # 0.0 - 1.0 (from Options Call/Put Wall)
    recency_score: float        # 0.0 - 1.0
    strength_score: float       # 0 - 100
    is_poc: bool = False
    is_oi_wall: bool = False
    last_tested_ts: int | None = None
