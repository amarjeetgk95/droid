from datetime import datetime, timezone
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field
from app.models.market import DataStatus

# Strict symbol whitelist: Only Bitcoin (BTC) and Ethereum (ETH) pairs allowed
ALLOWED_CRYPTO_SYMBOLS: set[str] = {"BTCUSDT", "ETHUSDT", "ETHBTC"}


class OrderBookSequenceStatus(str, Enum):
    SYNCING = "SYNCING"
    ACTIVE = "ACTIVE"
    GAP_DETECTED = "GAP_DETECTED"
    STALE = "STALE"
    DISCONNECTED = "DISCONNECTED"


class BasisStatus(str, Enum):
    CONTANGO = "CONTANGO"
    BACKWARDATION = "BACKWARDATION"
    NEUTRAL = "NEUTRAL"


class RelativeStrengthStatus(str, Enum):
    ETH_OUTPERFORMING = "ETH_OUTPERFORMING"
    BTC_OUTPERFORMING = "BTC_OUTPERFORMING"
    NEUTRAL = "NEUTRAL"


class CryptoTicker(BaseModel):
    symbol: str
    asset: str
    display_name: str
    market_type: str = "spot"
    price: float
    bid_price: float | None = None
    ask_price: float | None = None
    bid_size: float | None = None
    ask_size: float | None = None
    change_24h: float
    change_percent_24h: float
    high_24h: float
    low_24h: float
    volume_24h_base: float
    volume_24h_quote: float
    vwap: float | None = None
    trade_count: int | None = None
    spread: float | None = None
    spread_percent: float | None = None
    basis_pts: float | None = None
    high_low_spread_pct: float | None = None
    sparkline: list[float] = Field(default_factory=list)
    source_timestamp: datetime | None = None
    received_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data_age_ms: int = 0
    status: DataStatus = DataStatus.LIVE
    provider: str = "binance"
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CryptoOrderBookLevel(BaseModel):
    price: float
    quantity: float
    notional: float
    cumulative_quantity: float = 0.0
    cumulative_notional: float = 0.0


class CryptoOrderBook(BaseModel):
    symbol: str
    market_type: str = "spot"
    bids: list[CryptoOrderBookLevel]
    asks: list[CryptoOrderBookLevel]
    best_bid: float
    best_ask: float
    mid_price: float
    spread: float
    spread_percent: float
    bid_depth_total: float = 0.0
    ask_depth_total: float = 0.0
    depth_imbalance: float = 0.0
    depth_imbalance_pct: float = 0.0
    snapshot_id: int | None = None
    last_update_id: int | None = None
    event_timestamp: datetime | None = None
    received_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data_age_ms: int = 0
    sequence_status: OrderBookSequenceStatus = OrderBookSequenceStatus.ACTIVE
    status: DataStatus = DataStatus.LIVE
    provider: str = "binance"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CryptoDerivatives(BaseModel):
    symbol: str
    mark_price: float
    index_price: float
    spot_price: float | None = None
    basis: float = 0.0
    basis_percent: float = 0.0
    basis_status: BasisStatus = BasisStatus.NEUTRAL
    funding_rate: float
    funding_rate_percent: float
    annualized_funding_rate: float
    next_funding_time: datetime
    countdown_seconds: int
    open_interest_usd: float
    open_interest_coins: float
    long_short_ratio: float
    long_percentage: float
    short_percentage: float
    top_traders_long_short_ratio: float | None = None
    status: DataStatus = DataStatus.LIVE
    provider: str = "binance_futures"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CryptoPairComparison(BaseModel):
    eth_btc_ratio: float
    eth_btc_change_24h: float
    eth_btc_change_percent_24h: float
    btc_price: float
    btc_change_percent_24h: float
    eth_price: float
    eth_change_percent_24h: float
    performance_spread_24h: float
    relative_strength: RelativeStrengthStatus
    relative_volume_ratio: float
    status: DataStatus = DataStatus.LIVE
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CryptoMarketOverview(BaseModel):
    fear_greed_score: int
    fear_greed_label: str
    btc_dominance_pct: float
    eth_dominance_pct: float
    total_market_cap_usd: float
    combined_volume_24h_usd: float
    eth_btc_ratio: float
    tracked_pairs_count: int = 2
    top_assets: list[CryptoTicker] = Field(default_factory=list)
    top_gainers: list[CryptoTicker] = Field(default_factory=list)
    top_losers: list[CryptoTicker] = Field(default_factory=list)
    status: DataStatus = DataStatus.LIVE
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    provider: str = "binance"


class CryptoHealthResponse(BaseModel):
    btc: dict[str, str]
    eth: dict[str, str]
    websocket: str
    last_update_ms: int
    overall_status: str


class SignalDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class CryptoSignalStatus(str, Enum):
    ACTIVE = "ACTIVE"
    TRIGGERED = "TRIGGERED"
    TARGET_HIT = "TARGET_HIT"
    STOPPED_OUT = "STOPPED_OUT"
    EXPIRED = "EXPIRED"


class CryptoSignal(BaseModel):
    id: str
    symbol: str
    asset: str
    direction: SignalDirection
    strategy: str
    strategy_name: str
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    current_price: float
    risk_reward_ratio: float
    confidence: float
    timeframe: str = "1H"
    status: CryptoSignalStatus = CryptoSignalStatus.ACTIVE
    confluence_factors: list[str] = Field(default_factory=list)
    rationale: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CryptoSignalsResponse(BaseModel):
    signals: list[CryptoSignal]
    total_active: int
    btc_signals: int
    eth_signals: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
