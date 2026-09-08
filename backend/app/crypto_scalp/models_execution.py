"""
Crypto Scalp Execution & Track Record Data Models
Immutable event logs, paper execution records, and quantitative performance analytics.
"""
from __future__ import annotations

import time
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
from app.models.crypto import SignalDirection


class CryptoScalpPositionState(str, Enum):
    ACTIVE = "ACTIVE"
    PARTIALLY_CLOSED = "PARTIALLY_CLOSED"  # T1 reached, 50% booked, SL moved to BE
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class CryptoScalpExitEventType(str, Enum):
    ENTRY_FILL = "ENTRY_FILL"
    T1_HIT = "T1_HIT"
    BREAKEVEN_RATCHET = "BREAKEVEN_RATCHET"
    BREAKEVEN_STOP = "BREAKEVEN_STOP"
    T2_HIT = "T2_HIT"
    INITIAL_STOP = "INITIAL_STOP"
    TIME_STOP = "TIME_STOP"
    MANUAL_CLOSE = "MANUAL_CLOSE"


class CryptoScalpExecutionMode(str, Enum):
    PAPER = "PAPER"
    LIVE = "LIVE"
    REPLAY = "REPLAY"


class CryptoScalpExecutionConfig(BaseModel):
    """Centralized execution parameters for paper execution friction."""
    execution_mode: CryptoScalpExecutionMode = CryptoScalpExecutionMode.PAPER
    account_equity: float = 10_000.0
    risk_per_trade_pct: float = 1.0  # 1% equity ($100 risk)
    target_1_close_fraction: float = 0.50  # 50% closed at T1
    entry_slippage_bps: float = 2.0  # 0.02%
    exit_slippage_bps: float = 2.0  # 0.02%
    taker_fee_bps: float = 5.0  # 0.05% per side (Binance Futures VIP0 taker)
    time_stop_seconds: int = 1800  # 30 minutes
    ambiguous_trigger_policy: str = "CONSERVATIVE"  # Prioritize stop loss if both breached in same tick/bar


class CryptoScalpExecutionEvent(BaseModel):
    """Immutable audit event for every state change in position lifecycle."""
    event_id: str
    trade_id: str
    signal_id: str
    event_type: CryptoScalpExitEventType
    symbol: str
    direction: SignalDirection
    strategy: str
    timestamp_ms: int = Field(default_factory=lambda: int(time.time() * 1000))
    market_price: float
    fill_price: float
    quantity: float
    fee_usd: float = 0.0
    slippage_usd: float = 0.0
    gross_pnl_usd: float = 0.0
    net_pnl_usd: float = 0.0
    r_multiple: float = 0.0
    state_before: CryptoScalpPositionState
    state_after: CryptoScalpPositionState
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CryptoScalpExecutionRecord(BaseModel):
    """Consolidated trade record representing complete lifecycle."""
    trade_id: str
    signal_id: str
    symbol: str
    asset: str
    direction: SignalDirection
    strategy: str
    strategy_name: str
    execution_mode: CryptoScalpExecutionMode = CryptoScalpExecutionMode.PAPER
    position_state: CryptoScalpPositionState = CryptoScalpPositionState.ACTIVE

    # Price levels
    signal_price: float
    entry_fill_price: float
    initial_stop_price: float
    current_stop_price: float  # Ratcheted to BE when T1 hit
    target_1_price: float
    target_2_price: float
    exit_price: Optional[float] = None
    exit_reason: Optional[CryptoScalpExitEventType] = None
    exit_reason_detail: Optional[str] = None

    # Quantities & Position Sizing
    quantity_initial: float
    quantity_closed_t1: float = 0.0
    quantity_closed_final: float = 0.0
    quantity_remaining: float
    notional_usd: float = 0.0
    initial_risk_usd: float = 0.0

    # P&L and Attribution
    gross_pnl_usd: float = 0.0
    fees_usd: float = 0.0
    slippage_usd: float = 0.0
    net_pnl_usd: float = 0.0
    net_return_pct: float = 0.0
    r_multiple: float = 0.0
    theoretical_r: float = 0.0
    execution_drag_r: float = 0.0  # theoretical_r - r_multiple

    # Timestamps & Durations
    t1_hit_at: Optional[int] = None
    t2_hit_at: Optional[int] = None
    stop_hit_at: Optional[int] = None
    duration_seconds: int = 0
    duration_str: str = "0s"
    created_at_utc: int = Field(default_factory=lambda: int(time.time() * 1000))
    closed_at_utc: Optional[int] = None
    events: list[CryptoScalpExecutionEvent] = Field(default_factory=list)


class CryptoScalpStrategyStats(BaseModel):
    """Quantitative performance attribution for an individual strategy."""
    strategy: str
    strategy_name: str
    total_signals: int = 0
    filled_trades: int = 0
    completed_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0
    win_rate_pct: float = 0.0
    profit_factor: float = 1.0
    expectancy_r: float = 0.0
    gross_profit_usd: float = 0.0
    gross_loss_usd: float = 0.0
    net_pnl_usd: float = 0.0
    average_r: float = 0.0
    average_duration_seconds: int = 0
    sample_size: int = 0
    insufficient_sample: bool = True  # True if completed < 10


class CryptoScalpAssetStats(BaseModel):
    """Performance attribution split by crypto asset (BTC vs ETH)."""
    asset: str
    symbol: str
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate_pct: float = 0.0
    profit_factor: float = 1.0
    net_pnl_usd: float = 0.0
    expectancy_r: float = 0.0
    average_duration_seconds: int = 0


class CryptoScalpPerformanceMetrics(BaseModel):
    """Top-level quantitative performance attribution across all scalp trades."""
    total_signals: int = 0
    active_positions: int = 0
    completed_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0
    win_rate_pct: float = 0.0
    profit_factor: float = 1.0
    expectancy_r: float = 0.0
    average_r: float = 0.0
    average_win_r: float = 0.0
    average_loss_r: float = 0.0

    # P&L Totals
    gross_profit_usd: float = 0.0
    gross_loss_usd: float = 0.0
    net_pnl_usd: float = 0.0
    total_fees_usd: float = 0.0
    total_slippage_usd: float = 0.0
    total_execution_drag_usd: float = 0.0

    average_duration_seconds: int = 0
    average_duration_str: str = "0s"
    insufficient_sample: bool = True  # True if completed_trades < 10

    # Attributions
    strategy_breakdown: dict[str, CryptoScalpStrategyStats] = Field(default_factory=dict)
    asset_breakdown: dict[str, CryptoScalpAssetStats] = Field(default_factory=dict)


def format_detailed_exit_reason(
    reason: Optional[Any],
    symbol: str = "BTCUSDT",
    entry_fill: float = 0.0,
    exit_price: Optional[float] = None,
    target_1: float = 0.0,
    target_2: float = 0.0,
    stop_loss: float = 0.0,
    r_multiple: float = 0.0,
    duration_str: str = "",
) -> str:
    """Generate institutional-grade detailed narrative for trade exit reason."""
    r_str = f"{r_multiple:+.2f}R" if r_multiple != 0 else "0.00R"
    clean_sym = symbol.replace("USDT", "")
    exit_p_str = f"${exit_price:,.2f}" if exit_price else "market price"

    val = reason.value if hasattr(reason, "value") else str(reason or "")
    if val in ("T2_HIT", "TARGET_2", "TARGET_2_HIT"):
        return f"Target 2 Reached — Full scale-out executed at {exit_p_str} on {clean_sym}, locking in max profit ({r_str})."
    elif val in ("BREAKEVEN_STOP", "BREAKEVEN_RATCHET"):
        return f"Breakeven Stop Hit — 50% locked at Target 1; remaining runner was protected and closed at entry ({exit_p_str}) with net gain {r_str}."
    elif val in ("INITIAL_STOP", "STOP_LOSS_HIT"):
        return f"Stop Loss Hit — Market breached risk threshold at {exit_p_str} on {clean_sym}; position liquidated to cap downside at {r_str}."
    elif val in ("TIME_STOP", "RUNNER_TIME_STOP_HIT"):
        dur = f" after {duration_str}" if duration_str else ""
        return f"Time Stop Exceeded — Scalp duration cap reached{dur}; auto-squared off at {exit_p_str} ({r_str})."
    elif val in ("MANUAL_CLOSE", "MANUAL_EXIT"):
        return f"Manual Square-Off — Position was manually exited by operator at {exit_p_str} ({r_str})."
    elif val == "T1_HIT":
        return f"Target 1 Hit — Scaled out 50% at ${target_1:,.2f}; stop-loss ratcheted to breakeven (${entry_fill:,.2f})."
    elif val in ("ACTIVE", "OPEN", ""):
        return f"Position Active — Tracking live market towards T1 (${target_1:,.2f}) and T2 (${target_2:,.2f}) with stop at ${stop_loss:,.2f}."
    return f"Order Closed — Reason: {val} at {exit_p_str} ({r_str})."
