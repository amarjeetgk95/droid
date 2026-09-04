"""
Canonical AI Signal Schemas — §14, §21

All AI modules consume/produce AISignal — the one schema every module reads/writes.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, Field


class Decision(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NO_TRADE = "NO_TRADE"


class SetupType(str, Enum):
    BREAKOUT = "BREAKOUT"
    PULLBACK = "PULLBACK"
    MOMENTUM = "MOMENTUM"
    MEAN_REVERSION = "MEAN_REVERSION"
    CONTINUATION = "CONTINUATION"
    REVERSAL = "REVERSAL"
    GAP_FILL = "GAP_FILL"
    VOLATILITY_CONTRACTION = "VOLATILITY_CONTRACTION"


class Regime(str, Enum):
    TREND = "TREND"
    RANGE = "RANGE"
    BREAKOUT = "BREAKOUT"
    REVERSAL = "REVERSAL"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    UNKNOWN = "UNKNOWN"


class Direction(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class VolatilityLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ValidationStatus(str, Enum):
    PASS = "PASS"
    REJECT = "REJECT"


class AIProviderStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    SUSPENDED = "SUSPENDED"


class SampleQuality(str, Enum):
    POOR = "POOR"
    FAIR = "FAIR"
    GOOD = "GOOD"


class HistoricalEvidence(BaseModel):
    matches_found: int = 0
    continuation_rate: float = 0.0
    failure_rate: float = 0.0
    reversal_rate: float = 0.0
    median_move_points: float = 0.0
    median_duration_seconds: int = 0
    sample_quality: SampleQuality = SampleQuality.POOR


class OptionsContext(BaseModel):
    pcr_oi: float = 1.0
    pcr_volume: float = 1.0
    atm_iv: float = 14.0
    direction: Literal["BULLISH", "BEARISH", "NEUTRAL"] = "NEUTRAL"
    call_pressure: float = 50.0
    put_pressure: float = 50.0
    breakout_confirmation: str = "NEUTRAL"


class RegimeObject(BaseModel):
    regime: Regime = Regime.UNKNOWN
    direction: Direction = Direction.NEUTRAL
    strength: int = Field(default=0, ge=0, le=100)
    volatility: VolatilityLevel = VolatilityLevel.MEDIUM
    confidence: int = Field(default=0, ge=0, le=100)


class LatencyBreakdown(BaseModel):
    provider_latency_ms: int = 0
    network_latency_ms: int = 0
    parse_latency_ms: int = 0
    validation_latency_ms: int = 0
    total_latency_ms: int = 0


class RejectionReason(str, Enum):
    MARKET_CLOSED = "MARKET_CLOSED"
    STALE_DATA = "STALE_DATA"
    INVALID_SIGNAL = "INVALID_SIGNAL"
    INVALID_SCHEMA = "INVALID_SCHEMA"
    INVALID_ENUM = "INVALID_ENUM"
    CONFIDENCE_OUT_OF_RANGE = "CONFIDENCE_OUT_OF_RANGE"
    INVALID_STOP_TARGET = "INVALID_STOP_TARGET"
    EXPIRED_SIGNAL = "EXPIRED_SIGNAL"
    DUPLICATE_SIGNAL = "DUPLICATE_SIGNAL"
    EXCESSIVE_RISK = "EXCESSIVE_RISK"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    AI_UNAVAILABLE = "AI_UNAVAILABLE"
    UNKNOWN_REGIME = "UNKNOWN_REGIME"
    RISK_VIOLATION = "RISK_VIOLATION"
    POSITION_SIZE_EXCEEDED = "POSITION_SIZE_EXCEEDED"
    MARGIN_INSUFFICIENT = "MARGIN_INSUFFICIENT"
    MAX_DAILY_LOSS_HIT = "MAX_DAILY_LOSS_HIT"
    SPREAD_TOO_WIDE = "SPREAD_TOO_WIDE"
    CIRCUIT_BREAKER = "CIRCUIT_BREAKER"
    KILL_SWITCH = "KILL_SWITCH"
    TIMEFRAME_MISMATCH = "TIMEFRAME_MISMATCH"
    SYMBOL_MISMATCH = "SYMBOL_MISMATCH"
    CONFLICTING_SIGNALS = "CONFLICTING_SIGNALS"
    HISTORICAL_LEAKAGE = "HISTORICAL_LEAKAGE"


class ValidationResult(BaseModel):
    status: ValidationStatus = ValidationStatus.REJECT
    reason_code: Optional[RejectionReason] = None
    reason_detail: str = ""


class MarketContext(BaseModel):
    context_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str = "NIFTY"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: str = "1.0.0"

    current_price: float = 0.0
    market_status: str = "UNKNOWN"

    structure_1m: str = ""
    structure_3m: str = ""
    structure_5m: str = ""
    structure_15m: str = ""

    vwap: float = 0.0
    atr: float = 0.0
    volume: float = 0.0
    momentum: float = 0.0

    support_resistance: dict[str, float] = Field(default_factory=dict)

    regime: RegimeObject = Field(default_factory=RegimeObject)
    options_context: Optional[OptionsContext] = None
    historical_context: Optional[HistoricalEvidence] = None
    existing_position_state: str = "NONE"

    context_hash: str = Field(default_factory=lambda: str(uuid.uuid4()))


class AISignal(BaseModel):
    signal_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str = "NIFTY"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    timeframe: Literal["1M", "3M", "5M", "15M"] = "5M"

    decision: Decision = Decision.NO_TRADE
    setup_type: SetupType = SetupType.CONTINUATION
    regime: Regime = Regime.UNKNOWN
    direction: Direction = Direction.NEUTRAL

    raw_confidence: int = Field(default=0, ge=0, le=100)
    calibrated_confidence: int = Field(default=0, ge=0, le=100)
    confidence_threshold: int = Field(default=50, ge=0, le=100)

    entry: float = 0.0
    stop_loss: float = 0.0
    target: float = 0.0

    ttl_seconds: int = 60
    expires_at: Optional[datetime] = None

    historical_context: Optional[HistoricalEvidence] = None
    options_context: Optional[OptionsContext] = None

    reasons: list[str] = Field(default_factory=list)
    invalidation: list[str] = Field(default_factory=list)

    provider: str = ""
    model: str = ""

    latency_ms: int = 0
    latency_breakdown: LatencyBreakdown = Field(default_factory=LatencyBreakdown)

    validation_result: ValidationStatus = ValidationStatus.REJECT
    rejection_reason_code: Optional[RejectionReason] = None
    rejection_detail: str = ""

    reused: bool = False
    superseded: bool = False

    version: str = "1.0.0"

    def to_execution_dict(self) -> dict:
        return {
            "signal_id": self.signal_id,
            "symbol": self.symbol,
            "decision": self.decision.value,
            "setup_type": self.setup_type.value,
            "regime": self.regime.value,
            "direction": self.direction.value,
            "entry": self.entry,
            "stop_loss": self.stop_loss,
            "target": self.target,
            "ttl_seconds": self.ttl_seconds,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "raw_confidence": self.raw_confidence,
            "calibrated_confidence": self.calibrated_confidence,
            "reasons": self.reasons,
            "invalidation": self.invalidation,
            "provider": self.provider,
            "model": self.model,
            "latency_ms": self.latency_ms,
            "validation_result": self.validation_result.value,
            "rejection_reason_code": self.rejection_reason_code.value if self.rejection_reason_code else None,
            "reused": self.reused,
            "superseded": self.superseded,
        }


class ExecutionDecision(BaseModel):
    decision: Literal["PASS", "REJECT"] = "REJECT"
    reason_code: Optional[RejectionReason] = None
    reason_detail: str = ""
    signal_id: Optional[str] = None
    order_request: Optional[dict] = None


class ProviderMetrics(BaseModel):
    provider: str
    model: str
    request_id: str
    latency_ms: int
    status: str
    token_usage: Optional[dict] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    timeframe: str = "5M"
    signal_id: str = ""


class AuditRecord(BaseModel):
    record_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    signal_id: str = ""

    symbol: str = "NIFTY"
    timeframe: str = "5M"
    market_context_hash_version: str = ""

    regime: str = ""
    ai_provider: str = ""
    ai_model: str = ""
    prompt_version: str = ""

    ai_input: dict = Field(default_factory=dict)
    ai_output: dict = Field(default_factory=dict)

    validation_result: str = ""
    rejection_reason_code: Optional[str] = None

    latency_breakdown: LatencyBreakdown = Field(default_factory=LatencyBreakdown)
    signal_ttl: int = 0

    execution_decision: str = ""
    actual_execution: Optional[str] = None
    actual_fill: Optional[dict] = None
    eventual_outcome: Optional[str] = None

    version: str = "1.0.0"


class ProviderConfig(BaseModel):
    provider: str
    model: str
    timeout_ms: int = 4000
    max_retries: int = 1
    is_primary: bool = True
    health_check_interval_seconds: int = 15
    consecutive_failures_to_degrade: int = 3
    consecutive_failures_to_suspend: int = 6
    recovery_pings_required: int = 3


class ConfidenceCalibrationTable(BaseModel):
    version: str = "1.0.0"
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    buckets: dict[int, float] = Field(default_factory=dict)
    min_samples_per_bucket: int = 30
    lookback_window_days: int = 90


class AIEvaluationMetrics(BaseModel):
    signal_quality: dict = Field(default_factory=dict)
    ai_quality: dict = Field(default_factory=dict)
    operational_quality: dict = Field(default_factory=dict)
    by_strategy: dict = Field(default_factory=dict)
    by_timeframe: dict = Field(default_factory=dict)
    by_regime: dict = Field(default_factory=dict)
    by_setup_type: dict = Field(default_factory=dict)
    by_provider: dict = Field(default_factory=dict)
    by_model: dict = Field(default_factory=dict)
    by_confidence_bucket: dict = Field(default_factory=dict)
    by_time_of_day: dict = Field(default_factory=dict)


class DeepInsightTimeframeEntry(BaseModel):
    timeframe: str
    direction: Direction = Direction.NEUTRAL
    strength: int = Field(default=50, ge=0, le=100)
    structure: str = ""


class DeepInsightMarketLevels(BaseModel):
    current_price: float = 0.0
    vwap: float = 0.0
    support: float = 0.0
    resistance: float = 0.0
    vwap_relation: Literal["Above", "Below", "At"] = "At"


class DeepInsightMomentum(BaseModel):
    status: str = "Unknown"
    value: float = 0.0


class DeepInsightVolume(BaseModel):
    relative_value: float = 1.0
    status: Literal["High", "Normal", "Low"] = "Normal"


class DeepInsightMarket(BaseModel):
    regime: Regime = Regime.UNKNOWN
    direction: Direction = Direction.NEUTRAL
    regime_strength: int = 0
    volatility: VolatilityLevel = VolatilityLevel.MEDIUM
    levels: DeepInsightMarketLevels = Field(default_factory=DeepInsightMarketLevels)
    momentum: DeepInsightMomentum = Field(default_factory=DeepInsightMomentum)
    volume: DeepInsightVolume = Field(default_factory=DeepInsightVolume)


class DeepInsightOptionsEvidence(BaseModel):
    bias: Direction = Direction.NEUTRAL
    pcr: float = 1.0
    put_support: float = 0.0
    call_resistance: float = 0.0
    oi_trend: Literal["Increasing", "Decreasing", "Stable"] = "Stable"
    iv: str = "Moderate"
    interpretation: str = ""


class DeepInsightHistoricalEvidence(BaseModel):
    similar_states: int = 0
    continuation: float = 0.0
    failure: float = 0.0
    reversal: float = 0.0
    median_move: float = 0.0
    median_duration: str = ""
    sample_quality: SampleQuality = SampleQuality.POOR


class DeepInsightSetup(BaseModel):
    setup_type: SetupType = SetupType.CONTINUATION
    entry_zone: str = ""
    stop_loss: float = 0.0
    target: str = ""
    risk_reward: float = 0.0


class DeepInsightSignalState(BaseModel):
    state: Literal["ANALYZING", "ACTIVE", "VALIDATING", "APPROVED", "REJECTED", "EXPIRED", "SUPERSEDED", "AI_UNAVAILABLE"] = "AI_UNAVAILABLE"
    age: int = 0
    ttl: int = 0
    ttl_remaining: int = 0


class DeepInsightValidation(BaseModel):
    status: ValidationStatus = ValidationStatus.REJECT
    rejection_reason: Optional[str] = None


class DeepInsightProvider(BaseModel):
    name: str = ""
    model: str = ""
    latency_ms: int = 0


class DeepInsightDataQuality(BaseModel):
    completeness: float = 0.0
    status: Literal["Complete", "Partial", "Incomplete"] = "Incomplete"


class DeepInsightPayload(BaseModel):
    symbol: str = "NIFTY"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    market: DeepInsightMarket = Field(default_factory=DeepInsightMarket)
    regime: Regime = Regime.UNKNOWN
    multi_timeframe: list[DeepInsightTimeframeEntry] = Field(default_factory=list)

    ai_view: dict = Field(default_factory=dict)
    technical_evidence: dict = Field(default_factory=dict)
    options_evidence: DeepInsightOptionsEvidence = Field(default_factory=DeepInsightOptionsEvidence)
    historical_evidence: DeepInsightHistoricalEvidence = Field(default_factory=DeepInsightHistoricalEvidence)

    setup: DeepInsightSetup = Field(default_factory=DeepInsightSetup)
    risks: dict = Field(default_factory=dict)
    invalidation: list[str] = Field(default_factory=list)

    signal_state: DeepInsightSignalState = Field(default_factory=DeepInsightSignalState)
    data_quality: DeepInsightDataQuality = Field(default_factory=DeepInsightDataQuality)
    validation: DeepInsightValidation = Field(default_factory=DeepInsightValidation)
    provider: DeepInsightProvider = Field(default_factory=DeepInsightProvider)

    error: Optional[str] = None


ALLOWED_BIASES = ("BUY", "SELL", "HOLD", "NO_TRADE", "WAIT_FOR_CONFIRMATION")

LEGACY_BIAS_MAP = {
    "BULLISH": "BUY",
    "BEARISH": "SELL",
    "NEUTRAL": "HOLD",
    "VOLATILE": "WAIT_FOR_CONFIRMATION",
}

DECISION_TO_BIAS = {
    Decision.LONG: "BUY",
    Decision.SHORT: "SELL",
    Decision.NO_TRADE: "NO_TRADE",
}

DECISION_TO_DIRECTION = {
    Decision.LONG: Direction.BULLISH,
    Decision.SHORT: Direction.BEARISH,
    Decision.NO_TRADE: Direction.NEUTRAL,
}
