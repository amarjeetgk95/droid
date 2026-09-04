"""
Base Protocol and Domain Models for the 5 Institutional Quant Strategies.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Literal, Protocol, Any, Optional
from pydantic import BaseModel, Field
from app.signals.contract_resolver import InstrumentMaster

StrategyName = Literal[
    "BREAKOUT",
    "MEAN_REVERSION",
    "TREND_PULLBACK",
    "GAMMA_SQUEEZE",
    "ORB",
    "VWAP_SCALP",
    "MICRO_MOMENTUM",
    "EMA_RIBBON",
    "GAMMA_SPIKE",
]
TradeDirection = Literal["LONG_CALL", "LONG_PUT"]
Timeframe = Literal["1M", "3M", "5M", "15M", "1H", "1D"]
SignalType = Literal["SCALP", "INTRADAY", "SWING"]


class StrategyContext(BaseModel):
    underlying: Literal["NIFTY", "BANKNIFTY", "SENSEX"]
    spot_price: Decimal
    timeframe: Timeframe = "5M"
    indicators: dict[str, Any] = Field(default_factory=dict)
    mtf: dict[str, Any] = Field(default_factory=dict)
    fno: dict[str, Any] = Field(default_factory=dict)
    regime: str = "RANGE"  # TREND_UP, TREND_DOWN, RANGE, HIGH_VOL, LOW_VOL, EVENT
    session_state: str = "OPEN"
    timestamp_ms: int = Field(default_factory=lambda: int(__import__("time").time() * 1000))
    candles: list[dict] = Field(default_factory=list)
    vwap: Optional[Decimal] = None
    volume_ma_20: Optional[float] = None
    is_new_1m_candle: bool = False
    is_new_5m_candle: bool = False


class SignalCandidate(BaseModel):
    candidate_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    underlying: Literal["NIFTY", "BANKNIFTY", "SENSEX"]
    strategy: StrategyName
    direction: TradeDirection
    timeframe: Timeframe
    spot_price: Decimal

    # Desk & Classification
    signal_type: SignalType = "INTRADAY"
    is_scalp: bool = False

    # Levels
    entry_min: Decimal
    entry_max: Decimal
    trigger: Decimal
    stop_loss: Decimal
    target_1: Decimal
    target_2: Decimal

    # Metrics
    risk_points: Decimal
    risk_reward_t1: float
    risk_reward_t2: float
    max_chase_fraction: float = 0.50

    # Two-Clock Lifecycles (§6)
    ttl_seconds: int = 300
    time_stop_seconds: Optional[int] = None
    runner_ttl_seconds: Optional[int] = None

    # Confluence sub-scores (0-100)
    technical_score: float = 50.0
    mtf_score: float = 50.0
    fno_score: float = 50.0
    regime_score: float = 50.0
    ai_score: Optional[float] = None
    overall_confidence: float = 75.0

    rationale: list[str] = Field(default_factory=list)
    option_contract: Optional[InstrumentMaster] = None
    created_at_utc: int = Field(default_factory=lambda: int(__import__("time").time() * 1000))
    strategy_version: str = "v6.0"


class Strategy(Protocol):
    name: StrategyName

    def detect(self, ctx: StrategyContext) -> Optional[SignalCandidate]:
        """Detect if quantitative strategy conditions are satisfied."""
        ...
