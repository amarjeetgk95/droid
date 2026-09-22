"""
Domain types, enums, and models for VORTEX-SNAP Scalping Engine.

All structures are typed, serialized via Pydantic, and point-in-time safe.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────

class SessionPhase(str, Enum):
    """Trading session phases for Indian index derivatives (09:15 - 15:30 IST)."""
    PRE_OPEN = "PRE_OPEN"                     # 09:00 - 09:15
    MARKET_OPEN = "MARKET_OPEN"               # 09:15 - 09:20 (price discovery, high noise)
    OPENING_RANGE = "OPENING_RANGE"           # 09:20 - 09:45 (initial balance establishment)
    NORMAL_INTRADAY = "NORMAL_INTRADAY"       # 09:45 - 14:45 (institutional flow & trend)
    LATE_SESSION = "LATE_SESSION"             # 14:45 - 15:15 (intraday square-off momentum)
    FORCED_SQUARE_OFF = "FORCED_SQUARE_OFF"   # 15:15 - 15:30 (broker square-off window)
    CLOSED = "CLOSED"                         # 15:30+ or weekends/holidays


class MarketRegime(str, Enum):
    """Regime classification (§19). Controls allowable strategy candidate types."""
    TREND = "TREND"
    TRENDING_VOLATILITY = "TRENDING_VOLATILITY"
    RANGE = "RANGE"
    EXPANSION = "EXPANSION"
    EXHAUSTION = "EXHAUSTION"
    CHAOTIC = "CHAOTIC"
    UNKNOWN = "UNKNOWN"


class CompressionZone(str, Enum):
    """Compression intensity tier (§6)."""
    UNCOMPRESSED = "UNCOMPRESSED"       # < 0.55
    WATCH = "WATCH"                     # 0.55 - 0.70
    ARMED = "ARMED"                     # 0.70 - 0.85
    EXTREME = "EXTREME"                 # > 0.85


class TranslationState(str, Enum):
    """Interpretation of directional pressure vs price displacement (§8)."""
    DIRECTIONAL_ACCEPTANCE = "DIRECTIONAL_ACCEPTANCE"  # High pressure + high displacement
    ABSORPTION_CANDIDATE = "ABSORPTION_CANDIDATE"      # High pressure + low displacement
    REJECTION_CONFLICT = "REJECTION_CONFLICT"          # Pressure direction != price direction
    NEUTRAL = "NEUTRAL"                                # Indeterminate or low pressure


class LevelType(str, Enum):
    """Key structural level categories (§5)."""
    PDH = "PDH"                     # Previous Day High
    PDL = "PDL"                     # Previous Day Low
    PDC = "PDC"                     # Previous Day Close
    CDO = "CDO"                     # Current Day Open
    SESSION_HIGH = "SESSION_HIGH"   # Rolling intraday high
    SESSION_LOW = "SESSION_LOW"     # Rolling intraday low
    ORH = "ORH"                     # Opening Range High (first 15/30m)
    ORL = "ORL"                     # Opening Range Low
    VWAP = "VWAP"                   # Volume Weighted Average Price
    SWING_HIGH_5M = "SWING_HIGH_5M" # 5-min context swing high
    SWING_LOW_5M = "SWING_LOW_5M"   # 5-min context swing low
    VOLUME_NODE = "VOLUME_NODE"     # High volume consolidation node


class EventType(str, Enum):
    """Breakout event classifications (§12)."""
    CONTINUATION = "CONTINUATION"   # Type A: High compression, vacuum, translation aligned
    ABSORPTION = "ABSORPTION"       # Type B: High pressure, low translation, level interaction
    VACUUM_TRAP = "VACUUM_TRAP"     # Type C: Rapid displacement, fail to hold level, reclaim


class VortexState(str, Enum):
    """16-State VORTEX-SNAP Finite State Machine (§16)."""
    IDLE = "IDLE"
    COMPRESSION = "COMPRESSION"
    ARMED = "ARMED"
    IGNITION = "IGNITION"
    CLASSIFICATION = "CLASSIFICATION"
    CONTINUATION = "CONTINUATION"
    ABSORPTION = "ABSORPTION"
    TRAP = "TRAP"
    CONFIRMATION = "CONFIRMATION"
    PRE_TRADE_VALIDATION = "PRE_TRADE_VALIDATION"
    EXECUTABLE = "EXECUTABLE"
    ACTIVE = "ACTIVE"
    EXIT = "EXIT"
    COOLDOWN = "COOLDOWN"


# ─────────────────────────────────────────────────────────────────────────────
# Base Feature Models
# ─────────────────────────────────────────────────────────────────────────────

class Candle(BaseModel):
    """1-minute or aggregated OHLCV candle with strict validation."""
    timestamp: int = Field(description="Epoch millisecond timestamp of candle close")
    open: float = Field(gt=0, description="Open price")
    high: float = Field(gt=0, description="High price")
    low: float = Field(gt=0, description="Low price")
    close: float = Field(gt=0, description="Close price")
    volume: float = Field(ge=0, description="Traded volume in bar")

    @property
    def range(self) -> float:
        return max(self.high - self.low, 1e-9)

    @property
    def body(self) -> float:
        return self.close - self.open

    @property
    def upper_wick(self) -> float:
        return max(self.high - max(self.open, self.close), 0.0)

    @property
    def lower_wick(self) -> float:
        return max(min(self.open, self.close) - self.low, 0.0)


class MarketSessionInfo(BaseModel):
    """Market session context (§4)."""
    session_phase: SessionPhase
    minutes_from_open: float = Field(ge=0)
    minutes_to_close: float = Field(ge=0)
    day_of_week: int = Field(ge=0, le=6, description="Monday=0, Sunday=6")
    timestamp_ms: int
    is_trading_allowed: bool
    is_no_trade_window: bool
    is_forced_square_off: bool


class StructuralLevel(BaseModel):
    """Individual structural level and its dynamic relevance (§5)."""
    level_type: LevelType
    price: float
    relevance_score: float = Field(ge=0.0, le=1.0)
    distance_points: float = Field(description="Signed distance: current_price - price")
    distance_pct: float = Field(description="Absolute percentage distance from current price")
    touch_count: int = Field(ge=0, description="Historical touches in current session")
    rejection_count: int = Field(ge=0, description="Clean rejections observed at level")
    is_broken: bool = Field(default=False)
    is_retested: bool = Field(default=False)
    volume_at_level: float = Field(default=0.0)


class StructuralLevelMapResult(BaseModel):
    """Complete structural level map snapshot."""
    levels: List[StructuralLevel] = Field(default_factory=list)
    nearest_support: Optional[StructuralLevel] = None
    nearest_resistance: Optional[StructuralLevel] = None
    distance_to_nearest_support: Optional[float] = None
    distance_to_nearest_resistance: Optional[float] = None
    vwap: Optional[float] = None
    computation_time_ms: float = 0.0


class CompressionResult(BaseModel):
    """Compression Engine output (§6)."""
    compression_score: float = Field(ge=0.0, le=1.0)
    zone: CompressionZone
    atr_ratio: float = Field(description="ATR_short / ATR_long")
    realized_vol_percentile: float = Field(ge=0.0, le=1.0)
    true_range_compression: float = Field(ge=0.0, le=1.0)
    candle_overlap: float = Field(ge=0.0, le=1.0)
    range_contraction: float = Field(ge=0.0, le=1.0)
    directional_entropy: float = Field(ge=0.0, le=1.0)
    displacement_efficiency: float = Field(ge=0.0, le=1.0)
    duration_bars: int = Field(ge=0, description="Bars spent in current compression zone")
    computation_time_ms: float = 0.0


class DirectionalPressureResult(BaseModel):
    """Directional Pressure Engine output (§7)."""
    net_pressure: float = Field(description="Net cumulative pressure over short window")
    pressure_score: float = Field(ge=-1.0, le=1.0, description="Normalized pressure score")
    pressure_direction: int = Field(description="Direction: +1 (bullish), -1 (bearish), 0 (neutral)")
    positive_pressure: float = Field(ge=0.0)
    negative_pressure: float = Field(ge=0.0)
    pressure_acceleration: float = Field(description="Raw rate of change of pressure (volume units/bar^2, legacy)")
    pressure_acceleration_norm: float = Field(default=0.0, description="Scale-normalized acceleration (comparable to pressure_score units/bar)")
    pressure_persistence: int = Field(description="Signed consecutive bars with same-sign pressure (negative=bearish)")
    pressure_change: float = Field(description="Raw pressure change from previous bar (volume units)")
    pressure_5bar: float = Field(description="5-bar rolling net pressure")
    pressure_10bar: float = Field(description="10-bar rolling net pressure")
    computation_time_ms: float = 0.0


class TranslationRatioResult(BaseModel):
    """Translation Ratio output (§8) - PRIMARY HYPOTHESIS."""
    translation_ratio: float = Field(ge=0.0, description="Price displacement / Pressure")
    translation_score: float = Field(ge=0.0, le=1.0, description="Normalized translation efficiency")
    translation_state: TranslationState
    normalized_displacement: float = Field(ge=0.0, description="ATR-normalized displacement (dimensionless, NOT points)")
    raw_displacement_points: float = Field(default=0.0, description="Raw price displacement in index points (current_close - reference_close)")
    normalized_pressure: float = Field(ge=0.0)
    price_direction: int = Field(description="+1 up, -1 down, 0 flat")
    pressure_direction: int = Field(description="+1 bull, -1 bear, 0 neutral")
    direction_aligned: bool = Field(description="True if price displacement aligns with pressure")
    translation_change: float = Field(description="Change in translation ratio vs previous bar")
    computation_time_ms: float = 0.0


class AbsorptionResult(BaseModel):
    """Absorption Detector output (§9)."""
    absorption_score: float = Field(ge=0.0, le=1.0)
    is_absorption_suspected: bool
    volume_shock_ratio: float = Field(ge=0.0)
    rejection_wick_ratio: float = Field(ge=0.0, le=1.0)
    level_proximity_score: float = Field(ge=0.0, le=1.0)
    repeated_test_count: int = Field(ge=0)
    failure_to_extend: bool
    opposing_pressure: bool
    interacted_level: Optional[StructuralLevel] = None
    computation_time_ms: float = 0.0


class LiquidityVacuumResult(BaseModel):
    """Liquidity Vacuum Detector output (§10)."""
    liquidity_vacuum_score: float = Field(ge=0.0, le=1.0)
    is_vacuum_detected: bool
    range_expansion: float = Field(ge=0.0, description="Current TR / Median recent TR")
    volume_shock: float = Field(ge=0.0, description="Current volume / Median recent volume")
    close_location: float = Field(ge=0.0, le=1.0, description="Close position in candle: (C-L)/(H-L)")
    overlap_penalty: float = Field(ge=0.0, le=1.0, description="Recent candle overlap penalty")
    prior_compression_passed: bool = Field(description="True if preceded by validated compression")
    computation_time_ms: float = 0.0


class SnapEnergyResult(BaseModel):
    """Snap Energy Composite output (§11)."""
    snap_energy: float = Field(ge=0.0, le=1.0, description="Accumulated potential release energy")
    compression_duration: int = Field(ge=0, description="Bars spent in compression")
    pressure_accumulation: float = Field(ge=0.0, description="Integrated directional pressure")
    directional_consistency: float = Field(ge=0.0, le=1.0, description="Directional uniformity of pressure")
    energy_tier: str = Field(description="LOW, MODERATE, HIGH, EXPLOSIVE")
    computation_time_ms: float = 0.0


class RegimeResult(BaseModel):
    """Market Regime Engine output (§19)."""
    regime: MarketRegime
    regime_confidence: float = Field(ge=0.0, le=1.0)
    trend_strength: float = Field(ge=0.0, le=1.0)
    volatility_state: str = Field(description="LOW, NORMAL, HIGH, EXTREME")
    efficiency_ratio: float = Field(ge=0.0, le=1.0, description="Kaufman efficiency ratio")
    permitted_events: List[EventType] = Field(default_factory=list)
    computation_time_ms: float = 0.0


class VortexFeatureSnapshot(BaseModel):
    """Unified point-in-time snapshot of all VORTEX-SNAP features at candle T."""
    instrument: str
    timestamp_ms: int
    spot_price: float
    session: MarketSessionInfo
    structural_levels: StructuralLevelMapResult
    compression: CompressionResult
    pressure: DirectionalPressureResult
    translation: TranslationRatioResult
    absorption: AbsorptionResult
    vacuum: LiquidityVacuumResult
    snap_energy: SnapEnergyResult
    regime: RegimeResult
    total_latency_ms: float = Field(ge=0.0)
    ablation_mask: Dict[str, bool] = Field(default_factory=dict)
