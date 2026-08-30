from pydantic import BaseModel, Field
from datetime import datetime
from typing import Literal
from enum import Enum


class DataStatus(str, Enum):
    LIVE = "LIVE"
    STALE = "STALE"
    DEMO = "DEMO"
    DISCONNECTED = "DISCONNECTED"
    ERROR = "ERROR"


class MarketSession(str, Enum):
    PRE_OPEN = "PRE_OPEN"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    POST_CLOSE = "POST_CLOSE"


class NormalizedQuote(BaseModel):
    """Normalized market quote — provider-independent."""
    symbol: str
    display_name: str
    timestamp: datetime
    ltp: float
    open: float
    high: float
    low: float
    previous_close: float
    change: float
    change_percent: float
    volume: int
    open_interest: int | None = None  # None when not applicable (e.g., VIX)
    status: DataStatus = DataStatus.DEMO
    provider: str = "fyers"


class NormalizedCandle(BaseModel):
    """Normalized OHLCV candle."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float | None = None


class NormalizedOptionQuote(BaseModel):
    """Normalized option quote — for future phases."""
    timestamp: datetime
    provider: str
    instrument: str
    contract_id: str
    underlying: str
    expiry: datetime
    strike: float
    option_type: Literal["CE", "PE"]
    ltp: float
    bid: float | None = None
    ask: float | None = None
    volume: int = 0
    oi: int = 0


class IndexCard(BaseModel):
    """Dashboard index card data."""
    symbol: str
    display_name: str
    ltp: float
    change: float
    change_percent: float
    open: float
    high: float
    low: float
    previous_close: float
    volume: int
    open_interest: int | None = None
    sparkline: list[float] = Field(default_factory=list)
    status: DataStatus = DataStatus.DEMO
    timestamp: datetime | None = None
    provider: str = "fyers"


class MarketBreadthData(BaseModel):
    """Market breadth statistics."""
    advancing: int
    declining: int
    unchanged: int
    advance_decline_ratio: float
    sectors: list["SectorBreadth"] = Field(default_factory=list)
    sentiment: Literal["VERY_BEARISH", "BEARISH", "NEUTRAL", "BULLISH", "VERY_BULLISH"] = "NEUTRAL"
    sentiment_score: float = 50.0  # 0-100
    status: DataStatus = DataStatus.DEMO
    timestamp: datetime | None = None


class SectorBreadth(BaseModel):
    """Sector-level breadth data."""
    name: str
    change_percent: float
    advancing: int
    declining: int
    unchanged: int


class MarketHealthStatus(BaseModel):
    """Market data health information with full telemetry diagnostics (Section 72)."""
    status: Literal["HEALTHY", "DEGRADED", "UNHEALTHY"] = "HEALTHY"
    provider: str = "fyers"
    mode: Literal["DEMO", "LIVE"] = "DEMO"
    last_update: datetime | None = None
    data_age_seconds: float | None = None
    latency_ms: float | None = None  # None = not measurable
    active_instruments: int = 0
    reconnect_count: int = 0
    subscriptions: int = 0
    buffer_depth: int = 0
    dropped_events: int = 0
    circuit_breaker_state: str = "CLOSED"
    last_heartbeat: datetime | None = None
    message: str = ""


class MarketStatusResponse(BaseModel):
    """Overall market status."""
    session: MarketSession
    market_time: datetime
    is_trading_day: bool
    data_status: DataStatus
    provider: str


# API Response Envelope
class ApiMeta(BaseModel):
    """Standard API response metadata."""
    provider: str = "fyers"
    timestamp: datetime
    status: DataStatus = DataStatus.DEMO


class ApiResponse(BaseModel):
    """Standard API response envelope."""
    data: dict | list | None = None
    error: str | None = None
    meta: ApiMeta


# Update forward refs
MarketBreadthData.model_rebuild()
