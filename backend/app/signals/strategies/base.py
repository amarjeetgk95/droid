"""
Base Protocol and Domain Models for the 13-key Strategy Portfolio (P1 overhaul).

Active scan portfolio: 11 strategies (6 intraday + 5 scalp) + 1 alias
(BREAKOUT -> VOLATILITY_BREAKOUT, same instance) = 12 keys in
STRATEGY_REGISTRY.  EMA_RIBBON is demoted: importable for back-compat but
disabled by default and NOT auto-scanned.

Shared P1 thresholds (single source of truth):
  - ADX trend cutoff: 22.0 (all strategies)
  - Volume: 1.5x micro/momentum & breakout, 1.3x ORB, 1.2x other 1M scalps
  - PCR: bull <= 0.80, bear >= 1.20
All detectors are fail-closed: missing inputs return None, never synthetic defaults.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Literal, Protocol, Any, Optional
from pydantic import BaseModel, Field
from app.signals.contract_resolver import InstrumentMaster

StrategyName = Literal[
    "BREAKOUT",
    "VOLATILITY_BREAKOUT",
    "MEAN_REVERSION",
    "TREND_PULLBACK",
    "REGIME_ADAPTIVE_TREND",
    "GAMMA_SQUEEZE",
    "ORB",
    "VWAP_SCALP",
    "LIQUIDITY_SWEEP_RECLAIM",
    "MICRO_MOMENTUM",
    "MOMENTUM_REACCELERATION",
    "EMA_RIBBON",
    "GAMMA_SPIKE",
]
TradeDirection = Literal["LONG_CALL", "LONG_PUT"]
Timeframe = Literal["1M", "3M", "5M", "15M", "1H", "1D"]
SignalType = Literal["SCALP", "INTRADAY", "SWING"]

# ── P1 shared thresholds (single source of truth) ──
ADX_TREND_CUTOFF: float = 22.0
VOLUME_MICRO_MIN: float = 1.5
VOLUME_BREAKOUT_MIN: float = 1.5
VOLUME_ORB_MIN: float = 1.3
VOLUME_SCALP_MIN: float = 1.2
PCR_BULL_MAX: float = 0.80
PCR_BEAR_MIN: float = 1.20


def extract_volume_ratio(indicators: dict[str, Any]) -> Optional[float]:
    """Fail-closed volume-ratio extractor. Returns None when not measured.

    No synthetic default: callers must return None (fail closed) when this
    returns None.
    """
    if not isinstance(indicators, dict):
        return None
    raw = indicators.get("volume_ratio")
    if raw is None:
        vol = indicators.get("volume")
        if isinstance(vol, dict):
            raw = vol.get("relative_volume", vol.get("ratio"))
    if raw is None:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if val <= 0:
        return None
    return val


def extract_breakout_pressure(indicators: dict[str, Any]) -> Optional[float]:
    """Fail-closed breakout-pressure extractor. None when not computed."""
    if not isinstance(indicators, dict):
        return None
    raw = indicators.get("breakout_pressure")
    if raw is None:
        scores = indicators.get("scores")
        if isinstance(scores, dict):
            raw = scores.get("breakout_pressure")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def extract_adx(indicators: dict[str, Any]) -> Optional[float]:
    """Fail-closed ADX extractor. None when ADX not computed."""
    if not isinstance(indicators, dict):
        return None
    raw = indicators.get("adx")
    if raw is None:
        trend = indicators.get("trend")
        if isinstance(trend, dict):
            raw = trend.get("adx")
    if raw is None:
        mom = indicators.get("momentum")
        if isinstance(mom, dict):
            raw = mom.get("adx")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def has_closed_1m_candle(ctx: Any) -> bool:
    """True only when the 1M candle is closed with second-tick confirmation.

    In production the pipeline sets is_new_1m_candle=True on the 1M scan
    cadence (prior candle closed, new tick seen). Detectors must fail closed
    when this is False — no intrabar spot-touch scalps.
    """
    try:
        return bool(getattr(ctx, "is_new_1m_candle", False))
    except Exception:
        return False


class StrategyContext(BaseModel):
    model_config = {"extra": "allow"}

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
    fno_degraded: bool = False
    vwap_degraded: bool = False
    vwap_coverage_pct: float = 100.0
    feature_snapshot: Optional[Any] = None
    vix_percentile: Optional[float] = None
    lunch_session: bool = False
    pre_market_gap_pct: float = 0.0


class SignalCandidate(BaseModel):
    candidate_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    underlying: Literal["NIFTY", "BANKNIFTY", "SENSEX"]
    strategy: StrategyName
    direction: TradeDirection
    timeframe: Timeframe
    spot_price: Decimal
    fno_degraded: bool = False
    vwap_degraded: bool = False
    vwap_coverage_pct: float = 100.0
    vix_percentile: Optional[float] = None
    lunch_session: bool = False
    pre_market_gap_pct: float = 0.0

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
    overall_confidence: float = 78.0

    rationale: list[str] = Field(default_factory=list)
    option_contract: Optional[InstrumentMaster] = None

    # Options Intelligence, Expected Move & Economics Context (§40)
    greeks: Optional[dict[str, Any]] = None
    expected_move: Optional[dict[str, Any]] = None
    ai_research: Optional[dict[str, Any]] = None
    path_simulation: Optional[dict[str, Any]] = None
    context_snapshot: dict[str, Any] = Field(default_factory=dict)
    
    # Orthogonal Confluence & Net Edge (§23, §27)
    confluence_factors: list[str] = Field(default_factory=list)
    participation: Optional[dict[str, Any]] = None
    net_edge: Optional[float] = None

    created_at_utc: int = Field(default_factory=lambda: int(__import__("time").time() * 1000))
    strategy_version: str = "v6.0"


class Strategy(Protocol):
    name: StrategyName

    def detect(self, ctx: StrategyContext) -> Optional[SignalCandidate]:
        """Detect if quantitative strategy conditions are satisfied."""
        ...
