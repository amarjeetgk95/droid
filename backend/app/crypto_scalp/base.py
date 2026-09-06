"""
Crypto Scalping Engine — Core Abstractions & Data Structures
Independent from Indian index F&O structures. Tailored for 24/7 crypto spot & perpetual markets.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable
from pydantic import BaseModel, Field, ConfigDict

from app.models.crypto import (
    SignalDirection,
    CryptoOrderBook,
    CryptoDerivatives,
)
from app.models.market import NormalizedCandle


def calc_ema(values: list[float], period: int) -> float:
    """Calculate Exponential Moving Average over a price series."""
    if not values:
        return 0.0
    if len(values) < period:
        return sum(values) / len(values)
    
    multiplier = 2.0 / (period + 1)
    # Start with SMA of first `period` items
    ema = sum(values[:period]) / period
    for val in values[period:]:
        ema = (val - ema) * multiplier + ema
    return round(ema, 4)


def calc_atr(candles: list[NormalizedCandle], period: int = 14) -> float:
    """Calculate Average True Range from NormalizedCandle bars."""
    if len(candles) < 2:
        return 0.0
    
    tr_list: list[float] = []
    for i in range(1, len(candles)):
        h = candles[i].high
        l = candles[i].low
        prev_c = candles[i - 1].close
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        tr_list.append(tr)
    
    if not tr_list:
        return 0.0
    if len(tr_list) < period:
        return round(sum(tr_list) / len(tr_list), 4)
    
    atr = sum(tr_list[:period]) / period
    for tr in tr_list[period:]:
        atr = (atr * (period - 1) + tr) / period
    return round(atr, 4)


def calc_vwap(candles: list[NormalizedCandle]) -> float:
    """Calculate Volume-Weighted Average Price across candles."""
    cum_vol = 0.0
    cum_pv = 0.0
    for c in candles:
        typical_price = (c.high + c.low + c.close) / 3.0
        cum_pv += typical_price * c.volume
        cum_vol += c.volume
    if cum_vol <= 0:
        return candles[-1].close if candles else 0.0
    return round(cum_pv / cum_vol, 4)


class CryptoScalpContext(BaseModel):
    """
    Rich market context for crypto scalping analysis.
    Built per symbol (BTCUSDT / ETHUSDT) on 1m/5m/15m timeframes.
    """
    symbol: str
    asset: str  # "BTC" or "ETH"
    current_price: float
    candles_1m: list[NormalizedCandle] = Field(default_factory=list)
    candles_5m: list[NormalizedCandle] = Field(default_factory=list)
    candles_15m: list[NormalizedCandle] = Field(default_factory=list)

    # Technical Indicators
    vwap_session: float = 0.0
    ema_9_1m: float = 0.0
    ema_21_1m: float = 0.0
    ema_50_1m: float = 0.0
    atr_14_1m: float = 0.0
    volume_surge_ratio: float = 1.0  # current bar volume / 20-period avg volume

    # High / Low price anchors for breakouts
    high_15m: float = 0.0
    low_15m: float = 0.0

    # L2 Order Book & Derivatives (optional for pure TA, required for order flow strategies)
    orderbook: CryptoOrderBook | None = None
    derivatives: CryptoDerivatives | None = None
    eth_btc_ratio: float | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class CryptoScalpCandidate(BaseModel):
    """Candidate scalp signal emitted by a strategy before risk filtration."""
    symbol: str
    asset: str
    direction: SignalDirection
    strategy: str
    strategy_name: str
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    risk_points: float
    risk_percent: float
    risk_reward_ratio: float
    confidence: float
    timeframe: str = "1m"
    confluence_factors: list[str] = Field(default_factory=list)
    rationale: str
    atr_value: float | None = None
    volume_ratio: float | None = None
    funding_rate: float | None = None
    depth_imbalance: float | None = None


@runtime_checkable
class CryptoScalpStrategy(Protocol):
    """Protocol that all crypto scalping strategies must implement."""
    strategy_code: str
    name: str

    def detect(self, ctx: CryptoScalpContext) -> CryptoScalpCandidate | None:
        """Analyze context and return a CryptoScalpCandidate or None if conditions not met."""
        ...
