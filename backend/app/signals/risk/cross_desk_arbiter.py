"""
Cross-Desk Inventory Arbiter (§31, §51).
Prevents inventory cannibalization and portfolio risk inflation when Scalp and Intraday desks
generate opposing or simultaneous signals on the same underlying.

Governed by the Deterministic State Priority Matrix:
  - Intraday FLAT: Allow all valid scalps.
  - Intraday IN PROFIT (>1R):
      - Same direction: ALLOW (pyramiding within risk limits).
      - Opposing direction: HARVEST_WARNING (tighten intraday stop to breakeven or partial scale-out).
  - Intraday IN DRAWDOWN (<0):
      - Same direction: ALLOW if within overall desk risk envelope.
      - Opposing direction: HARD SUPPRESS (never trade against an already stressed intraday trade).
"""
from __future__ import annotations

from typing import Literal, Optional, Any
from pydantic import BaseModel, Field

ArbiterAction = Literal["ALLOW", "SUPPRESS", "HARVEST_WARNING", "REDUCE_SIZE"]


class ArbiterDecision(BaseModel):
    action: ArbiterAction = "ALLOW"
    passed: bool = True
    reason: Optional[str] = None
    suggested_intraday_action: Optional[str] = None  # e.g., "TIGHTEN_STOP_TO_BE", "SCALE_OUT_50"
    sizing_multiplier: float = 1.0


class CrossDeskArbiter:
    """
    Arbitrates execution permissions between Scalp Desk and Intraday Desk.
    """

    def arbitrate(
        self,
        candidate_is_scalp: bool,
        candidate_underlying: str,
        candidate_direction: str,
        active_trades: list[Any],
    ) -> ArbiterDecision:
        """
        Evaluates candidate against currently active trades on the same underlying.
        """
        # Find active trades on the same underlying
        underlying_trades = [
            t for t in active_trades
            if getattr(t, "underlying", "") == candidate_underlying
            and getattr(t, "fsm_state", "") in ("CONFIRMED", "TARGET_1_HIT", "ACTIVE", "PARTIALLY_FILLED")
        ]

        if not underlying_trades:
            return ArbiterDecision(action="ALLOW", passed=True, reason="No active trades on underlying")

        # Check if candidate is a Scalp trade while an Intraday trade exists
        if candidate_is_scalp:
            intraday_trades = [
                t for t in underlying_trades
                if not getattr(t, "is_scalp", False) and getattr(t, "timeframe", "5M") not in ("1M", "3M")
            ]

            if not intraday_trades:
                return ArbiterDecision(action="ALLOW", passed=True, reason="No active intraday trades on underlying")

            # Evaluate each active intraday trade
            for it in intraday_trades:
                it_direction = getattr(it, "direction", "")
                is_same_dir = (it_direction == candidate_direction)
                
                # Check intraday PnL state (R-multiple)
                r_multiple = float(getattr(it, "r_multiple", 0.0) or getattr(it, "unrealized_r", 0.0) or 0.0)

                # State 1: Intraday trade is in drawdown (< 0R)
                if r_multiple < 0:
                    if not is_same_dir:
                        # HARD SUPPRESS: Opposing scalp while intraday is underwater
                        return ArbiterDecision(
                            action="SUPPRESS",
                            passed=False,
                            reason=f"REJECT_CROSS_DESK_CONFLICT: Cannot open opposing scalp ({candidate_direction}) while intraday trade {getattr(it, 'signal_id', '')} is underwater ({r_multiple:.2f}R)",
                        )
                    else:
                        # Same direction: Allow, but with reduced size if drawdown is deep
                        sizing = 0.75 if r_multiple < -0.5 else 1.0
                        return ArbiterDecision(
                            action="ALLOW",
                            passed=True,
                            reason=f"Same direction scalp aligned with intraday trade in mild pullback ({r_multiple:.2f}R)",
                            sizing_multiplier=sizing,
                        )

                # State 2: Intraday trade is in solid profit (> 1.0R)
                elif r_multiple >= 1.0:
                    if not is_same_dir:
                        # HARVEST WARNING: Scalp counter-trend can signal early exhaustion
                        return ArbiterDecision(
                            action="HARVEST_WARNING",
                            passed=True,
                            reason=f"Counter-trend scalp detected while intraday trade is up +{r_multiple:.2f}R. Signal to tighten intraday stop to breakeven.",
                            suggested_intraday_action="TIGHTEN_STOP_TO_BE",
                            sizing_multiplier=0.50,  # Half-size opposing scalp
                        )
                    else:
                        # Same direction: Pyramiding permitted
                        return ArbiterDecision(
                            action="ALLOW",
                            passed=True,
                            reason=f"Pyramid scalp aligned with winning intraday trade (+{r_multiple:.2f}R)",
                            sizing_multiplier=1.0,
                        )

                # State 3: Intraday trade is around breakeven (0 to 1.0R)
                else:
                    if not is_same_dir:
                        return ArbiterDecision(
                            action="SUPPRESS",
                            passed=False,
                            reason=f"REJECT_CROSS_DESK_CONFLICT: Opposing scalp suppressed while intraday trade is near breakeven ({r_multiple:.2f}R)",
                        )

        # Candidate is Intraday trade while Scalp trade exists
        else:
            scalp_trades = [
                t for t in underlying_trades
                if getattr(t, "is_scalp", False) or getattr(t, "timeframe", "5M") in ("1M", "3M")
            ]
            for st in scalp_trades:
                st_direction = getattr(st, "direction", "")
                if st_direction != candidate_direction:
                    # Intraday macro trade overrides fast scalp, but flag it
                    return ArbiterDecision(
                        action="ALLOW",
                        passed=True,
                        reason=f"Macro intraday trade {candidate_direction} takes precedence over micro scalp {st_direction}",
                        suggested_intraday_action="MONITOR_SCALP_EXIT",
                    )

        return ArbiterDecision(action="ALLOW", passed=True, reason="Cross-desk risk check passed")


cross_desk_arbiter = CrossDeskArbiter()
