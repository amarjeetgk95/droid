"""
Domain models and data contracts for Droid Swing Trading Module (v6.0 Options Overhaul).
Strict, typed, deterministic structures for index options swing research and execution.
"""
from __future__ import annotations

import uuid
import time
from typing import Literal, Any, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums & Literals
# ---------------------------------------------------------------------------
HorizonType = Literal["POSITIONAL", "INTRADAY"]

SwingStrategyType = Literal[
    "TREND_BREAKOUT_CE",
    "TREND_BREAKOUT_PE",
    "PULLBACK_CE",
    "PULLBACK_PE",
    "STAGE2_CE",
    "STAGE2_PE",
    "IV_DIRECTIONAL",
    "INTRADAY_PULLBACK_CE",
    "INTRADAY_PULLBACK_PE",
    "INTRADAY_ORB_CE",
    "INTRADAY_ORB_PE",
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
    "ABSTAINED",      # Market conditions forced non-execution
    "BLOCKED",        # Risk gate / exposure ceiling blocked entry
    "THETA_WARNING",  # Excessive theta decay risk on open position
    "EXPIRY_WARNING", # Near-expiry risk (DTE <= 3)
]

StopMethod = Literal[
    "INITIAL",
    "BREAK_EVEN",
    "TRAILING_PREMIUM",
    "TIME_DECAY",
]

ExitReason = Literal[
    "UNDERLYING_STOP",
    "OPTION_STOP",
    "TARGET_1",
    "TARGET_2",
    "TRAILING_STOP",
    "THETA_DECAY",
    "EXPIRY_RISK",
    "IV_CRUSH",
    "LIQUIDITY_FAILURE",
    "PORTFOLIO_RISK",
    "REGIME_INVALIDATION",
    "MANUAL_EXIT",
]


# ---------------------------------------------------------------------------
# Trade Validity Gate (§6)
# ---------------------------------------------------------------------------
class TradeValidity(BaseModel):
    underlying_valid: bool = True
    option_valid: bool = True
    portfolio_valid: bool = True
    execution_valid: bool = True
    overall_valid: bool = True
    rejection_reasons: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Universe & Fundamentals
# ---------------------------------------------------------------------------
class UniverseItem(BaseModel):
    symbol: str
    display_name: str
    exchange: str = "NSE"
    fyers_symbol: str = ""
    fno_eligible: bool = True
    lot_size: int = 1
    strike_interval: float = 50.0
    tick_size: float = 0.05


# ---------------------------------------------------------------------------
# Market Regime & Volatility Environment
# ---------------------------------------------------------------------------
class MarketRegime(BaseModel):
    regime: MarketRegimeType = "NEUTRAL"
    # Fail-closed: None when unmeasured (UNVETTED/INSUFFICIENT_DATA), never 50.0.
    confidence: float | None = None
    confidence_status: str = "UNVETTED"
    persistence_bars: int = 0
    benchmark_symbol: str = "NIFTY"
    benchmark_price: float = 0.0
    benchmark_change_pct: float = 0.0
    ma_alignment_score: float | None = None
    ma_alignment_status: str = "INSUFFICIENT_DATA"
    recent_drawdown_pct: float = 0.0
    iv_percentile: float | None = None
    iv_percentile_status: str = "INSUFFICIENT_DATA"
    iv_regime: str = "UNKNOWN"         # LOW, NORMAL, ELEVATED, EXTREME, UNKNOWN
    reasons: list[str] = Field(default_factory=list)
    timestamp: int = Field(default_factory=lambda: int(time.time()))


class SectorClassification(BaseModel):
    sector: str
    trend: SectorStatusType = "NEUTRAL"
    # Fail-closed: None when unmeasured, never silent 50.0.
    relative_strength: float | None = None
    relative_strength_status: str = "INSUFFICIENT_DATA"
    return_20d_pct: float = 0.0
    leading_stocks: list[str] = Field(default_factory=list)
    timestamp: int = Field(default_factory=lambda: int(time.time()))


# ---------------------------------------------------------------------------
# Setup Scoring (Deterministic 0-100 Options Rubric)
# ---------------------------------------------------------------------------
class SetupScoreBreakdown(BaseModel):
    trend: float = Field(default=0.0, ge=0.0, le=15.0)             # 0-15 (Underlying MA stack)
    structure: float = Field(default=0.0, ge=0.0, le=10.0)         # 0-10 (VCP / Consolidation)
    volume: float = Field(default=0.0, ge=0.0, le=5.0)             # 0-5  (Volume confirmation)
    expected_move: float = Field(default=0.0, ge=0.0, le=10.0)     # 0-10 (Expected vs Implied move)
    iv_favorability: float = Field(default=0.0, ge=0.0, le=10.0)   # 0-10 (Low IV for long premium)
    greeks_quality: float = Field(default=0.0, ge=0.0, le=10.0)    # 0-10 (Delta sweet spot 0.50-0.70)
    theta_efficiency: float = Field(default=0.0, ge=0.0, le=5.0)   # 0-5  (Theta drag < 20%)
    liquidity: float = Field(default=0.0, ge=0.0, le=10.0)         # 0-10 (OI > threshold, tight spread)
    regime: float = Field(default=0.0, ge=0.0, le=5.0)             # 0-5  (Macro regime match)
    risk_reward: float = Field(default=0.0, ge=0.0, le=10.0)       # 0-10 (Premium R:R)
    portfolio_fit: float = Field(default=0.0, ge=0.0, le=5.0)      # 0-5  (Diversification / heat)
    dte_adequacy: float = Field(default=0.0, ge=0.0, le=5.0)       # 0-5  (DTE >= expected hold + 3)
    total: float = Field(default=0.0, ge=0.0, le=100.0)            # Sum 0-100
    score_is_probability: bool = False


# ---------------------------------------------------------------------------
# Swing Options Setup Specification
# ---------------------------------------------------------------------------
class SwingSetup(BaseModel):
    setup_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    underlying: str                      # "NIFTY", "BANKNIFTY", "SENSEX"
    direction: Literal["LONG_CALL", "LONG_PUT"]
    option_type: Literal["CE", "PE"]
    strategy: SwingStrategyType

    # Option Contract Details
    horizon: HorizonType = "POSITIONAL"
    timeframe: str = "1D"                # "1D", "15M", "5M"
    hard_exit_time: Optional[str] = None # e.g. "15:15:00" for intraday
    strike: float
    expiry_date: str                     # ISO date "YYYY-MM-DD"
    contract_symbol: str                 # FYERS format: e.g. "NSE:NIFTY26SEP25000CE"
    lot_size: int
    expected_holding_days: int = 7       # 2-20 days target window (0 for intraday)
    dte: int = 0                         # Days to expiry

    # Underlying Technical Context
    spot_price: float
    spot_trigger: float                  # Technical entry trigger on spot
    spot_stop: float                     # Technical thesis invalidation level on spot
    daily_atr: float = 0.0
    vwap: Optional[float] = None         # Intraday volume-weighted average price

    # Option Premium Execution Levels (₹ per unit)
    entry_premium: float
    stop_premium: float
    target_premium_1: float              # +1.5R premium target
    target_premium_2: float              # +3.0R premium target
    premium_risk_per_lot: float = 0.0    # (entry_premium - stop_premium) * lot_size

    # Greeks & Volatility Telemetry
    iv: float = 0.0
    iv_percentile: float = 50.0
    iv_regime: str = "NORMAL"
    greeks: dict[str, Any] = Field(default_factory=dict) # delta, gamma, theta_day, theta_hour, vega
    theta_drag_ratio: float = 0.0        # Hourly theta as % of expected profit

    # Quantitative Selection & Scoring
    score: SetupScoreBreakdown
    trade_validity: TradeValidity = Field(default_factory=TradeValidity)
    strike_selection_rationale: list[str] = Field(default_factory=list)
    strike_selection_score: float = 0.0
    liquidity_score: float = 0.0
    execution_score: float = 0.0

    # Macro & Technical Context
    market_regime: MarketRegimeType = "NEUTRAL"
    technical_reasons: list[str] = Field(default_factory=list)
    options_reasons: list[str] = Field(default_factory=list)
    risk_reasons: list[str] = Field(default_factory=list)
    invalidation_rules: list[str] = Field(default_factory=list)

    # Lifecycle & Audit
    signal_state: SignalStateType = "WATCH"
    created_at_utc: int = Field(default_factory=lambda: int(time.time() * 1000))
    valid_until_utc: int = Field(default_factory=lambda: int((time.time() + 86400 * 5) * 1000))


# ---------------------------------------------------------------------------
# Active Options Position Tracking
# ---------------------------------------------------------------------------
class SwingPosition(BaseModel):
    position_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    setup_id: str
    underlying: str
    option_type: Literal["CE", "PE"]
    strike: float
    expiry_date: str
    contract_symbol: str
    direction: Literal["LONG_CALL", "LONG_PUT"]
    strategy: SwingStrategyType
    horizon: HorizonType = "POSITIONAL"
    timeframe: str = "1D"
    hard_exit_time: Optional[str] = None # e.g. "15:15:00" for intraday

    # Execution & Sizing
    entry_premium: float
    current_premium: float
    num_lots: int = 1
    lot_size: int = 1

    # Dual-Layer Stops & Targets
    initial_stop_premium: float
    current_stop_premium: float
    spot_stop: float                     # Underlying structural invalidation level
    stop_method: StopMethod = "INITIAL"
    target_1: float
    target_2: float

    # Real-time Context
    spot_at_entry: float
    current_spot: float
    greeks_at_entry: dict[str, Any] = Field(default_factory=dict)
    iv_at_entry: float = 0.0
    days_held: int = 0
    dte_remaining: int = 0
    highest_premium: float = 0.0         # For trailing premium stops
    theta_cost_accumulated: float = 0.0

    # Lifecycle & Performance
    entered_at_utc: int = Field(default_factory=lambda: int(time.time() * 1000))
    unrealized_pnl: float = 0.0          # (current_premium - entry_premium) * lot_size * num_lots
    pnl_pct: float = 0.0                 # (current_premium / entry_premium - 1) * 100
    r_multiple: float = 0.0
    status: Literal["OPEN", "PARTIALLY_CLOSED", "CLOSED"] = "OPEN"
    close_premium: Optional[float] = None
    closed_at_utc: Optional[int] = None
    exit_reason: Optional[ExitReason] = None


# ---------------------------------------------------------------------------
# Portfolio & Greeks Risk State
# ---------------------------------------------------------------------------
class PortfolioRiskState(BaseModel):
    total_equity: float = 1_000_000.0
    total_premium_deployed: float = 0.0   # Sum of entry_premium * lot_size * num_lots
    premium_at_risk: float = 0.0          # Max potential loss across open stop levels
    portfolio_heat_pct: float = 0.0       # (premium_at_risk / total_equity) * 100
    max_heat_pct: float = 5.0             # Max 5% total open risk
    net_delta: float = 0.0                # Aggregate portfolio Delta from PortfolioGreeksLedger
    net_theta_day: float = 0.0            # Aggregate portfolio daily Theta burn (₹/day)
    net_vega: float = 0.0                 # Aggregate portfolio Vega
    open_positions_count: int = 0
    max_positions_count: int = 6
    positions_by_underlying: dict[str, int] = Field(default_factory=dict)
    max_positions_per_underlying: int = 2

