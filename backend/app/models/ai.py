from datetime import datetime, timezone
from typing import Literal, Any
from pydantic import BaseModel, Field

MarketBias = Literal["BULLISH", "BEARISH", "NEUTRAL", "VOLATILE"]
AIChatRole = Literal["system", "user", "assistant", "tool"]


class AIInsightResponse(BaseModel):
    """Structured, explainable AI market intelligence report."""
    symbol: str
    timestamp: datetime
    market_bias: MarketBias
    confidence: float = Field(description="Confidence percentage (0-100%)")
    executive_summary: str
    options_interpretation: str
    futures_flow_analysis: str
    regime_and_levels: str
    recommended_strategy_framework: str
    risk_management_notes: str
    disclaimer: str = Field(
        default="This AI analysis is strictly for quantitative research and education. It does not constitute financial advice or trade recommendations."
    )
    provider_used: str = "gemini"


class AIInsightPayload(BaseModel):
    """Request payload to generate AI market analysis."""
    symbol: str = "NIFTY"
    provider: str | None = None
    custom_query: str | None = None


class AIHistoryItem(BaseModel):
    """Summary item for past generated market analyses."""
    id: str
    symbol: str
    timestamp: datetime
    market_bias: MarketBias
    confidence: float
    executive_summary: str


# ---------------------------------------------------------------------------
# Conversational Copilot & Chat Schemas
# ---------------------------------------------------------------------------

class AIChatMessage(BaseModel):
    """Single message in a multi-turn AI chat conversation."""
    role: AIChatRole
    content: str = ""
    reasoning_content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None


class AIChatRequest(BaseModel):
    """Request payload for multi-turn AI chat / copilot."""
    messages: list[AIChatMessage]
    symbol: str = "NIFTY"
    provider: str = "openrouter"
    model: str | None = None
    temperature: float = 0.3
    context_page: str | None = None
    enable_tools: bool = True
    allow_paid: bool | None = None
    openrouter_api_key: str | None = None
    gemini_api_key: str | None = None
    openai_api_key: str | None = None
    ollama_base_url: str | None = None
    ollama_model: str | None = None


class AIChatStreamChunk(BaseModel):
    """Streaming chunk emitted via SSE."""
    type: Literal["content", "reasoning", "tool_call", "tool_result", "done", "error"]
    delta: str = ""
    reasoning_delta: str = ""
    tool_call: dict[str, Any] | None = None
    tool_result: dict[str, Any] | None = None
    finish_reason: str | None = None
    provider_used: str | None = None
    model_used: str | None = None


# ---------------------------------------------------------------------------
# Options Strategy Architect Schemas
# ---------------------------------------------------------------------------

class AIOptionLeg(BaseModel):
    strike: float
    option_type: Literal["CE", "PE"]
    action: Literal["BUY", "SELL"]
    expiry: str | None = None
    estimated_premium: float = 0.0
    delta: float | None = None
    theta: float | None = None


class AIOptionsStrategyRecommendation(BaseModel):
    """Structured options strategy structured by AI based on quantitative context."""
    symbol: str
    strategy_name: str
    market_outlook: str
    legs: list[AIOptionLeg]
    max_profit_pts: str = "Limited / Variable"
    max_loss_pts: str = "Defined / Variable"
    risk_reward_ratio: str = "1:2"
    breakevens: list[float] = []
    net_debit_credit_pts: float = 0.0
    net_delta: float = 0.0
    net_theta: float = 0.0
    rationale: str
    entry_rules: list[str] = []
    exit_rules: list[str] = []
    risk_management: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    provider_used: str = "openrouter"


class AIOptionsStrategyRequest(BaseModel):
    symbol: str = "NIFTY"
    outlook: Literal["BULLISH", "BEARISH", "NEUTRAL", "HIGH_VOLATILITY", "LOW_VOLATILITY", "DIRECTIONAL_RANGE"] = "NEUTRAL"
    custom_query: str | None = None
    target_dte: int | None = None
    max_risk_tolerance: Literal["LOW", "MODERATE", "AGGRESSIVE"] = "MODERATE"
    provider: str = "openrouter"
    model: str | None = None
    allow_paid: bool | None = None
    openrouter_api_key: str | None = None
    gemini_api_key: str | None = None


# ---------------------------------------------------------------------------
# Trade Thesis & Invalidation Auditor Schemas
# ---------------------------------------------------------------------------

class AITradeValidationRequest(BaseModel):
    symbol: str = "NIFTY"
    timeframe: str = "15m"
    direction: Literal["BUY", "SELL"] = "BUY"
    entry_price: float
    stop_loss: float
    target_price: float
    thesis_notes: str | None = None
    provider: str = "openrouter"
    model: str | None = None
    allow_paid: bool | None = None
    openrouter_api_key: str | None = None
    gemini_api_key: str | None = None


class AITradeValidationResponse(BaseModel):
    symbol: str
    decision: Literal["CONFIRM", "REJECT", "WATCH", "UNCERTAIN"]
    score: int = Field(ge=0, le=100, description="Quality score 0-100")
    risk_reward_calculated: float
    technical_alignment: str
    derivatives_alignment: str
    volatility_regime_check: str
    invalidation_conditions: list[str] = []
    warning_traps: list[str] = []
    executive_verdict: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    provider_used: str = "openrouter"


# ---------------------------------------------------------------------------
# Daily Market Briefings
# ---------------------------------------------------------------------------

class AIDailyBriefingResponse(BaseModel):
    symbol: str
    session_type: Literal["PRE_MARKET", "POST_MARKET", "INTRADAY_UPDATE"]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    executive_summary: str
    key_levels_to_watch: dict[str, Any]
    options_pin_and_pivots: str
    fii_dii_implication: str
    actionable_playbook: list[str] = []
    provider_used: str = "openrouter"
