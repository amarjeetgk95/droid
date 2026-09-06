"""Enums for the Chart Intelligence & Indicator Research Laboratory."""

from enum import Enum


class IndicatorCategory(str, Enum):
    STANDARD = "STANDARD"
    STRUCTURAL = "STRUCTURAL"
    DERIVATIVE = "DERIVATIVE"
    PROPRIETARY = "PROPRIETARY"
    EXPERIMENTAL = "EXPERIMENTAL"


class IndicatorLifecycle(str, Enum):
    EXPERIMENTAL = "EXPERIMENTAL"
    VALIDATING = "VALIDATING"
    CANDIDATE = "CANDIDATE"
    COMPARISON = "COMPARISON"
    INCUBATION = "INCUBATION"
    SHADOW = "SHADOW"
    PRODUCTION = "PRODUCTION"
    RETIRED = "RETIRED"


class Direction(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"


class ForecastHorizon(str, Enum):
    HORIZON_5M = "5m"
    HORIZON_15M = "15m"
    HORIZON_30M = "30m"
    HORIZON_1H = "1h"
    HORIZON_4H = "4h"
    HORIZON_NEXT_DAY = "NEXT_DAY"


class MarketSession(str, Enum):
    OPENING = "OPENING"     # 09:15 - 09:45
    EARLY = "EARLY"         # 09:45 - 11:30
    MID = "MID"             # 11:30 - 13:30
    LATE = "LATE"           # 13:30 - 15:00
    CLOSING = "CLOSING"     # 15:00 - 15:30
    CLOSED = "CLOSED"


class ExpiryBucket(str, Enum):
    EXPIRY_DAY = "EXPIRY_DAY"
    DTE_1 = "1DTE"
    DTE_2_3 = "2_3DTE"
    DTE_4_7 = "4_7DTE"
    DTE_GT_7 = "GT_7DTE"


class DataQualityStatus(str, Enum):
    LIVE = "LIVE"
    DEGRADED = "DEGRADED"
    STALE = "STALE"
    FAILED = "FAILED"
    EMPTY = "EMPTY"
    UNKNOWN = "UNKNOWN"


class MarketRegime(str, Enum):
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    RANGING = "RANGING"
    VOLATILE = "VOLATILE"
    COMPRESSING = "COMPRESSING"
    UNKNOWN = "UNKNOWN"


class ExperimentStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
