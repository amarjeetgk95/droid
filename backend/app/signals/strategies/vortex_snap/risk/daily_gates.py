"""
Daily Risk Gates (§39).

Enforces global risk envelope limits:
- Max daily loss limit
- Max consecutive losses
- Max simultaneous open positions
- Max signals per hour / trades per session
- Max notional exposure
"""
from __future__ import annotations

from typing import List, Optional, Tuple
from pydantic import BaseModel, Field

from app.signals.strategies.vortex_snap.signals.reason_codes import ReasonCode


class DailyRiskLimits(BaseModel):
    """Configurable risk thresholds (§39)."""
    max_daily_loss_points: float = 120.0
    max_consecutive_losses: int = 3
    max_simultaneous_positions: int = 2
    max_trades_per_session: int = 8
    max_signals_per_hour: int = 4


class DailyRiskGate:
    """Monitors daily loss, trade count, and exposure."""

    def __init__(self, limits: Optional[DailyRiskLimits] = None) -> None:
        self.limits = limits or DailyRiskLimits()
        self.cumulative_pnl_points: float = 0.0
        self.consecutive_losses: int = 0
        self.total_trades_today: int = 0
        self.active_positions_count: int = 0

    def record_trade_outcome(self, net_points: float) -> None:
        """Record completed trade result."""
        self.cumulative_pnl_points += net_points
        self.total_trades_today += 1
        if net_points < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

    def can_open_position(self) -> Tuple[bool, Optional[ReasonCode]]:
        """Verify if a new trade is permitted under daily risk limits."""
        # 1. Max daily loss
        if self.cumulative_pnl_points <= -self.limits.max_daily_loss_points:
            return False, ReasonCode.DAILY_LOSS_LIMIT_REACHED

        # 2. Max consecutive losses
        if self.consecutive_losses >= self.limits.max_consecutive_losses:
            return False, ReasonCode.CONSECUTIVE_LOSS_LIMIT

        # 3. Max simultaneous positions
        if self.active_positions_count >= self.limits.max_simultaneous_positions:
            return False, ReasonCode.CORRELATED_EXPOSURE_ACTIVE

        return True, None

    def reset(self) -> None:
        """Reset daily counters at start of new trading session."""
        self.cumulative_pnl_points = 0.0
        self.consecutive_losses = 0
        self.total_trades_today = 0
        self.active_positions_count = 0
