"""
Directional Pressure Engine (§7).

Computes micro-pressure for each 1-minute candle based on body efficiency
multiplied by volume, with rolling/EMA normalization, persistence tracking,
and acceleration measurement.
"""
from __future__ import annotations

import time
from typing import List, Optional

import numpy as np

from app.signals.strategies.vortex_snap.types import (
    Candle,
    DirectionalPressureResult,
)
from app.signals.strategies.vortex_snap.config import DirectionalPressureConfig


def compute_raw_pressure(candle: Candle, epsilon: float = 1e-9) -> float:
    """Calculate raw directional pressure for a single 1-minute candle."""
    c_range = max(candle.high - candle.low, epsilon)
    body = candle.close - candle.open
    body_efficiency = body / c_range  # in [-1.0, 1.0]
    return float(candle.volume * body_efficiency)


class DirectionalPressureEngine:
    """Measures directional flow pressure, acceleration, and persistence."""

    def __init__(self, config: Optional[DirectionalPressureConfig] = None) -> None:
        self.config = config or DirectionalPressureConfig()

    def compute(
        self,
        candles: List[Candle],
        prior_persistence: int = 0,
    ) -> DirectionalPressureResult:
        """Calculate point-in-time directional pressure at current bar.

        Args:
            candles: Candle sequence up to time T.
            prior_persistence: Consecutive bars of same-sign pressure prior to current.

        Returns:
            DirectionalPressureResult.
        """
        start_t = time.perf_counter()
        if not candles:
            return DirectionalPressureResult(
                net_pressure=0.0,
                pressure_score=0.0,
                pressure_direction=0,
                positive_pressure=0.0,
                negative_pressure=0.0,
                pressure_acceleration=0.0,
                pressure_persistence=0,
                pressure_change=0.0,
                pressure_5bar=0.0,
                pressure_10bar=0.0,
                computation_time_ms=0.0,
            )

        eps = self.config.epsilon
        raw_pressures = [compute_raw_pressure(c, eps) for c in candles]

        # Rolling windows
        w_p = min(self.config.pressure_window, len(raw_pressures))
        w_scale = min(self.config.scale_window, len(raw_pressures))

        # Recent pressure series
        recent_pressures = raw_pressures[-w_p:]
        pos_pressures = [max(p, 0.0) for p in recent_pressures]
        neg_pressures = [abs(min(p, 0.0)) for p in recent_pressures]

        pos_sum = float(sum(pos_pressures))
        neg_sum = float(sum(neg_pressures))
        net_press = float(sum(recent_pressures))

        # 5-bar and 10-bar rolling sums
        press_5bar = float(sum(raw_pressures[-5:])) if len(raw_pressures) >= 5 else net_press
        press_10bar = float(sum(raw_pressures[-10:])) if len(raw_pressures) >= 10 else net_press

        # Scaling scale: mean absolute pressure over scale_window
        scale_window_pressures = [abs(p) for p in raw_pressures[-w_scale:]]
        mean_scale = float(np.mean(scale_window_pressures)) if scale_window_pressures else 1.0
        scale = max(mean_scale * math_sqrt_scale(w_p), eps)

        # Exponentially smoothed pressure
        alpha = self.config.ema_alpha
        ema_press = raw_pressures[0]
        for p in raw_pressures[1:]:
            ema_press = alpha * p + (1.0 - alpha) * ema_press

        # Normalized pressure score in [-1.0, 1.0] using hyperbolic tangent
        # Net pressure / scale, passed through tanh for bounded representation
        norm_ratio = net_press / scale
        pressure_score = float(np.tanh(norm_ratio))

        # Determine discrete pressure direction
        if pressure_score >= 0.20:
            p_dir = 1
        elif pressure_score <= -0.20:
            p_dir = -1
        else:
            p_dir = 0

        # Acceleration and change
        # Raw values are in volume units (can be thousands). Normalized values
        # divide by the same scale used for pressure_score so HUD/ML sees
        # comparable units (score units / bar).
        curr_p = raw_pressures[-1]
        prev_p = raw_pressures[-2] if len(raw_pressures) >= 2 else curr_p
        press_change = curr_p - prev_p

        if len(raw_pressures) >= 3:
            prev_change = prev_p - raw_pressures[-3]
            press_accel = press_change - prev_change
        else:
            press_accel = 0.0

        press_accel_norm = press_accel / scale if scale else 0.0

        # Persistence calculation
        if p_dir == 0:
            persistence = 0
        elif prior_persistence > 0 and p_dir > 0:
            persistence = prior_persistence + 1
        elif prior_persistence < 0 and p_dir < 0:
            persistence = prior_persistence - 1
        else:
            persistence = p_dir

        elapsed = (time.perf_counter() - start_t) * 1000.0

        return DirectionalPressureResult(
            net_pressure=round(net_press, 2),
            pressure_score=round(pressure_score, 4),
            pressure_direction=p_dir,
            positive_pressure=round(pos_sum, 2),
            negative_pressure=round(neg_sum, 2),
            pressure_acceleration=round(press_accel, 2),
            pressure_acceleration_norm=round(float(press_accel_norm), 4),
            pressure_persistence=persistence,
            pressure_change=round(press_change, 2),
            pressure_5bar=round(press_5bar, 2),
            pressure_10bar=round(press_10bar, 2),
            computation_time_ms=round(elapsed, 3),
        )


def math_sqrt_scale(window: int) -> float:
    """Scaling factor for sum of random variables under central limit theorem."""
    return float(np.sqrt(max(window, 1)))
