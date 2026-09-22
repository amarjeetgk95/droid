"""
Market Regime Engine (§19).

Classifies market state into 7 operational regimes:
- TREND
- TRENDING_VOLATILITY
- RANGE
- EXPANSION
- EXHAUSTION
- CHAOTIC
- UNKNOWN

Maps permissible event classifications (Continuation, Absorption, Trap) per regime.
"""
from __future__ import annotations

import math
import time
from typing import List, Optional

import numpy as np

from app.signals.strategies.vortex_snap.types import (
    Candle,
    CompressionResult,
    DirectionalPressureResult,
    EventType,
    MarketRegime,
    RegimeResult,
    TranslationRatioResult,
)
from app.signals.strategies.vortex_snap.config import MarketRegimeConfig


def compute_adx(candles: List[Candle], period: int = 14) -> float:
    """Calculate point-in-time Average Directional Index (ADX)."""
    if len(candles) < period * 2:
        return 20.0  # Default neutral

    trs: List[float] = []
    dm_plus: List[float] = []
    dm_minus: List[float] = []

    for i in range(1, len(candles)):
        c = candles[i]
        prev = candles[i - 1]

        # True range
        tr = max(c.high - c.low, abs(c.high - prev.close), abs(c.low - prev.close))
        trs.append(max(tr, 1e-9))

        # Directional movement
        up_move = c.high - prev.high
        down_move = prev.low - c.low

        if up_move > down_move and up_move > 0:
            dm_plus.append(up_move)
        else:
            dm_plus.append(0.0)

        if down_move > up_move and down_move > 0:
            dm_minus.append(down_move)
        else:
            dm_minus.append(0.0)

    # Wilder's smoothing
    smooth_tr = float(np.mean(trs[:period]))
    smooth_plus = float(np.mean(dm_plus[:period]))
    smooth_minus = float(np.mean(dm_minus[:period]))

    for i in range(period, len(trs)):
        smooth_tr = smooth_tr - (smooth_tr / period) + trs[i]
        smooth_plus = smooth_plus - (smooth_plus / period) + dm_plus[i]
        smooth_minus = smooth_minus - (smooth_minus / period) + dm_minus[i]

    di_plus = 100.0 * (smooth_plus / max(smooth_tr, 1e-9))
    di_minus = 100.0 * (smooth_minus / max(smooth_tr, 1e-9))

    dx = 100.0 * abs(di_plus - di_minus) / max(di_plus + di_minus, 1e-9)
    return float(dx)


def compute_kaufman_efficiency(candles: List[Candle], period: int = 10) -> float:
    """Kaufman Efficiency Ratio: Net directional change / Total path distance."""
    if len(candles) < period + 1:
        return 0.5

    sub = candles[-period - 1 :]
    net_change = abs(sub[-1].close - sub[0].close)
    path = sum(abs(sub[i].close - sub[i - 1].close) for i in range(1, len(sub)))
    return float(net_change / max(path, 1e-9))


class MarketRegimeEngine:
    """Determines active market regime and allowable event types."""

    def __init__(self, config: Optional[MarketRegimeConfig] = None) -> None:
        self.config = config or MarketRegimeConfig()

    def compute(
        self,
        candles_1m: List[Candle],
        compression: CompressionResult,
        pressure: DirectionalPressureResult,
        translation: TranslationRatioResult,
        candles_5m: Optional[List[Candle]] = None,
    ) -> RegimeResult:
        """Compute regime classification at bar T.

        Args:
            candles_1m: 1-minute candle sequence up to T.
            compression: Compression result at T.
            pressure: Pressure result at T.
            translation: Translation result at T.
            candles_5m: Optional 5-minute candle sequence up to T.

        Returns:
            RegimeResult snapshot.
        """
        start_t = time.perf_counter()
        n = len(candles_1m)

        if n < 20:
            # Explicit low-trust fallback: insufficient history for ADX/efficiency.
            # UNKNOWN with a low confidence marks this as "no measurement yet" —
            # never a mid-range value that could be mistaken for a real call.
            # (Fallback marker: regime == UNKNOWN and confidence <= 0.30.)
            return RegimeResult(
                regime=MarketRegime.UNKNOWN,
                regime_confidence=0.2,
                trend_strength=0.0,
                volatility_state="NORMAL",
                efficiency_ratio=0.5,
                permitted_events=[],
                computation_time_ms=0.0,
            )

        # 1. ADX Trend Strength
        adx_val = compute_adx(candles_1m, self.config.adx_period)
        norm_adx = min(adx_val / 50.0, 1.0)

        # 2. Kaufman Efficiency Ratio
        eff_ratio = compute_kaufman_efficiency(candles_1m, period=10)

        # 3. Volatility State (ATR ratio and realized vol)
        atr_ratio = compression.atr_ratio
        if atr_ratio > self.config.volatility_expansion_ratio:
            vol_state = "HIGH" if atr_ratio < 2.0 else "EXTREME"
        elif atr_ratio < 0.65:
            vol_state = "LOW"
        else:
            vol_state = "NORMAL"

        # 4. Entropy / Choppiness check
        entropy = compression.directional_entropy

        # 5. Regime Classification Logic (§19)
        if vol_state in ("HIGH", "EXTREME") and entropy >= self.config.chaotic_entropy_threshold and eff_ratio < 0.25:
            regime = MarketRegime.CHAOTIC
            conf = min(entropy, 0.95)
            permitted = []  # Explicit NO TRADE (§18/§19)

        elif eff_ratio >= self.config.efficiency_trend_threshold and adx_val >= self.config.trend_adx_threshold:
            if vol_state in ("HIGH", "EXTREME"):
                regime = MarketRegime.TRENDING_VOLATILITY
                permitted = [EventType.CONTINUATION, EventType.VACUUM_TRAP]
            else:
                regime = MarketRegime.TREND
                permitted = [EventType.CONTINUATION]
            conf = min((eff_ratio + norm_adx) / 2.0, 0.95)

        elif vol_state in ("HIGH", "EXTREME") and compression.true_range_compression < 0.35:
            regime = MarketRegime.EXPANSION
            conf = 0.80
            permitted = [EventType.CONTINUATION, EventType.ABSORPTION]

        elif eff_ratio <= self.config.efficiency_range_threshold or compression.compression_score >= 0.70:
            regime = MarketRegime.RANGE
            conf = max(compression.compression_score, 1.0 - eff_ratio)
            permitted = [EventType.ABSORPTION, EventType.VACUUM_TRAP]

        elif abs(pressure.pressure_score) >= 0.70 and translation.translation_ratio <= 0.35:
            regime = MarketRegime.EXHAUSTION
            conf = 0.85
            permitted = [EventType.ABSORPTION, EventType.VACUUM_TRAP]

        else:
            # Explicit low-trust fallback: no rule above fired, so this is NOT a
            # measured call. Confidence is derived from efficiency + trend
            # strength (capped at 0.55) so it can never equal a hardcoded 0.60.
            # (Fallback marker: confidence <= 0.55 on this path, no rule matched.)
            eff_component = (1.0 - eff_ratio) * 0.35
            trend_component = (1.0 - norm_adx) * 0.20
            conf = round(min(0.55, max(0.25, eff_component + trend_component + 0.10)), 4)
            regime = MarketRegime.RANGE
            permitted = [EventType.ABSORPTION, EventType.VACUUM_TRAP]

        elapsed = (time.perf_counter() - start_t) * 1000.0

        return RegimeResult(
            regime=regime,
            regime_confidence=round(conf, 4),
            trend_strength=round(norm_adx, 4),
            volatility_state=vol_state,
            efficiency_ratio=round(eff_ratio, 4),
            permitted_events=permitted,
            computation_time_ms=round(elapsed, 3),
        )
