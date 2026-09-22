"""
Compression Engine (§6).

Computes multi-metric market compression score in [0, 1] using:
- ATR ratio (short vs long)
- Realized volatility percentile
- True range compression
- Consecutive candle overlap
- Range contraction ratio
- Directional entropy
- Displacement efficiency (net path / gross path)
"""
from __future__ import annotations

import math
import time
from typing import List, Optional

import numpy as np

from app.signals.strategies.vortex_snap.types import (
    Candle,
    CompressionResult,
    CompressionZone,
)
from app.signals.strategies.vortex_snap.config import CompressionConfig


def compute_true_ranges(candles: List[Candle]) -> List[float]:
    """Calculate true range for a sequence of candles."""
    trs: List[float] = []
    for i, c in enumerate(candles):
        if i == 0:
            trs.append(c.range)
        else:
            prev_close = candles[i - 1].close
            tr = max(c.high - c.low, abs(c.high - prev_close), abs(c.low - prev_close))
            trs.append(max(tr, 1e-9))
    return trs


def compute_atr(trs: List[float], period: int) -> float:
    """Simple moving average ATR over the last `period` bars."""
    if len(trs) < period:
        return float(np.mean(trs)) if trs else 1e-9
    return float(np.mean(trs[-period:]))


class CompressionEngine:
    """Measures multi-factor compression and classifies compression zones."""

    def __init__(self, config: Optional[CompressionConfig] = None) -> None:
        self.config = config or CompressionConfig()

    def compute(
        self,
        candles: List[Candle],
        prior_duration: int = 0,
    ) -> CompressionResult:
        """Compute point-in-time compression metrics at current candle.

        Args:
            candles: Candle sequence up to time T (minimum required ~25 bars).
            prior_duration: Bars previously spent in compression for state continuity.

        Returns:
            CompressionResult.
        """
        start_t = time.perf_counter()
        n = len(candles)
        if n < self.config.atr_long_period:
            return CompressionResult(
                compression_score=0.0,
                zone=CompressionZone.UNCOMPRESSED,
                atr_ratio=1.0,
                realized_vol_percentile=0.5,
                true_range_compression=0.0,
                candle_overlap=0.0,
                range_contraction=0.0,
                directional_entropy=0.5,
                displacement_efficiency=0.5,
                duration_bars=0,
                computation_time_ms=0.0,
            )

        trs = compute_true_ranges(candles)

        # 1. ATR Ratio: ATR_short / ATR_long
        atr_short = compute_atr(trs, self.config.atr_short_period)
        atr_long = compute_atr(trs, self.config.atr_long_period)
        atr_ratio = atr_short / max(atr_long, 1e-9)

        # When compressed, atr_ratio < 1.0 (e.g. 0.5 - 0.7).
        # Invert to [0, 1] compression measure:
        # e.g., ratio 0.5 -> score 1.0, ratio 1.5 -> score 0.0
        atr_comp_score = max(0.0, min(1.0, (1.5 - atr_ratio) / 1.0))

        # 2. Realized Volatility Percentile
        # Standard deviation of 1-min log returns over rolling window
        closes = np.array([c.close for c in candles], dtype=np.float64)
        log_rets = np.diff(np.log(closes))
        w_vol = self.config.realized_vol_window

        if len(log_rets) >= w_vol * 2:
            rolling_vols = [
                float(np.std(log_rets[i - w_vol : i]))
                for i in range(w_vol, len(log_rets) + 1)
            ]
            current_vol = rolling_vols[-1]
            # Percentile rank of current vol in recent history
            vol_pct = sum(1 for v in rolling_vols if v <= current_vol) / len(rolling_vols)
        else:
            current_vol = float(np.std(log_rets[-w_vol:])) if len(log_rets) >= w_vol else 1e-4
            vol_pct = 0.5

        # Lower volatility = higher compression
        vol_comp_score = max(0.0, min(1.0, 1.0 - vol_pct))

        # 3. True Range Compression (current TR vs recent median TR)
        recent_trs = trs[-self.config.atr_long_period :]
        median_tr = float(np.median(recent_trs))
        current_tr = trs[-1]
        tr_ratio = current_tr / max(median_tr, 1e-9)
        # Low current TR -> high compression
        tr_comp_score = max(0.0, min(1.0, (1.5 - tr_ratio) / 1.2))

        # 4. Consecutive Candle Overlap
        w_ov = min(self.config.overlap_window, n - 1)
        overlaps: List[float] = []
        for i in range(n - w_ov, n):
            c_curr = candles[i]
            c_prev = candles[i - 1]
            overlap_h = min(c_curr.high, c_prev.high)
            overlap_l = max(c_curr.low, c_prev.low)
            if overlap_h > overlap_l:
                overlap_range = overlap_h - overlap_l
                total_span = max(c_curr.high, c_prev.high) - min(c_curr.low, c_prev.low)
                overlaps.append(overlap_range / max(total_span, 1e-9))
            else:
                overlaps.append(0.0)
        avg_overlap = float(np.mean(overlaps)) if overlaps else 0.0

        # 5. High-Low Range Contraction
        w_cont = min(self.config.contraction_window, n)
        recent_span = max(c.high for c in candles[-w_cont:]) - min(c.low for c in candles[-w_cont:])
        longer_w = min(self.config.atr_long_period * 2, n)
        longer_span = max(c.high for c in candles[-longer_w:]) - min(c.low for c in candles[-longer_w:])
        # Span ratio: short span / longer span (when contracted, recent_span << longer_span)
        span_ratio = recent_span / max(longer_span, 1e-9)
        span_comp_score = max(0.0, min(1.0, (0.60 - span_ratio) / 0.45))

        # 6. Directional Entropy (oscillating bodies = higher compression)
        w_ent = min(self.config.entropy_window, n)
        signs = [1 if c.close >= c.open else 0 for c in candles[-w_ent:]]
        p_up = sum(signs) / len(signs)
        p_down = 1.0 - p_up
        if 0.0 < p_up < 1.0:
            entropy = -(p_up * math.log2(p_up) + p_down * math.log2(p_down))
        else:
            entropy = 0.0  # One-sided trending moves have low entropy

        # 7. Displacement Efficiency (Net path / Gross path)
        w_disp = min(self.config.displacement_window, n)
        net_disp = abs(candles[-1].close - candles[-w_disp].close)
        gross_path = sum(abs(candles[i].close - candles[i - 1].close) for i in range(n - w_disp + 1, n))
        if gross_path < 1e-6:
            disp_eff = 0.0
        else:
            disp_eff = max(0.0, min(1.0, net_disp / gross_path))
        # Low displacement efficiency = oscillating tightly = high compression
        disp_comp_score = max(0.0, min(1.0, 1.0 - disp_eff))

        # Multi-factor composite compression score
        composite_score = (
            0.22 * atr_comp_score
            + 0.18 * vol_comp_score
            + 0.15 * tr_comp_score
            + 0.15 * avg_overlap
            + 0.12 * span_comp_score
            + 0.08 * entropy
            + 0.10 * disp_comp_score
        )
        final_score = max(0.0, min(1.0, composite_score))

        # Zone classification
        if final_score >= self.config.extreme_threshold:
            zone = CompressionZone.EXTREME
        elif final_score >= self.config.armed_threshold:
            zone = CompressionZone.ARMED
        elif final_score >= self.config.watch_threshold:
            zone = CompressionZone.WATCH
        else:
            zone = CompressionZone.UNCOMPRESSED

        # Update compression duration
        if final_score >= self.config.watch_threshold:
            duration = prior_duration + 1
        else:
            duration = 0

        elapsed = (time.perf_counter() - start_t) * 1000.0

        return CompressionResult(
            compression_score=round(final_score, 4),
            zone=zone,
            atr_ratio=round(atr_ratio, 4),
            realized_vol_percentile=round(vol_pct, 4),
            true_range_compression=round(tr_comp_score, 4),
            candle_overlap=round(avg_overlap, 4),
            range_contraction=round(span_comp_score, 4),
            directional_entropy=round(entropy, 4),
            displacement_efficiency=round(disp_eff, 4),
            duration_bars=duration,
            computation_time_ms=round(elapsed, 3),
        )
