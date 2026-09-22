"""
Confirmation Engine (§17).

Applies event-specific confirmation checks before transitioning a candidate
from CLASSIFICATION to CONFIRMATION -> PRE-TRADE VALIDATION.

Supported confirmation mechanisms:
- FOLLOW_THROUGH: Next candle closes in the trade direction beyond the trigger bar.
- RETEST_AND_HOLD: Price tests the broken/defended level and holds.
- REJECTION_CONFIRMATION: Confirmatory wick or failure to breach level.
- PRESSURE_SHIFT: Directional pressure aligns or accelerates in trade direction.
- MICRO_SWING_BREAK: Price crosses trigger bar's extreme.
"""
from __future__ import annotations

from typing import Optional, Tuple
from pydantic import BaseModel, Field

from app.signals.strategies.vortex_snap.types import (
    Candle,
    EventType,
    VortexFeatureSnapshot,
)
from app.signals.strategies.vortex_snap.signals.event_classifier import ClassifiedEvent
from app.signals.strategies.vortex_snap.signals.reason_codes import ReasonCode


class ConfirmationResult(BaseModel):
    """Result of confirmation evaluation."""
    is_confirmed: bool
    confirmation_mechanism: Optional[str] = None
    reason_code: Optional[ReasonCode] = None
    confidence_boost: float = 0.0


class ConfirmationEngine:
    """Evaluates confirmation mechanisms based on event classification."""

    def evaluate(
        self,
        event: ClassifiedEvent,
        trigger_candle: Candle,
        confirm_candle: Candle,
        snapshot: VortexFeatureSnapshot,
    ) -> ConfirmationResult:
        """Evaluate if confirm_candle confirms the event initiated at trigger_candle.

        Args:
            event: ClassifiedEvent from prior bar.
            trigger_candle: The candle where event was classified.
            confirm_candle: The subsequent 1-minute candle.
            snapshot: Feature snapshot at confirm_candle.

        Returns:
            ConfirmationResult.
        """
        direction = event.direction

        # 1. TYPE A: CONTINUATION CONFIRMATION
        if event.event_type == EventType.CONTINUATION:
            # Long Continuation:
            if direction > 0:
                # Follow-through check: closed higher than trigger close, or broke trigger high
                if confirm_candle.close > trigger_candle.close or confirm_candle.high > trigger_candle.high:
                    if snapshot.pressure.pressure_direction >= 0:
                        return ConfirmationResult(
                            is_confirmed=True,
                            confirmation_mechanism="FOLLOW_THROUGH_CANDLE",
                            reason_code=ReasonCode.FOLLOW_THROUGH_CONFIRMED,
                            confidence_boost=0.08,
                        )
                # Retest and hold: tested level without closing below it
                if confirm_candle.low <= event.interacted_level.price and confirm_candle.close >= event.interacted_level.price:
                    return ConfirmationResult(
                        is_confirmed=True,
                        confirmation_mechanism="RETEST_AND_HOLD",
                        reason_code=ReasonCode.LEVEL_RETEST_HELD,
                        confidence_boost=0.10,
                    )
            # Short Continuation:
            elif direction < 0:
                if confirm_candle.close < trigger_candle.close or confirm_candle.low < trigger_candle.low:
                    if snapshot.pressure.pressure_direction <= 0:
                        return ConfirmationResult(
                            is_confirmed=True,
                            confirmation_mechanism="FOLLOW_THROUGH_CANDLE",
                            reason_code=ReasonCode.FOLLOW_THROUGH_CONFIRMED,
                            confidence_boost=0.08,
                        )
                if confirm_candle.high >= event.interacted_level.price and confirm_candle.close <= event.interacted_level.price:
                    return ConfirmationResult(
                        is_confirmed=True,
                        confirmation_mechanism="RETEST_AND_HOLD",
                        reason_code=ReasonCode.LEVEL_RETEST_HELD,
                        confidence_boost=0.10,
                    )

        # 2. TYPE B: ABSORPTION REVERSAL CONFIRMATION
        elif event.event_type == EventType.ABSORPTION:
            # Long Reversal (Absorption at support):
            if direction > 0:
                # Pressure shift or positive follow-through
                if confirm_candle.close > trigger_candle.close and confirm_candle.close > confirm_candle.open:
                    return ConfirmationResult(
                        is_confirmed=True,
                        confirmation_mechanism="REJECTION_CONFIRMATION",
                        reason_code=ReasonCode.LEVEL_ABSORPTION_CONFIRMED,
                        confidence_boost=0.12,
                    )
            # Short Reversal (Absorption at resistance):
            elif direction < 0:
                if confirm_candle.close < trigger_candle.close and confirm_candle.close < confirm_candle.open:
                    return ConfirmationResult(
                        is_confirmed=True,
                        confirmation_mechanism="REJECTION_CONFIRMATION",
                        reason_code=ReasonCode.LEVEL_ABSORPTION_CONFIRMED,
                        confidence_boost=0.12,
                    )

        # 3. TYPE C: VACUUM TRAP CONFIRMATION
        elif event.event_type == EventType.VACUUM_TRAP:
            # Short Trap (Fakeout above resistance, reclaimed downward):
            if direction < 0:
                if confirm_candle.close < event.interacted_level.price and confirm_candle.close <= trigger_candle.close:
                    return ConfirmationResult(
                        is_confirmed=True,
                        confirmation_mechanism="MICRO_SWING_BREAK",
                        reason_code=ReasonCode.TRAP_RECLAIM_CONFIRMED,
                        confidence_boost=0.15,
                    )
            # Long Trap (Fakeout below support, reclaimed upward):
            elif direction > 0:
                if confirm_candle.close > event.interacted_level.price and confirm_candle.close >= trigger_candle.close:
                    return ConfirmationResult(
                        is_confirmed=True,
                        confirmation_mechanism="MICRO_SWING_BREAK",
                        reason_code=ReasonCode.TRAP_RECLAIM_CONFIRMED,
                        confidence_boost=0.15,
                    )

        return ConfirmationResult(
            is_confirmed=False,
            confirmation_mechanism=None,
            reason_code=ReasonCode.CONFIRMATION_TIMEOUT,
            confidence_boost=0.0,
        )
