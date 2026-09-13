"""
Domain models and data contracts for Droid Swing Trading Module (v5.0).
Strict, typed, deterministic structures for swing research and execution.
"""
from __future__ import annotations

import uuid
import time
from datetime import datetime, timezone
from typing import Literal, Any, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums & Literals
# ---------------------------------------------------------------------------
SwingStrategyType = Literal[
    "VCP_BREAKOUT",
    "TREND_PULLBACK_20EMA",
    "STAGE2_BREAKOUT",
]

MarketRegimeType = Literal[
    "BULL",
    "NEUTRAL",
    "DISTRIBUTION",
    "BEAR",
    "HIGH_VOLATILITY",
    "DATA_UNCERTAIN",
]

SectorStatusType = Literal[
    "LEADING",
    "IMPROVING",
    "NEUTRAL",
    "WEAKENING",
    "LAGGING",
]

SignalStateType = Literal[
    "WATCH",          # Setup forming, on radar
    "READY",          # Conditions met, awaiting price trigger
    "TRIGGERED",      # Price breached trigger in valid entry zone
    "ENTERED",        # Position active in portfolio
    "PARTIAL_EXIT",   # T1 reached, partial locked, remainder trailing
    "TRAILING",       # Trailing stop active
    "EXITED",         # Closed at target or stop
    "INVALIDATED",    # Technical setup broken before trigger
    "EXPIRED",        # Did not trigger within validity window
    "ABSTAINED",      # Market/sector conditions forced non-execution
    "BLOCKED",        # Risk gate / sector concentration blocked entry
]

TrailingMethodType = Literal[
    "STRUCTURAL_PIVOT",
    "EMA_20",
    "THREE_DAY_LOW",
    "BREAK_EVEN",
    "ATR_TRAIL",
]


# ---------------------------------------------------------------------------
# Universe & Fundamentals
# ---------------------------------------------------------------------------
class UniverseItem(BaseModel):
    symbol: str
    display_name: str
    sector: str
    industry: Optional[str] = None
    fno_eligible: bool = True
    lot_size: int = 1
    avg_volume_20d: int = 0
    avg_turnover_cr: float = 0.0
    beta: float = 1.0


# ---------------------------------------------------------------------------
# Market Regime & Sector Strength
# ---------------------------------------------------------------------------
class MarketRegime(BaseModel):
    regime: MarketRegimeType = "NEUTRAL"
    confidence: float = 50.0
    persistence_bars: int = 0
    benchmark_symbol: str = "NIFTY"
    benchmark_price: float = 0.0
    benchmark_change_pct: float = 0.0
    ma_alignment_score: float = 50.0  # % above moving averages
    recent_drawdown_pct: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    timestamp: int = Field(default_factory=lambda: int(time.time()))


class SectorClassification(BaseModel):
    sector: str
    trend: SectorStatusType = "NEUTRAL"
    relative_strength: float = 50.0  # vs NIFTY
    return_20d_pct: float = 0.0
    leading_stocks: list[str] = Field(default_factory=list)
    timestamp: int = Field(default_factory=lambda: int(time.time()))


# ---------------------------------------------------------------------------
# Setup Scoring (Deterministic 0-100)
# ---------------------------------------------------------------------------
class SetupScoreBreakdown(BaseModel):
    trend: float = Field(default=0.0, ge=0.0, le=20.0)             # 0-20
    structure: float = Field(default=0.0, ge=0.0, le=15.0)         # 0-15
    volume: float = Field(default=0.0, ge=0.0, le=15.0)            # 0-15
    relative_strength: float = Field(default=0.0, ge=0.0, le=10.0) # 0-10
    sector: float = Field(default=0.0, ge=0.0, le=10.0)            # 0-10
    regime: float = Field(default=0.0, ge=0.0, le=15.0)            # 0-15
    risk_reward: float = Field(default=0.0, ge=0.0, le=10.0)       # 0-10
    liquidity: float = Field(default=0.0, ge=0.0, le=5.0)          # 0-5
    total: float = Field(default=0.0, ge=0.0, le=100.0)            # Sum 0-100
    score_is_probability: bool = False                             # Non-negotiable rule §11


# ---------------------------------------------------------------------------
# Swing Setup Specification
# ---------------------------------------------------------------------------
class SwingSetup(BaseModel):
    setup_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str
    sector: str
    strategy: SwingStrategyType
    direction: Literal["LONG"] = "LONG"
    score: SetupScoreBreakdown

    # Execution Levels
    entry_zone_min: float
    entry_zone_max: float
    trigger_price: float
    max_chase_price: float               # max 1.0% above trigger
    stop_price: float                    # effective stop
    structural_stop: float               # pivot low
    atr_floor: float                     # 1.2 x Daily ATR
    target_1: float                      # 1.5R target
    target_2: float                      # 3.0R target

    # Risk & Sizing Metrics
    risk_per_share: float
    risk_pct: float                      # (risk_per_share / trigger_price) * 100
    risk_reward_t1: float
    risk_reward_t2: float
    expected_holding_days: int = 7       # 2-20 days default window
    daily_atr: float = 0.0

    # Macro & Sector Context
    market_regime: MarketRegimeType = "NEUTRAL"
    sector_state: SectorStatusType = "NEUTRAL"

    # Explainability & Disqualification
    technical_reasons: list[str] = Field(default_factory=list)
    risk_reasons: list[str] = Field(default_factory=list)
    invalidation_rules: list[str] = Field(default_factory=list)

    # Lifecycle & Audit
    signal_state: SignalStateType = "WATCH"
    created_at_utc: int = Field(default_factory=lambda: int(time.time() * 1000))
    valid_until_utc: int = Field(default_factory=lambda: int((time.time() + 86400 * 5) * 1000))


# ---------------------------------------------------------------------------
# Active Position Tracking
# ---------------------------------------------------------------------------
class SwingPosition(BaseModel):
    position_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    setup_id: str
    symbol: str
    sector: str
    strategy: SwingStrategyType
    entry_price: float
    current_price: float
    quantity: int
    initial_stop: float
    current_stop: float
    trailing_method: TrailingMethodType = "STRUCTURAL_PIVOT"
    target_1: float
    target_2: float
    days_held: int = 0
    entered_at_utc: int = Field(default_factory=lambda: int(time.time() * 1000))
    unrealized_pnl: float = 0.0
    pnl_pct: float = 0.0
    r_multiple: float = 0.0
    status: Literal["OPEN", "PARTIALLY_CLOSED", "CLOSED"] = "OPEN"
    close_price: Optional[float] = None
    closed_at_utc: Optional[int] = None
    exit_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Portfolio & Risk State
# ---------------------------------------------------------------------------
class PortfolioRiskState(BaseModel):
    total_equity: float = 1_000_000.0
    open_capital: float = 0.0
    open_risk_capital: float = 0.0
    portfolio_heat_pct: float = 0.0
    max_heat_pct: float = 5.0            # Max 5% total open risk
    max_risk_per_trade_pct: float = 1.0  # Max 1% equity per trade
    max_positions_per_sector: int = 2    # Prevent 5-bank cluster
    sector_allocations: dict[str, int] = Field(default_factory=dict)
    open_positions_count: int = 0
    max_positions_count: int = 6
