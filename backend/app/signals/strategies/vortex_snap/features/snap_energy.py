"""
Snap Energy Composite (§11).

Quantifies accumulated potential energy during the compression phase:
snap_energy = compression_score * pressure_accumulation * compression_duration * directional_consistency
Distinguishes short random noise from high-energy coiled spring breakouts.
"""
from __future__ import annotations

import time
from typing import List, Optional

import numpy as np

from app.signals.strategies.vortex_snap.types import (
    Candle,
    CompressionResult,
    DirectionalPressureResult,
    SnapEnergyResult,
)
from app.signals.strategies.vortex_snap.config import SnapEnergyConfig


class SnapEnergyEngine:
    """Computes accumulated potential release energy."""

    def __init__(self, config: Optional[SnapEnergyConfig] = None) -> None:
        self.config = config or SnapEnergyConfig()

    def compute(
        self,
        candles: List[Candle],
        compression: CompressionResult,
        pressure: DirectionalPressureResult,
    ) -> SnapEnergyResult:
        """Calculate snap energy at current candle.

        Args:
            candles: Candle sequence up to time T.
            compression: Compression result at T.
            pressure: Directional pressure result at T.

        Returns:
            SnapEnergyResult snapshot.
        """
        start_t = time.perf_counter()
        dur = compression.duration_bars

        if dur < self.config.min_compression_duration or len(candles) < dur:
            elapsed = (time.perf_counter() - start_t) * 1000.0
            return SnapEnergyResult(
                snap_energy=0.0,
                compression_duration=dur,
                pressure_accumulation=0.0,
                directional_consistency=0.0,
                energy_tier="LOW",
                computation_time_ms=round(elapsed, 3),
            )

        # Inspect candles across the compression duration
        dur_candles = candles[-dur:]
        pressures: List[float] = []
        for c in dur_candles:
            body = c.close - c.open
            c_range = max(c.high - c.low, 1e-9)
            pressures.append(float(c.volume * (body / c_range)))

        # 1. Pressure Accumulation (sum of directional pressure normalized by duration)
        raw_accum = sum(pressures)
        abs_accum = abs(raw_accum)

        # Scale relative to average volume
        mean_vol = float(np.mean([c.volume for c in dur_candles])) if dur_candles else 1.0
        norm_accum = abs_accum / max(mean_vol * dur, 1e-9)
        pressure_accum_score = max(0.0, min(1.0, norm_accum))

        # 2. Directional Consistency
        # Fraction of bars aligned with the dominant accumulated direction
        dominant_sign = 1 if raw_accum >= 0 else -1
        aligned_bars = sum(1 for p in pressures if (p > 0 and dominant_sign > 0) or (p < 0 and dominant_sign < 0))
        consistency = aligned_bars / max(dur, 1)

        # 3. Duration Factor (saturates smoothly at duration_saturation_bars)
        sat_bars = max(self.config.duration_saturation_bars, 1)
        duration_factor = min(dur / sat_bars, 1.2) / 1.2  # normalized in [0, 1]

        # 4. Composite Snap Energy Formula (§11)
        # Combine compression intensity, accumulated pressure, duration, and consistency
        comp_weight = compression.compression_score
        raw_energy = (
            comp_weight * 0.35
            + duration_factor * 0.25
            + pressure_accum_score * 0.20
            + consistency * self.config.consistency_weight
        )

        final_energy = max(0.0, min(1.0, raw_energy))

        # Energy Tier
        if final_energy >= self.config.energy_explosive_threshold:
            tier = "EXPLOSIVE"
        elif final_energy >= 0.65:
            tier = "HIGH"
        elif final_energy >= 0.40:
            tier = "MODERATE"
        else:
            tier = "LOW"

        elapsed = (time.perf_counter() - start_t) * 1000.0

        return SnapEnergyResult(
            snap_energy=round(final_energy, 4),
            compression_duration=dur,
            pressure_accumulation=round(pressure_accum_score, 4),
            directional_consistency=round(consistency, 4),
            energy_tier=tier,
            computation_time_ms=round(elapsed, 3),
        )
