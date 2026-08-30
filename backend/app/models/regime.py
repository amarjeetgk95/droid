from typing import Literal
from pydantic import BaseModel, Field

MarketRegimeState = Literal[
    "TRENDING_BULLISH",
    "TRENDING_BEARISH",
    "RANGEBOUND_LOW_VOL",
    "RANGEBOUND_HIGH_VOL",
    "VOLATILE_EXPANSION",
    "COMPRESSION_SQUEEZE",
]

VixRegimeCategory = Literal[
    "LOW_VOLATILITY",
    "NORMAL_VOLATILITY",
    "ELEVATED_VOLATILITY",
    "EXTREME_VOLATILITY",
]


class TechnicalIndicators(BaseModel):
    """Institutional technical indicator metrics."""
    rsi_14: float = Field(description="14-period RSI (0-100)")
    adx_14: float = Field(description="14-period ADX trend strength (>25 trending)")
    plus_di: float
    minus_di: float
    atr_14: float = Field(description="Average True Range in points")
    supertrend_value: float
    supertrend_direction: Literal["BULLISH", "BEARISH"]
    bollinger_upper: float
    bollinger_middle: float
    bollinger_lower: float
    bollinger_bandwidth: float = Field(description="Bollinger Bandwidth %")
    bollinger_pct_b: float
    ema_20: float | None = None
    ema_50: float | None = None
    sma_200: float | None = None


class PivotSetModel(BaseModel):
    """Floor/Fibonacci/Camarilla pivot levels."""
    pivot: float
    r1: float
    r2: float
    r3: float
    r4: float | None = None
    s1: float
    s2: float
    s3: float
    s4: float | None = None


class KeyLevelsModel(BaseModel):
    """Multi-method Support and Resistance levels."""
    classic_pivots: PivotSetModel
    fibonacci_pivots: PivotSetModel
    camarilla_pivots: PivotSetModel
    prior_day_high: float
    prior_day_low: float
    prior_day_close: float
    day_open: float
    poc: float = Field(description="Volume Profile Point of Control")
    vah: float = Field(description="Value Area High (70% boundary)")
    val: float = Field(description="Value Area Low (70% boundary)")
    nearest_resistance: float
    nearest_support: float
    distance_to_resistance_pts: float
    distance_to_support_pts: float


class VixRegimeInfo(BaseModel):
    """India VIX Volatility classification and option strategy bias."""
    vix_value: float
    change: float
    change_percent: float
    regime_category: VixRegimeCategory
    interpretation: str
    recommended_option_strategy: str
    historical_percentile: float = Field(description="Historical percentile ranking (0-100)")


class MarketRegimeOverview(BaseModel):
    """Composite Market Regime and Technical Intelligence."""
    symbol: str
    spot_price: float
    regime_state: MarketRegimeState
    confidence_score: float = Field(description="Regime classification confidence (0-100%)")
    summary_headline: str
    institutional_rationale: str
    indicators: TechnicalIndicators
    key_levels: KeyLevelsModel
    vix_regime: VixRegimeInfo
