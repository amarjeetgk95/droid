from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class OptionGreeks(BaseModel):
    """Institutional-grade analytical option Greeks."""
    delta: float = Field(description="Spot Delta (-1 to +1)")
    gamma: float = Field(description="Gamma")
    theta: float = Field(description="Normalized Theta (per calendar day)")
    vega: float = Field(description="Normalized Vega (per 1% IV)")
    rho: float = Field(description="Normalized Rho (per 1% rate change)")
    iv: float | None = Field(default=None, description="Implied Volatility (e.g. 0.15 = 15%)")
    theoretical_price: float = Field(description="Theoretical model price")
    intrinsic_value: float = Field(description="Intrinsic value")
    time_value: float = Field(description="Extrinsic time value")


class OptionSide(BaseModel):
    """Call (CE) or Put (PE) leg at a specific strike."""
    symbol: str
    instrument_token: str | None = None
    ltp: float
    change: float = 0.0
    change_percent: float = 0.0
    volume: int = 0
    open_interest: int = 0
    oi_change: int = 0
    bid: float | None = None
    ask: float | None = None
    is_itm: bool = False
    greeks: OptionGreeks | None = None


class OptionChainStrikeRow(BaseModel):
    """Single strike row in the Option Chain ladder."""
    strike: float
    is_atm: bool = False
    call: OptionSide | None = None
    put: OptionSide | None = None


class OptionsAnalytics(BaseModel):
    """Composite options analytics and sentiment indicators."""
    symbol: str
    spot_price: float
    futures_price: float
    expiry: str
    atm_strike: float
    atm_iv: float | None = None
    pcr_oi: float = 1.0
    pcr_volume: float = 1.0
    max_pain_strike: float
    total_call_oi: int = 0
    total_put_oi: int = 0
    total_call_volume: int = 0
    total_put_volume: int = 0
    iv_skew: float | None = None
    time_to_expiry_days: float = 0.0
    risk_free_rate: float = 0.0675
    rate_source: str = "IN_SOVEREIGN_BENCHMARK_6.75_FALLBACK"


class OptionChainResponse(BaseModel):
    """Complete interactive Option Chain payload."""
    underlying: str
    spot_price: float
    futures_price: float
    expiry: str
    expiries: list[str] = Field(default_factory=list)
    analytics: OptionsAnalytics
    strikes: list[OptionChainStrikeRow] = Field(default_factory=list)


class MaxPainResult(BaseModel):
    """Max Pain analysis payout curve."""
    symbol: str
    expiry: str
    max_pain_strike: float
    total_loss_at_max_pain: float
    strikes: list[float] = Field(default_factory=list)
    payouts: list[float] = Field(default_factory=list)
