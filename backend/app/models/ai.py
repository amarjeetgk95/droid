from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

MarketBias = Literal["BULLISH", "BEARISH", "NEUTRAL", "VOLATILE"]


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
    provider_used: str = "mock_ai"


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
