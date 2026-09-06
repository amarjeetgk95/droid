from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Literal, Optional, Any
from pydantic import BaseModel, Field

# Core Type Definitions (§7, §8, §9, §10, §17)
VerificationStatus = Literal[
    "UNVERIFIED",
    "PARTIALLY_VERIFIED",
    "VERIFIED",
    "CONFLICTING",
    "CANCELLED",
    "RESCHEDULED",
]

EventCertainty = Literal[
    "CONFIRMED",
    "LIKELY",
    "EXPECTED",
    "APPROXIMATE",
    "RUMORED",
    "UNKNOWN",
]

TimestampPrecision = Literal[
    "EXACT",
    "DATE_ONLY",
    "APPROXIMATE",
    "UNKNOWN",
]

ExpectedDirection = Literal[
    "BULLISH",
    "BEARISH",
    "NEUTRAL",
    "TWO_SIDED",
    "UNKNOWN",
]

TimeHorizon = Literal[
    "SCALP",
    "INTRADAY",
    "SWING",
    "MULTI_DAY",
    "LONG_TERM",
    "UNKNOWN",
]

EventType = Literal[
    "MACRO",
    "CENTRAL_BANK",
    "COMPANY",
    "EARNINGS",
    "CORPORATE_ACTION",
    "REGULATORY",
    "POLICY",
    "GLOBAL",
    "GEOPOLITICAL",
    "SECTOR",
    "OTHER",
]

TemporalPhase = Literal[
    "SCHEDULED",
    "APPROACHING",
    "ACTIVE",
    "POST_EVENT",
    "ARCHIVED",
]

DeduplicationMatch = Literal[
    "EXACT_DUPLICATE",
    "PROBABLE_DUPLICATE",
    "POSSIBLE_MATCH",
    "UNRELATED",
]

StrategyState = Literal[
    "NO_SETUP",
    "WAIT_FOR_CONFIRMATION",
    "PRE_EVENT_SETUP",
    "VOLATILITY_EXPANSION",
    "DIRECTIONAL_SETUP",
    "BREAKOUT_SETUP",
    "MOMENTUM_SETUP",
    "EVENT_SCALP",
    "POST_EVENT_CONTINUATION",
    "POST_EVENT_REVERSAL",
]

TradingDecision = Literal[
    "NO_TRADE",
    "WAIT_FOR_CONFIRMATION",
    "EXECUTE_SHADOW",
    "EXECUTE_ACTIVE",
]


class ProcessingFlags(BaseModel):
    discovered: bool = True
    verified: bool = False
    classified: bool = False
    impact_mapped: bool = False
    scored: bool = False


class RawSourceEvent(BaseModel):
    source_name: str
    source_type: str = "OFFICIAL"
    source_url: Optional[str] = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    fetch_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_verified: bool = False


class EventImpactMapping(BaseModel):
    target_type: Literal["SECTOR", "INDEX", "STOCK", "DERIVATIVE"]
    target_symbol: str
    impact_strength: Literal["HIGH", "MEDIUM", "LOW"]
    relationship_confidence: float = 1.0
    historical_sensitivity: Optional[float] = None
    primary_or_secondary: Literal["PRIMARY", "SECONDARY"] = "PRIMARY"
    notes: Optional[str] = None


class ImportanceScoreBreakdown(BaseModel):
    final_score: float
    source_authority: float
    scope: float
    historical_significance: float
    policy_impact: float
    surprise_potential: float
    weights_applied: dict[str, float]
    excluded_components: list[str] = Field(default_factory=list)
    formula_version: str = "v3.0.0"


class MarketImpactBreakdown(BaseModel):
    status: Literal["SCORED", "INSUFFICIENT_DATA", "EXCLUDED"] = "INSUFFICIENT_DATA"
    final_score: Optional[float] = None
    historical_move_percentile: Optional[float] = None
    liquidity_and_sensitivity: Optional[float] = None
    volatility_regime: Optional[float] = None
    positioning_skew: Optional[float] = None
    event_proximity: Optional[float] = None
    reason: Optional[str] = "Historical reaction dataset pending calibration"


class OpportunityScoreBreakdown(BaseModel):
    status: Literal["SCORED", "INSUFFICIENT_DATA", "NO_TRADE"] = "INSUFFICIENT_DATA"
    final_score: Optional[float] = None
    setup_quality: Optional[float] = None
    liquidity_and_spread: Optional[float] = None
    signal_confidence: Optional[float] = None
    risk_reward: Optional[float] = None
    confirmation_state: Optional[float] = None
    passed_gates: list[str] = Field(default_factory=list)
    failed_gates: list[str] = Field(default_factory=list)
    final_decision: TradingDecision = "NO_TRADE"
    reason: Optional[str] = "Phase 1: Trading Opportunity decoupled pending live market connectivity"


class EventScoreSnapshot(BaseModel):
    canonical_event_id: str
    formula_version: str = "v3.0.0"
    importance: ImportanceScoreBreakdown
    market_impact: MarketImpactBreakdown
    opportunity: OpportunityScoreBreakdown
    final_decision: TradingDecision = "NO_TRADE"
    calculated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PredictionSnapshot(BaseModel):
    prediction_id: str = Field(default_factory=lambda: f"PRED-{uuid.uuid4().hex[:8].upper()}")
    canonical_event_id: str
    prediction_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data_cutoff_timestamp: datetime
    feature_cutoff_timestamp: datetime
    formula_version: str = "v3.0.0"
    configuration_version: str = "v3.0.0"
    importance_score: Optional[float] = None
    market_impact_score: Optional[float] = None
    opportunity_score: Optional[float] = None
    predicted_direction: ExpectedDirection = "UNKNOWN"
    confidence: float = 0.0
    strategy_state: StrategyState = "NO_SETUP"
    decision: TradingDecision = "NO_TRADE"
    snapshot_immutable: bool = True


class EventComparable(BaseModel):
    past_event_id: str
    past_event_date: str
    similarity_score: float
    key_comparison_factor: Optional[str] = None
    past_market_reaction: dict[str, Any] = Field(default_factory=dict)


class LifecycleTransition(BaseModel):
    canonical_event_id: str
    from_phase: TemporalPhase
    to_phase: TemporalPhase
    reason: str
    actor: str = "EVENT_ENGINE"
    event_version: int = 1
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class CanonicalEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    canonical_event_id: str
    title: str
    description: Optional[str] = None
    event_type: EventType = "CENTRAL_BANK"
    sub_type: Optional[str] = None
    entity_id: str = "RBI"
    entity_name: str = "Reserve Bank of India"
    sector: str = "BANKING"
    event_timestamp: datetime
    timezone: str = "Asia/Kolkata"
    timestamp_precision: TimestampPrecision = "EXACT"
    verification_status: VerificationStatus = "UNVERIFIED"
    certainty: EventCertainty = "CONFIRMED"
    expected_direction: ExpectedDirection = "UNKNOWN"
    time_horizon: TimeHorizon = "INTRADAY"
    temporal_phase: TemporalPhase = "SCHEDULED"
    processing_flags: ProcessingFlags = Field(default_factory=ProcessingFlags)
    source_priority: str = "PRIMARY"
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relational details when loaded with relations
    sources: list[RawSourceEvent] = Field(default_factory=list)
    impact_mappings: list[EventImpactMapping] = Field(default_factory=list)
    scores: Optional[EventScoreSnapshot] = None
    latest_prediction: Optional[PredictionSnapshot] = None
    comparables: list[EventComparable] = Field(default_factory=list)


class EventCreate(BaseModel):
    canonical_event_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    event_type: EventType = "CENTRAL_BANK"
    sub_type: Optional[str] = "MONETARY_POLICY_COMMITTEE"
    entity_id: str = "RBI"
    entity_name: str = "Reserve Bank of India"
    sector: str = "BANKING"
    event_timestamp: datetime
    timezone: str = "Asia/Kolkata"
    timestamp_precision: TimestampPrecision = "EXACT"
    verification_status: VerificationStatus = "VERIFIED"
    certainty: EventCertainty = "CONFIRMED"
    expected_direction: ExpectedDirection = "UNKNOWN"
    time_horizon: TimeHorizon = "INTRADAY"
    source_name: str = "MANUAL_OPS"
    source_url: Optional[str] = None
    notes: Optional[str] = None


class EventUpdate(BaseModel):
    verification_status: Optional[VerificationStatus] = None
    certainty: Optional[EventCertainty] = None
    expected_direction: Optional[ExpectedDirection] = None
    temporal_phase: Optional[TemporalPhase] = None
    notes: Optional[str] = None
