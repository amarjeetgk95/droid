from typing import Literal
from pydantic import BaseModel, Field

StrategyCategory = Literal["DIRECTIONAL", "NON_DIRECTIONAL", "VOLATILITY", "ASYMMETRIC"]
MarketOutlook = Literal["BULLISH", "BEARISH", "NEUTRAL", "HIGH_VOLATILITY"]
LegSide = Literal["BUY", "SELL"]
OptionType = Literal["CE", "PE"]


class StrategyLegModel(BaseModel):
    """Single leg within a multi-leg options strategy."""
    id: str = Field(default="", description="Unique leg identifier")
    option_type: OptionType
    side: LegSide
    strike: float
    quantity: int = Field(default=1, description="Quantity in number of lots")
    price: float = Field(description="Entry premium per unit")
    iv: float = Field(default=0.15, description="Implied Volatility (e.g. 0.15)")
    expiry: str = Field(description="Expiry date YYYY-MM-DD")
    lot_size: int = Field(default=75, description="Lot size (e.g. 75 for NIFTY)")


class StrategyPayload(BaseModel):
    """Payload to evaluate a custom multi-leg strategy."""
    underlying: str = "NIFTY"
    legs: list[StrategyLegModel]
    spot_price: float | None = None
    expiry: str | None = None


class PayoffPointModel(BaseModel):
    """Single spot-price evaluation node on the dual-curve payoff."""
    spot_price: float
    expiry_pnl: float
    t0_pnl: float


class StrategyPayoffResult(BaseModel):
    """Complete payoff simulation and risk metrics."""
    underlying: str
    spot_price: float
    net_premium: float
    premium_type: Literal["DEBIT", "CREDIT"]
    max_profit: float | None = Field(default=None, description="Max Profit in ₹ (None if Unlimited)")
    max_loss: float | None = Field(default=None, description="Max Loss in ₹ (None if Unlimited)")
    breakevens: list[float]
    risk_reward_ratio: float | None = None
    pop_percent: float = Field(description="Probability of Profit (0-100%)")
    net_delta: float
    net_gamma: float
    net_theta: float
    net_vega: float
    payoff_curve: list[PayoffPointModel]
    legs: list[StrategyLegModel]


class StrategyTemplate(BaseModel):
    """Pre-built institutional options strategy blueprint."""
    id: str
    name: str
    category: StrategyCategory
    outlook: MarketOutlook
    description: str
    legs_description: list[str]


class ScannedStrategy(BaseModel):
    """Opportunity discovered by the Strategy Scanner."""
    id: str
    name: str
    underlying: str
    category: StrategyCategory
    outlook: MarketOutlook
    net_premium: float
    premium_type: Literal["DEBIT", "CREDIT"]
    max_profit: float | None
    max_loss: float | None
    pop_percent: float
    risk_reward_ratio: float | None
    breakevens: list[float]
    legs: list[StrategyLegModel]
