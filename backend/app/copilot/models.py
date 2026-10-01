"""Structured schemas for the DROID Market Intelligence Copilot.

Every quantitative value that reaches the frontend or the LLM passes through
these models. Missing evidence is `None` (never an invented number).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, Field

from app.copilot.enums import (
    AnalysisDepth,
    CopilotIntent,
    DataFreshness,
    DirectionalState,
    FactorState,
    GateStatus,
    Horizon,
    LevelType,
    ProbabilityStatus,
    QualityGrade,
    ScenarioId,
    SourceStatus,
    ValidationVerdict,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Source freshness (spec §23)
# --------------------------------------------------------------------------- #
class SourceFreshness(BaseModel):
    source: str
    label: str
    timestamp: datetime | None = None
    age_seconds: float | None = None
    status: SourceStatus = "UNAVAILABLE"
    detail: str | None = None


class DataQualityBlock(BaseModel):
    overall: QualityGrade = "UNKNOWN"
    missing_fields: list[str] = Field(default_factory=list)
    stale_sources: list[str] = Field(default_factory=list)
    sources: list[SourceFreshness] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# MarketContext (spec §5) — normalized, null-honest market snapshot
# --------------------------------------------------------------------------- #
class PriceContext(BaseModel):
    ltp: float | None = None
    change_pct: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    day_open: float | None = None
    previous_close: float | None = None
    volume: float | None = None


class RegimeContext(BaseModel):
    name: str = "UNKNOWN"
    summary: str | None = None
    trend_strength: float | None = None
    volatility_state: str | None = None
    adx: float | None = None
    vix: float | None = None
    vix_category: str | None = None
    classification_confidence: float | None = None


class TechnicalContext(BaseModel):
    rsi: float | None = None
    vwap: float | None = None
    supertrend: float | None = None
    supertrend_direction: str | None = None
    atr: float | None = None
    poc: float | None = None
    vah: float | None = None
    val: float | None = None
    ema_20: float | None = None
    ema_50: float | None = None
    sma_200: float | None = None
    bollinger_bandwidth: float | None = None
    bollinger_pct_b: float | None = None
    plus_di: float | None = None
    minus_di: float | None = None
    prior_day_high: float | None = None
    prior_day_low: float | None = None
    prior_day_close: float | None = None
    pivot: float | None = None
    r1: float | None = None
    r2: float | None = None
    s1: float | None = None
    s2: float | None = None


class OptionsContext(BaseModel):
    pcr_oi: float | None = None
    pcr_volume: float | None = None
    max_pain: float | None = None
    atm_iv: float | None = None
    iv_skew: float | None = None
    call_wall: float | None = None
    put_wall: float | None = None
    expiry: str | None = None
    total_call_oi: int | None = None
    total_put_oi: int | None = None
    time_to_expiry_days: float | None = None


class FuturesContext(BaseModel):
    contract_price: float | None = None
    basis: float | None = None
    basis_pct: float | None = None
    oi_change_pct: float | None = None
    positioning: str | None = None
    positioning_note: str | None = None
    rollover_pct: float | None = None
    curve_state: str | None = None


class InstitutionalFlowContext(BaseModel):
    fii: float | None = None
    dii: float | None = None
    net_flow: float | None = None
    sentiment: str | None = None
    as_of: str | None = None
    live: bool = False


class HistoricalContext(BaseModel):
    available: bool = False
    analog_count: int = 0
    similarity_threshold: float | None = None
    forward_outcome: dict[str, int] | None = None
    median_return: float | None = None
    mean_return: float | None = None
    win_rate: float | None = None
    dispersion: float | None = None
    direction_agreement: float | None = None
    message: str | None = None
    lookahead_guard: str | None = None
    engine_version: str = "copilot-analogs-1.0"


class MarketContext(BaseModel):
    symbol: str
    timestamp: datetime = Field(default_factory=_now)
    market_status: str = "UNKNOWN"
    horizon: Horizon = "TODAY"
    price: PriceContext = Field(default_factory=PriceContext)
    regime: RegimeContext = Field(default_factory=RegimeContext)
    technicals: TechnicalContext = Field(default_factory=TechnicalContext)
    options: OptionsContext = Field(default_factory=OptionsContext)
    futures: FuturesContext = Field(default_factory=FuturesContext)
    institutional_flow: InstitutionalFlowContext = Field(default_factory=InstitutionalFlowContext)
    historical: HistoricalContext = Field(default_factory=HistoricalContext)
    data_quality: DataQualityBlock = Field(default_factory=DataQualityBlock)
    partial: bool = False
    missing_sources: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Feature fusion (spec §6)
# --------------------------------------------------------------------------- #
class Factor(BaseModel):
    state: FactorState = "UNKNOWN"
    strength: float = 0.0
    confidence: float = 0.0
    evidence: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Confluence (spec §7)
# --------------------------------------------------------------------------- #
class ConfluenceResult(BaseModel):
    dominant_state: DirectionalState = "NO_SIGNAL"
    directional_strength: float = 0.0
    confluence: float = 0.0
    label: str = "NO SIGNAL"
    counts: dict[str, int] = Field(default_factory=dict)
    conflicting_factors: list[str] = Field(default_factory=list)
    factor_states: dict[str, str] = Field(default_factory=dict)
    insufficient_evidence: bool = False


# --------------------------------------------------------------------------- #
# Levels (spec §10)
# --------------------------------------------------------------------------- #
class MarketLevel(BaseModel):
    price: float
    type: LevelType
    source: list[str] = Field(default_factory=list)
    strength: float = 0.0
    status: str = "ACTIVE"
    distance_pct: float | None = None


class LevelsBlock(BaseModel):
    support: list[MarketLevel] = Field(default_factory=list)
    resistance: list[MarketLevel] = Field(default_factory=list)
    bull_trigger: float | None = None
    bear_trigger: float | None = None
    bull_trigger_note: str | None = None
    bear_trigger_note: str | None = None


# --------------------------------------------------------------------------- #
# Scenarios (spec §8)
# --------------------------------------------------------------------------- #
class Scenario(BaseModel):
    id: ScenarioId
    label: str
    probability: float | None = None
    probability_status: ProbabilityStatus = "UNAVAILABLE"
    conditions: list[str] = Field(default_factory=list)
    expected_range: dict[str, float | None | str] | None = None


# --------------------------------------------------------------------------- #
# Confidence vs data quality (spec §9)
# --------------------------------------------------------------------------- #
class ConfidenceBlock(BaseModel):
    model: float | None = None
    model_status: str = "UNAVAILABLE"
    data_quality: QualityGrade = "UNKNOWN"
    confluence: float = 0.0
    regime_stability: float | None = None


# --------------------------------------------------------------------------- #
# Prediction (spec §13)
# --------------------------------------------------------------------------- #
class PredictionResult(BaseModel):
    symbol: str
    horizon: Horizon
    direction: DirectionalState
    expected_return: float | None = None
    expected_range: dict[str, float | None] = Field(default_factory=dict)
    scenarios: list[Scenario] = Field(default_factory=list)
    confidence: ConfidenceBlock = Field(default_factory=ConfidenceBlock)
    model_version: str
    model_source: str
    probabilities: dict[str, float | None] = Field(default_factory=dict)
    calibration: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Invalidation (spec §11)
# --------------------------------------------------------------------------- #
class InvalidationBlock(BaseModel):
    current_state: str
    bullish_trigger: str | None = None
    bearish_trigger: str | None = None
    invalidation: str | None = None
    confirmation_rule: str | None = None


# --------------------------------------------------------------------------- #
# Signal validation gates (spec §30)
# --------------------------------------------------------------------------- #
class GateCheck(BaseModel):
    gate: str
    status: GateStatus = "SKIPPED"
    reason: str | None = None
    evidence: list[str] = Field(default_factory=list)


class SignalUnderReview(BaseModel):
    signal_id: str | None = None
    symbol: str
    direction: str | None = None
    strategy: str | None = None
    timeframe: str | None = None
    fsm_state: str | None = None
    created_at: str | None = None
    entry: float | None = None
    stop: float | None = None
    target_1: float | None = None
    target_2: float | None = None
    source: str = "REQUEST"


class SignalValidationResult(BaseModel):
    verdict: ValidationVerdict = "CONDITIONAL"
    signal: SignalUnderReview
    gates: list[GateCheck] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    engine_version: str = "copilot-gates-1.0"
    authoritative: bool = True


# --------------------------------------------------------------------------- #
# Intent router output (spec §3)
# --------------------------------------------------------------------------- #
class IntentDecision(BaseModel):
    intent: CopilotIntent = "GENERAL_MARKET_QUESTION"
    symbol: str = "NIFTY"
    horizon: Horizon = "TODAY"
    analysis_depth: AnalysisDepth = "STANDARD"
    requires_options: bool = False
    requires_futures: bool = False
    requires_flow: bool = False
    requires_historical: bool = False
    requires_signal_validation: bool = False
    requires_breakout: bool = False
    tool_plan: list[str] = Field(default_factory=list)
    matched_rule: str | None = None
    classifier: str = "RULES"
    confidence: float = 0.0
    breakout_level: float | None = None
    warnings: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Evidence / response (spec §16, §17)
# --------------------------------------------------------------------------- #
class CopilotEvidence(BaseModel):
    bullish: list[str] = Field(default_factory=list)
    bearish: list[str] = Field(default_factory=list)
    neutral: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)


class CopilotVersions(BaseModel):
    copilot: str
    feature_engine: str
    prediction_model: str
    calibration: str
    prompt: str
    analog_engine: str
    gate_engine: str


class CopilotMeta(BaseModel):
    analysis_id: str
    symbol: str
    intent: CopilotIntent
    horizon: Horizon
    generated_at: datetime = Field(default_factory=_now)
    latency_ms: int = 0
    sources_count: int = 0
    data_freshness: DataFreshness = "OFFLINE"
    partial: bool = False
    missing_sources: list[str] = Field(default_factory=list)
    versions: CopilotVersions
    provider: str | None = None
    model: str | None = None
    classifier: str = "RULES"


class CopilotSummary(BaseModel):
    regime: str = "UNKNOWN"
    direction: DirectionalState = "NO_SIGNAL"
    bias_label: str = "NO SIGNAL"
    tone: str = "warn"
    confidence: float | None = None
    expected_range: dict[str, float | None] = Field(default_factory=dict)
    ltp: float | None = None
    change_pct: float | None = None


class CopilotAnalysisResponse(BaseModel):
    version: str = "1.0"
    meta: CopilotMeta
    summary: CopilotSummary
    market_state: MarketContext
    factors: dict[str, Factor] = Field(default_factory=dict)
    confluence: ConfluenceResult
    levels: LevelsBlock
    scenarios: list[Scenario] = Field(default_factory=list)
    evidence: CopilotEvidence
    historical: HistoricalContext
    validation: SignalValidationResult | None = None
    prediction: PredictionResult
    invalidation: InvalidationBlock
    explanation: str = ""
    explanation_source: str = "DETERMINISTIC"
    warnings: list[str] = Field(default_factory=list)
    data_quality: DataQualityBlock
    tools: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Request models (spec §27)
# --------------------------------------------------------------------------- #
class CopilotAnalyzeRequest(BaseModel):
    symbol: str | None = None
    query: str = ""
    horizon: Horizon | None = None
    depth: AnalysisDepth = "STANDARD"
    intent: CopilotIntent | None = None
    # LLM explanation controls — never affect quantitative values.
    provider: str | None = None
    model: str | None = None
    allow_paid: bool | None = None
    explain: bool = True
    openrouter_api_key: str | None = None
    gemini_api_key: str | None = None
    openai_api_key: str | None = None
    ollama_base_url: str | None = None
    ollama_model: str | None = None
    # Validation / follow-up context
    signal_id: str | None = None
    previous_analysis_id: str | None = None
    entry_price: float | None = None
    stop_loss: float | None = None
    target_price: float | None = None


class CopilotChatTurn(BaseModel):
    role: str
    content: str


class CopilotChatRequest(BaseModel):
    messages: list[CopilotChatTurn] = Field(default_factory=list)
    symbol: str | None = None
    horizon: Horizon | None = None
    depth: AnalysisDepth = "STANDARD"
    previous_analysis_id: str | None = None
    provider: str | None = None
    model: str | None = None
    allow_paid: bool | None = None
    explain: bool = True
    openrouter_api_key: str | None = None
    gemini_api_key: str | None = None
    openai_api_key: str | None = None
    ollama_base_url: str | None = None
    ollama_model: str | None = None


class PredictionOutcomeRequest(BaseModel):
    prediction_id: str
    outcome: str
    realized_return_pct: float | None = None
    realized_direction: DirectionalState | None = None
    level_result: str | None = None
    notes: str | None = None


class CopilotAuditRecord(BaseModel):
    prediction_id: str
    analysis_id: str
    timestamp: datetime = Field(default_factory=_now)
    symbol: str
    horizon: Horizon
    intent: CopilotIntent
    market_context: dict[str, Any]
    feature_snapshot: dict[str, Any]
    prediction: dict[str, Any]
    scenarios: list[dict[str, Any]] = Field(default_factory=list)
    probabilities: dict[str, float | None] = Field(default_factory=dict)
    levels: dict[str, Any]
    confidence: dict[str, Any]
    model_version: str
    prompt_version: str
    copilot_version: str
    outcome: str | None = None
    error_metrics: dict[str, Any] | None = None


