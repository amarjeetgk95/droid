"""
Translation Ratio Engine (§8) - PRIMARY VORTEX-SNAP HYPOTHESIS.

Evaluates the ratio of directional price displacement to directional volume
pressure. Distinguishes between:
- Directional Acceptance (High pressure -> High displacement)
- Absorption Candidate (High pressure -> Low displacement)
- Rejection / Conflict (Pressure direction != Price direction)
"""
from __future__ import annotations

import time
from typing import List, Optional

import numpy as np

from app.signals.strategies.vortex_snap.types import (
    Candle,
    DirectionalPressureResult,
    TranslationRatioResult,
    TranslationState,
)
from app.signals.strategies.vortex_snap.config import TranslationRatioConfig


class TranslationRatioEngine:
    """Measures pressure-to-price translation efficiency."""

    def __init__(self, config: Optional[TranslationRatioConfig] = None) -> None:
        self.config = config or TranslationRatioConfig()

    def compute(
        self,
        candles: List[Candle],
        pressure_result: DirectionalPressureResult,
        reference_price: Optional[float] = None,
        prior_translation_ratio: Optional[float] = None,
    ) -> TranslationRatioResult:
        """Compute translation ratio and state at current bar T.

        Args:
            candles: Candle sequence up to time T.
            pressure_result: Output from DirectionalPressureEngine at bar T.
            reference_price: Optional explicit baseline price. If None, uses
                             candle at T - reference_lookback_bars (strictly <= T).
            prior_translation_ratio: Prior bar's translation ratio for change calculation.

        Returns:
            TranslationRatioResult snapshot.
        """
        start_t = time.perf_counter()
        n = len(candles)
        eps = self.config.epsilon

        if n < 2:
            return TranslationRatioResult(
                translation_ratio=1.0,
                translation_score=0.5,
                translation_state=TranslationState.NEUTRAL,
                normalized_displacement=0.0,
                raw_displacement_points=0.0,
                normalized_pressure=0.0,
                price_direction=0,
                pressure_direction=0,
                direction_aligned=True,
                translation_change=0.0,
                computation_time_ms=0.0,
            )

        current_close = candles[-1].close

        # 1. Point-in-time reference price
        lb = min(self.config.reference_lookback_bars, n - 1)
        if reference_price is None:
            ref_p = candles[-lb - 1].close
        else:
            ref_p = reference_price

        raw_displacement = current_close - ref_p
        abs_displacement = abs(raw_displacement)
        price_dir = 1 if raw_displacement > 0 else (-1 if raw_displacement < 0 else 0)

        # 2. Normalized Volatility Scale (ATR of recent bars)
        w_vol = min(self.config.volatility_scale_bars, n)
        recent_ranges = [max(c.high - c.low, eps) for c in candles[-w_vol:]]
        norm_vol = float(np.mean(recent_ranges)) if recent_ranges else 1.0

        # Normalized Price Displacement (scaled by expected random walk displacement over lb bars)
        sqrt_lb = max(np.sqrt(lb), 1.0)
        norm_displacement = abs_displacement / max(norm_vol * sqrt_lb, eps)

        # 3. Normalized Pressure
        # Ratio of net directional pressure to gross directional activity
        abs_net_pressure = abs(pressure_result.net_pressure)
        gross_pressure = pressure_result.positive_pressure + pressure_result.negative_pressure
        norm_pressure = abs_net_pressure / max(gross_pressure, eps)

        # 4. Translation Ratio (§8 formula)
        # translation_ratio = normalized_price_displacement / (normalized_pressure + epsilon)
        trans_ratio = norm_displacement / max(norm_pressure, eps)

        # 5. Normalized Translation Score in [0, 1] using sigmoid mapping
        # A ratio of 1.0 maps to ~0.50, > 2.0 maps towards 1.0, < 0.5 maps towards 0.0
        trans_score = float(1.0 / (1.0 + np.exp(-1.5 * (trans_ratio - 1.0))))

        # 6. Alignment between price direction and pressure direction
        press_dir = pressure_result.pressure_direction
        aligned = (price_dir == press_dir) if (price_dir != 0 and press_dir != 0) else True

        # 7. State Classification
        # High pressure condition
        is_high_pressure = abs(pressure_result.pressure_score) >= self.config.high_pressure_threshold
        is_high_translation = trans_ratio >= self.config.high_translation_threshold
        is_low_translation = trans_ratio <= self.config.low_translation_threshold

        if is_high_pressure:
            if not aligned and price_dir != 0 and press_dir != 0:
                state = TranslationState.REJECTION_CONFLICT
            elif is_high_translation and aligned:
                state = TranslationState.DIRECTIONAL_ACCEPTANCE
            elif is_low_translation:
                state = TranslationState.ABSORPTION_CANDIDATE
            else:
                state = TranslationState.NEUTRAL
        else:
            state = TranslationState.NEUTRAL

        # Rate of change
        if prior_translation_ratio is not None:
            trans_change = trans_ratio - prior_translation_ratio
        else:
            trans_change = 0.0

        elapsed = (time.perf_counter() - start_t) * 1000.0

        return TranslationRatioResult(
            translation_ratio=round(trans_ratio, 4),
            translation_score=round(trans_score, 4),
            translation_state=state,
            normalized_displacement=round(norm_displacement, 4),
            raw_displacement_points=round(float(raw_displacement), 2),
            normalized_pressure=round(norm_pressure, 4),
            price_direction=price_dir,
            pressure_direction=press_dir,
            direction_aligned=aligned,
            translation_change=round(trans_change, 4),
            computation_time_ms=round(elapsed, 3),
        )
