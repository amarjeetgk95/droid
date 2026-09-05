"""
Canonical Domain Schemas & Contracts for Historical Intelligence Engine — §§4, 5, 10, 11, 20, 21, 25, 40
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


# ── Enumerations ────────────────────────────────────────────────────────
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
    TRENDING_BULLISH = "TRENDING_BULLISH"
    TRENDING_BEARISH = "TRENDING_BEARISH"
    SIDEWAYS = "SIDEWAYS"
    BREAKOUT = "BREAKOUT"
    BREAKDOWN = "BREAKDOWN"
    UNKNOWN = "UNKNOWN"


class VolatilityRegime(str, Enum):
    LOW_VOLATILITY = "LOW_VOLATILITY"
    NORMAL_VOLATILITY = "NORMAL_VOLATILITY"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    EXTREME_VOLATILITY = "EXTREME_VOLATILITY"


class VixBucket(str, Enum):
    SUB_12 = "SUB_12"
    B_12_15 = "12_15"
    B_15_18 = "15_18"
    B_18_22 = "18_22"
    ABOVE_22 = "ABOVE_22"


class HIEStatus(str, Enum):
    READY = "READY"
    STALE = "STALE"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
    NO_MATCH = "NO_MATCH"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class IndexLifecycleState(str, Enum):
    BUILDING = "BUILDING"
    VALIDATING = "VALIDATING"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    REBUILDING = "REBUILDING"
    RETIRED = "RETIRED"


class SampleReliability(str, Enum):
    INSUFFICIENT = "INSUFFICIENT"        # < 10
    LOW_CONFIDENCE = "LOW_CONFIDENCE"    # 10–24
    MODERATE = "MODERATE"                # 25–49
    GOOD = "GOOD"                        # 50–99
    HIGH_SAMPLE = "HIGH_SAMPLE"          # 100+


# ── Candle Representation ──────────────────────────────────────────────
class CandleData(BaseModel):
    timestamp_utc: int  # Milliseconds UTC
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str = "primary"


# ── Feature Vector Families (§5) ───────────────────────────────────────
class PriceFeatures(BaseModel):
    returns: float = 0.0
    log_returns: float = 0.0
    gap: float = 0.0
    acceleration: float = 0.0
    vwap_distance: float = 0.0


class CandleFeatures(BaseModel):
    range_pts: float = 0.0
    body: float = 0.0
    upper_wick: float = 0.0
    lower_wick: float = 0.0
    body_to_range: float = 0.0
    close_location: float = 0.5  # 0.0 = low, 1.0 = high
    compression: float = 0.0


class StructureFeatures(BaseModel):
    swing_high: float = 0.0
    swing_low: float = 0.0
    is_hh: bool = False
    is_hl: bool = False
    is_lh: bool = False
    is_ll: bool = False
    consolidation: bool = False
    breakout_distance: float = 0.0
    retest_state: str = "NONE"   # NONE, RETESTING_SUPPORT, RETESTING_RESISTANCE


class TrendFeatures(BaseModel):
    ema_short: float = 0.0
    ema_medium: float = 0.0
    ema_slope: float = 0.0
    sma: float = 0.0
    slope: float = 0.0
    vwap: float = 0.0
    adx: float = 20.0
    rsi: float = 50.0
    macd: float = 0.0
    momentum_accel: float = 0.0


class VolumeVolFeatures(BaseModel):
    relative_volume: float = 1.0
    volume_percentile: float = 50.0
    volume_acceleration: float = 0.0
    atr: float = 1.0
    realized_volatility: float = 15.0
    vix: float = 14.0
    iv: float = 15.0
    iv_percentile: float = 50.0


class FuturesFeatures(BaseModel):
    basis: float = 0.0
    oi: float = 0.0
    oi_change: float = 0.0
    price_oi_divergence: float = 0.0
    buildup: str = "LONG_BUILDUP"  # LONG_BUILDUP, SHORT_BUILDUP, LONG_UNWINDING, SHORT_COVERING


class OptionsFeatures(BaseModel):
    ce_oi: float = 0.0
    pe_oi: float = 0.0
    pcr_oi: float = 1.0
    pcr_volume: float = 1.0
    atm_iv: float = 15.0
    iv_skew: float = 0.0
    atm_pressure: float = 0.0
    liquidity_score: float = 1.0


class MarketContextFeatures(BaseModel):
    breadth: float = 0.0
    market_liquidity: float = 1.0
    distance_to_support: float = 0.0
    distance_to_resistance: float = 0.0
    session_phase: SessionPhase = SessionPhase.MID_SESSION
    cross_market_state: str = "NEUTRAL"
    data_quality_score: float = 1.0


class CanonicalFeatureVector(BaseModel):
    """Unified Canonical Feature Vector (§5)."""
    price: PriceFeatures = Field(default_factory=PriceFeatures)
    candle: CandleFeatures = Field(default_factory=CandleFeatures)
    structure: StructureFeatures = Field(default_factory=StructureFeatures)
    trend: TrendFeatures = Field(default_factory=TrendFeatures)
    volume_vol: VolumeVolFeatures = Field(default_factory=VolumeVolFeatures)
    futures: FuturesFeatures = Field(default_factory=FuturesFeatures)
    options: OptionsFeatures = Field(default_factory=OptionsFeatures)
    market_context: MarketContextFeatures = Field(default_factory=MarketContextFeatures)

    def to_flat_dict(self) -> dict[str, float]:
        flat: dict[str, float] = {}
        for fam_name in ["price", "candle", "structure", "trend", "volume_vol", "futures", "options", "market_context"]:
            fam = getattr(self, fam_name)
            for k, v in fam.model_dump().items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    flat[f"{fam_name}_{k}"] = float(v)
                elif isinstance(v, bool):
                    flat[f"{fam_name}_{k}"] = 1.0 if v else 0.0
        return flat


class NormalizedFeatureVector(BaseModel):
    """Normalized feature values ready for distance/ANN calculations (§6)."""
    normalized_dict: dict[str, float]
    dense_vector: list[float]
    norm_version: str = "1.0.0"


# ── Canonical Historical State Snapshot (§4, §10) ───────────────────────
class HistoricalStateSnapshot(BaseModel):
    snapshot_id: str
    instrument: str
    instrument_family: str = "INDEX"
    exchange: str = "NSE"
    timeframe: str = "1m"
    timestamp: datetime
    trading_date: str
    session: SessionPhase
    minute_of_session: int = 0
    feature_version: str
    embedding_version: str
    schema_version: str = "1.0.0"
    market_regime: MarketRegime
    volatility_regime: VolatilityRegime
    vix_bucket: VixBucket
    trend_state: str = "FLAT"
    momentum_state: str = "NEUTRAL"
    structure_state: str = "CONSOLIDATION"
    volume_state: str = "NORMAL"
    futures_state: str = "NEUTRAL"
    options_state: str = "NEUTRAL"
    data_quality_score: float = 1.0
    feature_vector: CanonicalFeatureVector
    normalized_vector: NormalizedFeatureVector
    embedding: list[float]


# ── Historical Forward Outcomes (§11) ──────────────────────────────────
class ForwardOutcomeHorizon(BaseModel):
    horizon_minutes: int
    return_pct: float
    direction: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    mfe_pct: float                      # Maximum Favorable Excursion %
    mae_pct: float                      # Maximum Adverse Excursion %
    high_price: float
    low_price: float
    target_hit: bool
    stop_hit: bool
    duration_bars: Optional[int] = None
    continuation: bool = False
    failure: bool = False
    reversal: bool = False


class HistoricalOutcomeRecord(BaseModel):
    snapshot_id: str
    instrument: str
    timestamp: datetime
    entry_price: float
    outcome_15m: ForwardOutcomeHorizon
    outcome_30m: ForwardOutcomeHorizon
    outcome_60m: ForwardOutcomeHorizon
    labeled_at: datetime
    outcome_version: str = "1.0.0"


# ── Similarity & Analog Matches (§12, §14) ─────────────────────────────
class SimilarityBreakdown(BaseModel):
    embedding_similarity: float
    regime_similarity: float
    volatility_similarity: float
    session_similarity: float
    structure_similarity: float
    market_context_similarity: float
    final_similarity: float


class HistoricalAnalogMatch(BaseModel):
    snapshot_id: str
    instrument: str
    timeframe: str
    timestamp: datetime
    similarity_score: float
    breakdown: SimilarityBreakdown
    matched_regime: MarketRegime
    session_phase: SessionPhase
    outcome_15m: Optional[ForwardOutcomeHorizon] = None
    outcome_30m: Optional[ForwardOutcomeHorizon] = None
    outcome_60m: Optional[ForwardOutcomeHorizon] = None
    temporal_weight: float = 1.0
    is_fresh_window: bool = False


# ── Statistical Contracts (§20, §21) ───────────────────────────────────
class ConfidenceInterval(BaseModel):
    lower: float
    upper: float
    point_estimate: float
    confidence_level: float = 0.95


class HorizonStatistics(BaseModel):
    horizon_minutes: int
    bullish_probability: float
    bearish_probability: float
    neutral_probability: float
    continuation_probability: float
    failure_probability: float
    reversal_probability: float
    median_return: float
    mean_return: float
    median_mfe: float
    median_mae: float
    target_hit_rate: float
    stop_hit_rate: float
    median_duration: Optional[float] = None
    confidence_interval_bullish: ConfidenceInterval


# ── Query Request & Response (§24, §25) ────────────────────────────────
class HistoricalQuery(BaseModel):
    instrument: str = "NIFTY"
    timeframe: str = "1m"
    top_k: int = 50
    min_similarity: float = 0.65
    temporal_cutoff: Optional[datetime] = None  # Enforces strictly T < temporal_cutoff for replay
    regime_filter: Optional[MarketRegime] = None
    session_filter: Optional[SessionPhase] = None
    volatility_filter: Optional[VolatilityRegime] = None
    mode: Literal["MARKET_STATE", "CANDIDATE"] = "MARKET_STATE"
    candidate_type: Optional[str] = None
    strategy_id: Optional[str] = None
    include_fresh_window: bool = True
    fresh_window_days: int = 10


class HistoricalIntelligenceResult(BaseModel):
    """Canonical Output Contract matching §25."""
    historical_analysis_id: str
    instrument: str
    timestamp: datetime
    query_snapshot_id: str
    feature_version: str
    embedding_version: str
    sample_count: int
    effective_sample_size: float
    similarity_score: float
    probability_15m: float
    probability_30m: float
    probability_60m: float
    bullish_probability: float
    bearish_probability: float
    neutral_probability: float
    continuation_probability: float
    failure_probability: float
    reversal_probability: float
    median_return_15m: float
    median_return_30m: float
    median_return_60m: float
    median_MFE: float
    median_MAE: float
    target_hit_rate: float
    stop_hit_rate: float
    historical_regime: str
    sample_distribution: dict[str, int]
    confidence: float
    data_quality: float
    computed_at: datetime
    published_at: datetime
    staleness_seconds: float
    status: HIEStatus
    analog_matches: list[HistoricalAnalogMatch] = Field(default_factory=list)


# ── AI Context Structured Evidence (§26, §27) ───────────────────────────
class AIStructuredContext(BaseModel):
    historical_summary_text: str
    total_analogs: int
    effective_sample_size: float
    sample_reliability: SampleReliability
    evidence_table: dict[str, Any]
    failure_analysis: dict[str, Any]
    regime_consistency_note: str
    historical_edge_status: str


# ── Final Output Contract for Simple Historical AI ─────────────────────
class HorizonProbabilities(BaseModel):
    bullish: float = 0.0
    bearish: float = 0.0
    neutral: float = 0.0


class HistoricalAIResult(BaseModel):
    """
    Final Output Contract for Historical AI ('What Happened Last Time?' Engine).
    Reports empirical probabilities and forward outcomes from historical setups.
    """
    status: str = "READY"  # READY, INSUFFICIENT_SAMPLE, UNKNOWN, STALE
    sample_count: int = 0
    probability_15m: HorizonProbabilities = Field(default_factory=HorizonProbabilities)
    probability_30m: HorizonProbabilities = Field(default_factory=HorizonProbabilities)
    probability_60m: HorizonProbabilities = Field(default_factory=HorizonProbabilities)
    failure_rate: float = 0.0
    confidence: str = "UNKNOWN"  # LOW, MEDIUM, HIGH, UNKNOWN
    historical_context: str = ""
    # Optional empirical metrics
    median_return_15m: Optional[float] = None
    median_return_30m: Optional[float] = None
    median_return_60m: Optional[float] = None
    median_mfe: Optional[float] = None
    median_mae: Optional[float] = None
    continuation_rate: Optional[float] = None
    reversal_rate: Optional[float] = None
