"""
Microstructure Event Classifier (§12).

Classifies market events into:
- TYPE A: CONTINUATION (Breakout Acceptance)
- TYPE B: ABSORPTION (Absorption Reversal)
- TYPE C: VACUUM TRAP (Failed Breakout Reclaim)
"""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field

from app.signals.strategies.vortex_snap.types import (
    Candle,
    CompressionZone,
    EventType,
    LevelType,
    StructuralLevel,
    TranslationState,
    VortexFeatureSnapshot,
)
from app.signals.strategies.vortex_snap.signals.reason_codes import ReasonCode


class ClassifiedEvent(BaseModel):
    """Output from the event classifier."""
    event_type: EventType
    direction: int = Field(description="+1 for LONG, -1 for SHORT")
    confidence: float = Field(ge=0.0, le=1.0)
    interacted_level: StructuralLevel
    reason_codes: List[ReasonCode] = Field(default_factory=list)


class EventClassifier:
    """Classifies microstructure transitions into actionable candidate patterns."""

    def classify(
        self,
        snapshot: VortexFeatureSnapshot,
        candles_1m: List[Candle],
    ) -> Optional[ClassifiedEvent]:
        """Classify current market bar for TYPE A, B, or C event.

        Args:
            snapshot: Point-in-time feature snapshot at bar T.
            candles_1m: 1-minute candle sequence up to T.

        Returns:
            ClassifiedEvent or None if no valid event detected.
        """
        if len(candles_1m) < 3:
            return None

        current_candle = candles_1m[-1]
        current_price = current_candle.close
        levels = snapshot.structural_levels.levels

        # ─────────────────────────────────────────────────────────────────────
        # TYPE C: VACUUM TRAP (§12, §15) - Highest priority to catch failed breakouts
        # ─────────────────────────────────────────────────────────────────────
        # Bullish Trap (Short candidate):
        # 1. Price broke above resistance level in previous 1-3 bars
        # 2. But current bar closed back BELOW the broken level
        # 3. Pressure collapsed or reversed negative
        resistance_types = (LevelType.PDH, LevelType.ORH, LevelType.SESSION_HIGH, LevelType.SWING_HIGH_5M)
        for lvl in levels:
            if lvl.level_type in resistance_types:
                prev_high = max(c.high for c in candles_1m[-3:])
                if prev_high > lvl.price and current_candle.close < lvl.price:
                    if snapshot.pressure.pressure_score <= 0.10:  # Pressure collapsed or reversed
                        reasons = [
                            ReasonCode.BREAKOUT_FAILED,
                            ReasonCode.TRAP_RECLAIM_CONFIRMED,
                        ]
                        if snapshot.vacuum.is_vacuum_detected:
                            reasons.append(ReasonCode.VACUUM_CONFIRMED)
                        if snapshot.pressure.pressure_direction < 0:
                            reasons.append(ReasonCode.PRESSURE_NEGATIVE)

                        conf = 0.70 + (0.15 if snapshot.pressure.pressure_direction < 0 else 0.0)
                        return ClassifiedEvent(
                            event_type=EventType.VACUUM_TRAP,
                            direction=-1,  # SHORT trap
                            confidence=round(min(conf, 0.95), 4),
                            interacted_level=lvl,
                            reason_codes=reasons,
                        )

        # Bearish Trap (Long candidate):
        # 1. Price broke below support level in previous 1-3 bars
        # 2. But current bar closed back ABOVE the broken level
        # 3. Pressure collapsed or reversed positive
        support_types = (LevelType.PDL, LevelType.ORL, LevelType.SESSION_LOW, LevelType.SWING_LOW_5M)
        for lvl in levels:
            if lvl.level_type in support_types:
                prev_low = min(c.low for c in candles_1m[-3:])
                if prev_low < lvl.price and current_candle.close > lvl.price:
                    if snapshot.pressure.pressure_score >= -0.10:  # Selling pressure collapsed
                        reasons = [
                            ReasonCode.BREAKOUT_FAILED,
                            ReasonCode.TRAP_RECLAIM_CONFIRMED,
                        ]
                        if snapshot.vacuum.is_vacuum_detected:
                            reasons.append(ReasonCode.VACUUM_CONFIRMED)
                        if snapshot.pressure.pressure_direction > 0:
                            reasons.append(ReasonCode.PRESSURE_POSITIVE)

                        conf = 0.70 + (0.15 if snapshot.pressure.pressure_direction > 0 else 0.0)
                        return ClassifiedEvent(
                            event_type=EventType.VACUUM_TRAP,
                            direction=1,  # LONG trap
                            confidence=round(min(conf, 0.95), 4),
                            interacted_level=lvl,
                            reason_codes=reasons,
                        )

        # ─────────────────────────────────────────────────────────────────────
        # TYPE B: ABSORPTION (§12, §14)
        # ─────────────────────────────────────────────────────────────────────
        if snapshot.absorption.is_absorption_suspected or snapshot.absorption.absorption_score >= 0.65:
            # Find interacting level within tolerance
            interacted_lvl = snapshot.absorption.interacted_level
            if not interacted_lvl and levels:
                interacted_lvl = min(levels, key=lambda l: abs(current_price - l.price))

            if interacted_lvl:
                # Absorption of buying pressure at resistance -> Bearish reversal
                if snapshot.pressure.pressure_direction > 0 and current_price <= interacted_lvl.price * 1.002:
                    reasons = [
                        ReasonCode.LEVEL_ABSORPTION_CONFIRMED,
                        ReasonCode.TRANSLATION_WEAK,
                    ]
                    if snapshot.pressure.pressure_score > 0.5:
                        reasons.append(ReasonCode.PRESSURE_POSITIVE)
                    conf = snapshot.absorption.absorption_score
                    return ClassifiedEvent(
                        event_type=EventType.ABSORPTION,
                        direction=-1,  # SHORT reversal candidate
                        confidence=round(conf, 4),
                        interacted_level=interacted_lvl,
                        reason_codes=reasons,
                    )
                # Absorption of selling pressure at support -> Bullish reversal
                elif snapshot.pressure.pressure_direction < 0 and current_price >= interacted_lvl.price * 0.998:
                    reasons = [
                        ReasonCode.LEVEL_ABSORPTION_CONFIRMED,
                        ReasonCode.TRANSLATION_WEAK,
                    ]
                    if snapshot.pressure.pressure_score < -0.5:
                        reasons.append(ReasonCode.PRESSURE_NEGATIVE)
                    conf = snapshot.absorption.absorption_score
                    return ClassifiedEvent(
                        event_type=EventType.ABSORPTION,
                        direction=1,  # LONG reversal candidate
                        confidence=round(conf, 4),
                        interacted_level=interacted_lvl,
                        reason_codes=reasons,
                    )

        # ─────────────────────────────────────────────────────────────────────
        # TYPE A: CONTINUATION (§12, §13)
        # ─────────────────────────────────────────────────────────────────────
        is_compressed = snapshot.compression.zone in (CompressionZone.WATCH, CompressionZone.ARMED, CompressionZone.EXTREME)
        has_vacuum = snapshot.vacuum.is_vacuum_detected or snapshot.vacuum.liquidity_vacuum_score >= 0.50
        is_aligned_translation = (
            snapshot.translation.translation_state == TranslationState.DIRECTIONAL_ACCEPTANCE
            or (snapshot.translation.direction_aligned and snapshot.translation.translation_score >= 0.45)
        )

        if (is_compressed or snapshot.vacuum.prior_compression_passed) and has_vacuum and is_aligned_translation:
            # Long continuation: check if any resistance was broken
            if snapshot.pressure.pressure_direction > 0:
                broken_res = [
                    lvl for lvl in levels
                    if lvl.price < current_candle.close
                    and (lvl.level_type in resistance_types or lvl.price >= min(c.low for c in candles_1m[-5:]))
                ]
                if broken_res:
                    best_res = max(broken_res, key=lambda l: l.price)
                    reasons = [
                        ReasonCode.RESISTANCE_BROKEN,
                        ReasonCode.PRESSURE_POSITIVE,
                        ReasonCode.TRANSLATION_HIGH,
                        ReasonCode.VACUUM_CONFIRMED,
                    ]
                    if snapshot.compression.zone == CompressionZone.EXTREME:
                        reasons.append(ReasonCode.COMPRESSION_EXTREME)
                    elif snapshot.compression.zone == CompressionZone.ARMED:
                        reasons.append(ReasonCode.COMPRESSION_ARMED)
                    if snapshot.snap_energy.snap_energy >= 0.65:
                        reasons.append(ReasonCode.SNAP_ENERGY_HIGH)

                    base_conf = (
                        0.30 * snapshot.compression.compression_score
                        + 0.25 * snapshot.translation.translation_score
                        + 0.25 * snapshot.vacuum.liquidity_vacuum_score
                        + 0.20 * snapshot.snap_energy.snap_energy
                    )
                    return ClassifiedEvent(
                        event_type=EventType.CONTINUATION,
                        direction=1,  # LONG continuation
                        confidence=round(min(base_conf, 0.95), 4),
                        interacted_level=best_res,
                        reason_codes=reasons,
                    )

            # Short continuation: check if any support was broken
            if snapshot.pressure.pressure_direction < 0:
                broken_supp = [
                    lvl for lvl in levels
                    if lvl.price > current_candle.close
                    and (lvl.level_type in support_types or lvl.price <= max(c.high for c in candles_1m[-5:]))
                ]
                if broken_supp:
                    best_supp = min(broken_supp, key=lambda l: l.price)
                    reasons = [
                        ReasonCode.SUPPORT_BROKEN,
                        ReasonCode.PRESSURE_NEGATIVE,
                        ReasonCode.TRANSLATION_HIGH,
                        ReasonCode.VACUUM_CONFIRMED,
                    ]
                    if snapshot.compression.zone in (CompressionZone.EXTREME, CompressionZone.ARMED):
                        reasons.append(ReasonCode.COMPRESSION_ARMED)
                    if snapshot.snap_energy.snap_energy >= 0.65:
                        reasons.append(ReasonCode.SNAP_ENERGY_HIGH)

                    base_conf = (
                        0.30 * snapshot.compression.compression_score
                        + 0.25 * snapshot.translation.translation_score
                        + 0.25 * snapshot.vacuum.liquidity_vacuum_score
                        + 0.20 * snapshot.snap_energy.snap_energy
                    )
                    return ClassifiedEvent(
                        event_type=EventType.CONTINUATION,
                        direction=-1,  # SHORT continuation
                        confidence=round(min(base_conf, 0.95), 4),
                        interacted_level=best_supp,
                        reason_codes=reasons,
                    )

        return None
