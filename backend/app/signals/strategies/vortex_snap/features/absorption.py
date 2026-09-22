"""
Absorption Detector (§9).

Detects institutional absorption when directional pressure is high but price
displacement fails or rejects, particularly when interacting with structural levels.
"""
from __future__ import annotations

import time
from typing import List, Optional

import numpy as np

from app.signals.strategies.vortex_snap.types import (
    AbsorptionResult,
    Candle,
    DirectionalPressureResult,
    StructuralLevel,
    StructuralLevelMapResult,
    TranslationRatioResult,
    TranslationState,
)
from app.signals.strategies.vortex_snap.config import AbsorptionConfig


class AbsorptionDetector:
    """Evaluates absorption evidence and generates absorption_score in [0, 1]."""

    def __init__(self, config: Optional[AbsorptionConfig] = None) -> None:
        self.config = config or AbsorptionConfig()

    def compute(
        self,
        candles: List[Candle],
        pressure: DirectionalPressureResult,
        translation: TranslationRatioResult,
        level_map: StructuralLevelMapResult,
    ) -> AbsorptionResult:
        """Compute absorption diagnostics for current candle.

        Args:
            candles: Candle sequence up to time T.
            pressure: Directional pressure result at T.
            translation: Translation ratio result at T.
            level_map: Structural level map result at T.

        Returns:
            AbsorptionResult.
        """
        start_t = time.perf_counter()
        if not candles:
            return AbsorptionResult(
                absorption_score=0.0,
                is_absorption_suspected=False,
                volume_shock_ratio=1.0,
                rejection_wick_ratio=0.0,
                level_proximity_score=0.0,
                repeated_test_count=0,
                failure_to_extend=False,
                opposing_pressure=False,
                interacted_level=None,
                computation_time_ms=0.0,
            )

        current_candle = candles[-1]
        c_range = max(current_candle.high - current_candle.low, 1e-9)

        # 1. Volume Shock: current volume vs median recent volume
        n = len(candles)
        recent_vols = [c.volume for c in candles[-min(20, n) :]]
        med_vol = float(np.median(recent_vols)) if recent_vols else 1.0
        vol_shock = current_candle.volume / max(med_vol, 1e-9)
        vol_score = max(0.0, min(1.0, (vol_shock - 1.0) / 1.5))

        # 2. Pressure Intensity
        press_intensity = abs(pressure.pressure_score)
        press_score = max(0.0, min(1.0, (press_intensity - 0.40) / 0.50))

        # 3. Translation Inefficiency (Inverse of translation ratio)
        # Low translation ratio = high absorption evidence
        # E.g. translation_ratio < 0.5 is very weak displacement
        if translation.translation_ratio <= 0.05:
            trans_inefficiency = 1.0
        else:
            trans_inefficiency = max(0.0, min(1.0, (1.0 - translation.translation_ratio) / 0.8))

        # 4. Rejection Wick Ratio
        # For bullish pressure absorbed at resistance: upper wick is long
        # For bearish pressure absorbed at support: lower wick is long
        if pressure.pressure_direction > 0:
            wick_ratio = current_candle.upper_wick / c_range
        elif pressure.pressure_direction < 0:
            wick_ratio = current_candle.lower_wick / c_range
        else:
            wick_ratio = max(current_candle.upper_wick, current_candle.lower_wick) / c_range
        wick_score = max(0.0, min(1.0, (wick_ratio - 0.25) / 0.40))

        # 5. Structural Level Interaction
        interacted_level: Optional[StructuralLevel] = None
        level_score = 0.0
        repeated_tests = 0
        current_price = current_candle.close

        for lvl in level_map.levels:
            dist_pct = abs(current_price - lvl.price) / max(current_price, 1e-6)
            if dist_pct <= self.config.level_interaction_tolerance_pct:
                interacted_level = lvl
                level_score = max(level_score, lvl.relevance_score)
                repeated_tests = max(repeated_tests, lvl.touch_count)

        repeat_score = min(repeated_tests * 0.20, 1.0)

        # 6. Failure to Extend (price tried to break out but closed within prior ranges)
        failure_extend = False
        if n >= 3:
            prev_2 = candles[-3:-1]
            if pressure.pressure_direction > 0:
                # Pushed higher but closed below previous high
                if current_candle.high > max(c.high for c in prev_2) and current_candle.close < max(c.close for c in prev_2):
                    failure_extend = True
            elif pressure.pressure_direction < 0:
                # Pushed lower but closed above previous low
                if current_candle.low < min(c.low for c in prev_2) and current_candle.close > min(c.close for c in prev_2):
                    failure_extend = True

        extend_score = 0.25 if failure_extend else 0.0

        # 7. Opposing Pressure (Price displaced opposite to pressure direction)
        opposing = not translation.direction_aligned and press_intensity >= 0.30
        opposing_score = 0.25 if opposing else 0.0

        # Multi-factor composite absorption score
        composite_score = (
            0.22 * press_score
            + 0.22 * trans_inefficiency
            + 0.16 * vol_score
            + 0.15 * wick_score
            + 0.15 * level_score
            + 0.05 * repeat_score
            + extend_score
            + opposing_score
        )

        final_score = max(0.0, min(1.0, composite_score))
        suspected = (
            final_score >= 0.60
            and vol_shock >= self.config.min_volume_shock
            and (translation.translation_state == TranslationState.ABSORPTION_CANDIDATE or opposing or failure_extend)
        )

        elapsed = (time.perf_counter() - start_t) * 1000.0

        return AbsorptionResult(
            absorption_score=round(final_score, 4),
            is_absorption_suspected=suspected,
            volume_shock_ratio=round(vol_shock, 3),
            rejection_wick_ratio=round(wick_ratio, 4),
            level_proximity_score=round(level_score, 4),
            repeated_test_count=repeated_tests,
            failure_to_extend=failure_extend,
            opposing_pressure=opposing,
            interacted_level=interacted_level,
            computation_time_ms=round(elapsed, 3),
        )
