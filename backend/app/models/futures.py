from typing import Literal
from pydantic import BaseModel, Field

CurveState = Literal["CONTANGO", "BACKWARDATION", "FLAT"]
BuildupType = Literal["LONG_BUILDUP", "SHORT_BUILDUP", "LONG_UNWINDING", "SHORT_COVERING"]
BuildupStrength = Literal["STRONG", "MODERATE", "WEAK"]
RolloverPace = Literal["AHEAD", "IN_LINE", "BEHIND"]
FuturesTenor = Literal["NEAR", "NEXT", "FAR"]


class FuturesContractItem(BaseModel):
    """Normalized Futures contract metrics and carrying cost."""
    symbol: str
    instrument_token: str | None = None
    expiry: str
    tenor: FuturesTenor
    ltp: float
    change: float
    change_percent: float
    open: float
    high: float
    low: float
    volume: int
    open_interest: int
    oi_change: int
    oi_change_percent: float
    basis: float = Field(description="Futures LTP - Spot Price")
    basis_percent: float
    cost_of_carry_percent: float = Field(description="Annualized Cost of Carry %")
    fair_value: float = Field(description="Theoretical Cost-of-Carry Fair Price")
    fair_value_spread: float = Field(description="Actual LTP - Fair Value")
    days_to_expiry: float


class TermStructureCurve(BaseModel):
    """Futures term structure across near, next, and far expiries."""
    underlying: str
    spot_price: float
    curve_state: CurveState
    contracts: list[FuturesContractItem] = Field(default_factory=list)
    calendar_spread_next_near: float = Field(description="Next Month - Near Month Spread")
    calendar_spread_far_next: float = Field(description="Far Month - Next Month Spread")


class OIBuildupItem(BaseModel):
    """4-Quadrant Open Interest Buildup classification."""
    symbol: str
    underlying: str
    ltp: float
    price_change: float
    price_change_percent: float
    open_interest: int
    oi_change: int
    oi_change_percent: float
    buildup_type: BuildupType
    interpretation: str
    strength: BuildupStrength


class RolloverMetrics(BaseModel):
    """Rollover percentage, spread cost, and benchmark pace."""
    underlying: str
    expiry: str
    rollover_percent: float = Field(description="(Next OI + Far OI) / Total OI * 100")
    rollover_spread: float = Field(description="Next Month - Near Month Price Difference")
    three_month_avg_rollover: float = Field(default=72.5)
    rollover_pace: RolloverPace = "IN_LINE"
    total_futures_oi: int


class FuturesOverview(BaseModel):
    """Composite Futures analytics overview."""
    underlying: str
    spot_price: float
    term_structure: TermStructureCurve
    buildup: OIBuildupItem
    rollover: RolloverMetrics
    all_tracked_buildups: list[OIBuildupItem] = Field(default_factory=list)
