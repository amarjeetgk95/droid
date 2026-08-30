from datetime import datetime
from pydantic import BaseModel, Field
from app.models.market import DataStatus


class CryptoTicker(BaseModel):
    symbol: str
    display_name: str
    base_asset: str
    quote_asset: str
    price: float
    change_24h: float
    change_percent_24h: float
    high_24h: float
    low_24h: float
    volume_24h_quote: float
    volume_24h_base: float
    weighted_avg_price: float | None = None
    sparkline: list[float] = Field(default_factory=list)
    status: DataStatus = DataStatus.LIVE
    provider: str = "binance"
    last_updated: datetime


class CryptoOrderBookLevel(BaseModel):
    price: float
    quantity: float
    total: float


class CryptoOrderBook(BaseModel):
    symbol: str
    bids: list[CryptoOrderBookLevel]
    asks: list[CryptoOrderBookLevel]
    spread: float
    spread_percent: float
    timestamp: datetime
    provider: str = "binance"


class CryptoDerivatives(BaseModel):
    symbol: str
    mark_price: float
    index_price: float
    estimated_settle_price: float | None = None
    funding_rate: float
    funding_rate_percent: float
    next_funding_time: datetime
    open_interest_usd: float
    open_interest_coins: float
    long_short_ratio: float
    long_percentage: float
    short_percentage: float
    countdown_seconds: int
    provider: str = "binance_futures"
    timestamp: datetime


class CryptoMarketOverview(BaseModel):
    fear_greed_score: int
    fear_greed_label: str
    btc_dominance_pct: float
    total_market_cap_usd: float
    total_volume_24h_usd: float
    tracked_pairs_count: int
    top_gainers: list[CryptoTicker]
    top_losers: list[CryptoTicker]
    timestamp: datetime
    provider: str = "binance"
