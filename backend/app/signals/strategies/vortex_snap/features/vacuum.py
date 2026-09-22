"""
Liquidity Vacuum Detector (§10).

Detects sudden range expansion following compression, indicating rapid displacement
through thinned orderbook liquidity.
"""
from __future__ import annotations

import time
from typing import List, Optional

import numpy as np

from app.signals.strategies.vortex_snap.types import (
    Candle,
    CompressionResult,
    LiquidityVacuumResult,
)
from app.signals.strategies.vortex_snap.config import LiquidityVacuumConfig


class LiquidityVacuumDetector:
    """Measures range expansion, volume shock, and directional close placement."""

    def __init__(self, config: Optional[LiquidityVacuumConfig] = None) -> None:
        self.config = config or LiquidityVacuumConfig()

    def compute(
        self,
        candles: List[Candle],
        compression: CompressionResult,
        prior_compression_history: Optional[List[float]] = None,
    ) -> LiquidityVacuumResult:
        """Evaluate liquidity vacuum conditions at current candle.

        Args:
            candles: Candle sequence up to time T.
            compression: Current compression result.
            prior_compression_history: Rolling history of compression scores (prior 5-10 bars).

        Returns:
            LiquidityVacuumResult snapshot.
        """
        start_t = time.perf_counter()
        n = len(candles)
        if n < 5:
            return LiquidityVacuumResult(
                liquidity_vacuum_score=0.0,
                is_vacuum_detected=False,
                range_expansion=1.0,
                volume_shock=1.0,
                close_location=0.5,
                overlap_penalty=0.0,
                prior_compression_passed=False,
                computation_time_ms=0.0,
            )

        current_candle = candles[-1]
        c_range = max(current_candle.high - current_candle.low, 1e-9)

        # 1. True Range calculation for recent bars
        trs: List[float] = []
        for i in range(max(1, n - 20), n):
            prev_c = candles[i - 1].close
            c = candles[i]
            tr = max(c.high - c.low, abs(c.high - prev_c), abs(c.low - prev_c))
            trs.append(max(tr, 1e-9))

        curr_tr = max(
            current_candle.high - current_candle.low,
            abs(current_candle.high - candles[-2].close),
            abs(current_candle.low - candles[-2].close),
        )
        med_tr = float(np.median(trs)) if trs else 1e-9
        range_expansion = curr_tr / max(med_tr, 1e-9)

        # 2. Volume Shock
        recent_vols = [c.volume for c in candles[-min(20, n) : -1]]
        med_vol = float(np.median(recent_vols)) if recent_vols else 1.0
        volume_shock = current_candle.volume / max(med_vol, 1e-9)

        # 3. Close Location Factor (direction-agnostic displacement conviction)
        # Position of close inside bar: 0.0 at low, 1.0 at high
        close_pos = (current_candle.close - current_candle.low) / c_range
        close_location = max(0.0, min(1.0, close_pos))
        # Extreme close (either near high or near low) represents conviction
        conviction = 2.0 * abs(close_location - 0.5)  # in [0.0, 1.0]

        # 4. Overlap with Previous Candle (Penalty)
        prev_candle = candles[-2]
        overlap_h = min(current_candle.high, prev_candle.high)
        overlap_l = max(current_candle.low, prev_candle.low)
        if overlap_h > overlap_l:
            overlap_pct = (overlap_h - overlap_l) / c_range
        else:
            overlap_pct = 0.0
        overlap_penalty = max(0.0, min(1.0, overlap_pct))

        # 5. Transition validation: Preceded by compression
        # Either current duration is high, prior history was compressed, or candles[:-1] was compressed
        prior_comp_passed = False
        if compression.duration_bars >= 1 or compression.compression_score >= self.config.prior_compression_threshold:
            prior_comp_passed = True
        prior_history = prior_compression_history[:-1] if prior_compression_history else []
        if prior_history and any(s >= self.config.prior_compression_threshold for s in prior_history[-5:]):
            prior_comp_passed = True
        elif len(candles) >= 15:
            from app.signals.strategies.vortex_snap.features.compression import CompressionEngine
            prior_comp = CompressionEngine().compute(candles[:-1])
            if prior_comp.compression_score >= 0.50:
                prior_comp_passed = True

        # Normalized sub-scores
        exp_score = max(0.0, min(1.0, (range_expansion - 1.0) / 1.5))
        vol_score = max(0.0, min(1.0, (volume_shock - 1.0) / 1.5))
        overlap_factor = max(0.0, 1.0 - (overlap_penalty / max(self.config.max_overlap_penalty, 0.1)))

        # Composite liquidity vacuum score (§10)
        # range_expansion * volume_shock * close_location * (1 - overlap_penalty)
        raw_vacuum = exp_score * 0.40 + vol_score * 0.25 + conviction * 0.20 + overlap_factor * 0.15
        if prior_comp_passed:
            raw_vacuum *= 1.25  # Boost when cleanly breaking out of verified compression
        else:
            raw_vacuum *= 0.70  # Dampen if expansion occurred without compression

        final_score = max(0.0, min(1.0, raw_vacuum))
        is_vacuum = (
            final_score >= 0.60
            and range_expansion >= self.config.min_range_expansion
            and conviction >= 0.50
        )

        elapsed = (time.perf_counter() - start_t) * 1000.0

        return LiquidityVacuumResult(
            liquidity_vacuum_score=round(final_score, 4),
            is_vacuum_detected=is_vacuum,
            range_expansion=round(range_expansion, 3),
            volume_shock=round(volume_shock, 3),
            close_location=round(close_location, 4),
            overlap_penalty=round(overlap_penalty, 4),
            prior_compression_passed=prior_comp_passed,
            computation_time_ms=round(elapsed, 3),
        )
