from datetime import datetime, timezone
from typing import Literal, Any
from pydantic import BaseModel, Field, field_validator

MarketBias = Literal["BULLISH", "BEARISH", "NEUTRAL", "VOLATILE"]
AIChatRole = Literal["system", "user", "assistant", "tool"]


def coerce_to_text(v: Any) -> str:
    """Coerce any LLM output (dict, list, int, etc.) into a clean human-readable text string."""
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, list):
        items = []
        for item in v:
            text = coerce_to_text(item).strip()
            if text:
                if not text.startswith(("-", "•", "*", "1.", "2.", "3.", "4.", "5.")):
                    items.append(f"• {text}")
                else:
                    items.append(text)
        return "\n".join(items)
    if isinstance(v, dict):
        lines = []
        for k, val in v.items():
            label = str(k).replace("_", " ").strip().title()
            if isinstance(val, (dict, list)):
                sub_text = coerce_to_text(val).strip()
                lines.append(f"{label}:\n{sub_text}")
            else:
                lines.append(f"{label}: {val}")
        return "\n".join(lines)
    return str(v)


def coerce_to_string_list(v: Any) -> list[str]:
    """Coerce any LLM output into a list of strings."""
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if x is not None and str(x).strip()]
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return []
        # If separated by newlines
        if "\n" in s:
            return [line.strip().lstrip("-*•0123456789. ") for line in s.splitlines() if line.strip()]
        return [s]
    if isinstance(v, dict):
        return [f"{str(k).replace('_', ' ').title()}: {val}" for k, val in v.items()]
    return [str(v)]


class AIInsightResponse(BaseModel):
    """Structured, explainable AI market intelligence report."""
    symbol: str = "NIFTY"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    market_bias: MarketBias = "NEUTRAL"
    confidence: float = Field(default=75.0, description="Confidence percentage (0-100%)")
    executive_summary: str = ""
    # Plain-language 2-3 sentence takeaway for non-expert readers. Empty when
    # the model predates this field — frontend falls back to executive_summary.
    simple_takeaway: str = ""
    options_interpretation: str = ""
    futures_flow_analysis: str = ""
    regime_and_levels: str = ""
    recommended_strategy_framework: str = ""
    risk_management_notes: str = ""
    disclaimer: str = Field(
        default="This AI analysis is strictly for quantitative research and education. It does not constitute financial advice or trade recommendations."
    )
    provider_used: str = "gemini"

    @field_validator(
        "executive_summary",
        "simple_takeaway",
        "options_interpretation",
        "futures_flow_analysis",
        "regime_and_levels",
        "recommended_strategy_framework",
        "risk_management_notes",
        "disclaimer",
        mode="before",
    )
    @classmethod
    def validate_text_fields(cls, v: Any) -> str:
        return coerce_to_text(v)

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, v: Any) -> float:
        if v is None:
            return 75.0
        if isinstance(v, str):
            v_clean = v.strip().replace("%", "")
            try:
                val = float(v_clean)
            except Exception:
                return 75.0
        elif isinstance(v, (int, float)):
            val = float(v)
        else:
            return 75.0

        if 0 < val <= 1.0:
            val = val * 100.0
        return max(0.0, min(100.0, val))

    @field_validator("market_bias", mode="before")
    @classmethod
    def validate_market_bias(cls, v: Any) -> str:
        if not v:
            return "NEUTRAL"
        v_str = str(v).strip().upper()
        if v_str in ("BULLISH", "BEARISH", "NEUTRAL", "VOLATILE"):
            return v_str
        if "BULL" in v_str or "BUY" in v_str or "LONG" in v_str:
            return "BULLISH"
        if "BEAR" in v_str or "SELL" in v_str or "SHORT" in v_str:
            return "BEARISH"
        if "VOLATIL" in v_str or "CHOP" in v_str or "WAIT" in v_str:
            return "VOLATILE"
        return "NEUTRAL"


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

    @field_validator("strategy_name", "market_outlook", "rationale", "risk_management", mode="before")
    @classmethod
    def validate_text(cls, v: Any) -> str:
        return coerce_to_text(v)

    @field_validator("entry_rules", "exit_rules", mode="before")
    @classmethod
    def validate_lists(cls, v: Any) -> list[str]:
        return coerce_to_string_list(v)


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

    @field_validator("technical_alignment", "derivatives_alignment", "volatility_regime_check", "executive_verdict", mode="before")
    @classmethod
    def validate_text(cls, v: Any) -> str:
        return coerce_to_text(v)

    @field_validator("invalidation_conditions", "warning_traps", mode="before")
    @classmethod
    def validate_lists(cls, v: Any) -> list[str]:
        return coerce_to_string_list(v)


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

    @field_validator("executive_summary", "options_pin_and_pivots", "fii_dii_implication", mode="before")
    @classmethod
    def validate_text(cls, v: Any) -> str:
        return coerce_to_text(v)

    @field_validator("actionable_playbook", mode="before")
    @classmethod
    def validate_lists(cls, v: Any) -> list[str]:
        return coerce_to_string_list(v)
