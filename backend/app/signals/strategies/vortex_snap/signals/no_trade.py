"""
Explicit No-Trade Logic (§18).

Evaluates whether the strategy must deliberately emit NO TRADE.
NO TRADE is treated as a first-class strategy decision, not a system failure.
"""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field

from app.signals.strategies.vortex_snap.types import (
    MarketRegime,
    SessionPhase,
    VortexFeatureSnapshot,
)
from app.signals.strategies.vortex_snap.signals.reason_codes import ReasonCode


class NoTradeEvaluation(BaseModel):
    """Result of No-Trade evaluation."""
    is_no_trade: bool
    rejection_reasons: List[ReasonCode] = Field(default_factory=list)
    explanation: str = ""


class NoTradeGate:
    """Enforces absolute trade veto conditions before signal generation."""

    def evaluate(
        self,
        snapshot: VortexFeatureSnapshot,
        cooldown_active: bool = False,
        daily_loss_limit_breached: bool = False,
        consecutive_losses: int = 0,
        max_consecutive_losses: int = 3,
        slippage_estimate_pts: float = 0.0,
        max_allowed_slippage_pts: float = 15.0,
        active_correlated_exposure: bool = False,
    ) -> NoTradeEvaluation:
        """Check all explicit no-trade conditions.

        Args:
            snapshot: Current feature snapshot.
            cooldown_active: True if currently in cooldown period (§37).
            daily_loss_limit_breached: True if daily risk stop is hit (§39).
            consecutive_losses: Running count of consecutive loss trades.
            max_consecutive_losses: Threshold for risk circuit breaker.
            slippage_estimate_pts: Estimated execution friction points.
            max_allowed_slippage_pts: Slippage tolerance.
            active_correlated_exposure: True if correlated index already has active trade (§38).

        Returns:
            NoTradeEvaluation snapshot.
        """
        reasons: List[ReasonCode] = []

        # 1. Market Session & Clock
        if not snapshot.session.is_trading_allowed:
            if snapshot.session.is_forced_square_off:
                reasons.append(ReasonCode.FORCED_SQUARE_OFF)
            else:
                reasons.append(ReasonCode.NO_TRADE_WINDOW)

        # 2. Market Regime Gate (§19)
        if snapshot.regime.regime == MarketRegime.CHAOTIC:
            reasons.append(ReasonCode.REGIME_CHAOTIC)

        # 3. Cooldown Active (§37)
        if cooldown_active:
            reasons.append(ReasonCode.COOLDOWN_ACTIVE)

        # 4. Daily Risk Controls (§39)
        if daily_loss_limit_breached:
            reasons.append(ReasonCode.DAILY_LOSS_LIMIT_REACHED)

        if consecutive_losses >= max_consecutive_losses:
            reasons.append(ReasonCode.CONSECUTIVE_LOSS_LIMIT)

        # 5. Slippage / Friction Gate (§29, §39)
        if slippage_estimate_pts > max_allowed_slippage_pts:
            reasons.append(ReasonCode.SLIPPAGE_TOO_HIGH)

        # 6. Correlated Position Control (§38)
        if active_correlated_exposure:
            reasons.append(ReasonCode.CORRELATED_EXPOSURE_ACTIVE)

        # Explanation summary
        is_vetoed = len(reasons) > 0
        explanation = ", ".join(r.value for r in reasons) if is_vetoed else "All safety gates clear"

        return NoTradeEvaluation(
            is_no_trade=is_vetoed,
            rejection_reasons=reasons,
            explanation=explanation,
        )
