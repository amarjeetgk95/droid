"""Option Market Pressure Index (OMPI) v0.1 (§15-§18).

Proprietary experimental indicator combining directional price structure,
options market positioning, participation volume dynamics, volatility regime,
and option decay pressure into a unified -100 to +100 pressure index.

Every sub-component is fully transparent and exposed in the output.
"""

import math
from typing import Any, Dict, Optional
from datetime import datetime, timezone

from app.quant.indicators import (
    calculate_adx,
    calculate_atr,
    calculate_bollinger_bands,
    calculate_ema,
    calculate_rsi,
)
from app.research.enums import (
    DataQualityStatus,
    Direction,
    ForecastHorizon,
    IndicatorCategory,
    IndicatorLifecycle,
)
from app.research.indicator_base import IndicatorBase
from app.research.models import IndicatorContext, IndicatorOutput


class OMPIIndicator(IndicatorBase):
    """Option Market Pressure Index (OMPI) v0.1 (§15-§18).
    
    Synthesizes five structural market pressure vectors:
      1. Directional Price Pressure (P_dir)      [weight: 0.30]
      2. Options Position Pressure (P_opt)       [weight: 0.25]
      3. Participation & Volume Pressure (P_part) [weight: 0.20]
      4. Volatility Regime Pressure (P_vol)      [weight: 0.15]
      5. Option Cost / Decay Pressure (P_decay)  [weight: 0.10]
    
    Outputs a continuous pressure score in [-100.0, +100.0].
    """

    @property
    def indicator_id(self) -> str:
        return "ompi"

    @property
    def name(self) -> str:
        return "Option Market Pressure Index (OMPI)"

    @property
    def version(self) -> str:
        return "0.1.0"

    @property
    def category(self) -> IndicatorCategory:
        return IndicatorCategory.PROPRIETARY

    @property
    def lifecycle(self) -> IndicatorLifecycle:
        return IndicatorLifecycle.EXPERIMENTAL

    @property
    def description(self) -> str:
        return (
            "Proprietary 5-vector composite measuring underlying directional momentum, "
            "options positioning (PCR/walls/max pain), volume participation, volatility regime, "
            "and theta decay friction."
        )

    @property
    def formula_summary(self) -> str:
        return (
            "OMPI = 0.30*P_dir + 0.25*P_opt + 0.20*P_part + 0.15*P_vol + 0.10*P_decay; "
            "Bullish >= 20.0, Bearish <= -20.0"
        )

    @property
    def default_parameters(self) -> Dict[str, Any]:
        return {
            "w_dir": 0.30,
            "w_opt": 0.25,
            "w_part": 0.20,
            "w_vol": 0.15,
            "w_decay": 0.10,
            "bull_threshold": 20.0,
            "bear_threshold": -20.0,
        }

    async def calculate(self, context: IndicatorContext) -> IndicatorOutput:
        w_dir = float(context.parameters.get("w_dir", 0.30))
        w_opt = float(context.parameters.get("w_opt", 0.25))
        w_part = float(context.parameters.get("w_part", 0.20))
        w_vol = float(context.parameters.get("w_vol", 0.15))
        w_decay = float(context.parameters.get("w_decay", 0.10))
        bull_th = float(context.parameters.get("bull_threshold", 20.0))
        bear_th = float(context.parameters.get("bear_threshold", -20.0))

        closes = [float(c["close"]) for c in context.candles]
        highs = [float(c["high"]) for c in context.candles]
        lows = [float(c["low"]) for c in context.candles]
        opens = [float(c["open"]) for c in context.candles]
        volumes = [float(c.get("volume", 0.0) or 0.0) for c in context.candles]

        current_price = closes[-1] if closes else context.current_price
        atr = calculate_atr(highs, lows, closes, 14) if len(closes) >= 14 else (current_price * 0.005)

        # -------------------------------------------------------------
        # Vector 1: Directional Price Pressure (P_dir) [-100, +100]
        # -------------------------------------------------------------
        ema_20 = calculate_ema(closes, 20) or current_price
        ema_50 = calculate_ema(closes, 50) or current_price
        rsi = calculate_rsi(closes, 14)

        p_dir_score = 0.0
        # Price vs EMAs
        if current_price > ema_20:
            p_dir_score += 30.0
        else:
            p_dir_score -= 30.0

        if ema_20 > ema_50:
            p_dir_score += 25.0
        else:
            p_dir_score -= 25.0

        # RSI tilt: maps (rsi - 50) * 0.9 into [-45, +45]
        rsi_tilt = max(-45.0, min(45.0, (rsi - 50.0) * 0.9))
        p_dir_score += rsi_tilt
        p_dir = round(max(-100.0, min(100.0, p_dir_score)), 2)

        # -------------------------------------------------------------
        # Vector 2: Options Position Pressure (P_opt) [-100, +100]
        # -------------------------------------------------------------
        opt_ctx = context.options_context or {}
        pcr_oi = float(opt_ctx.get("pcr_oi", 1.0) or 1.0)
        call_wall = opt_ctx.get("call_wall")
        put_wall = opt_ctx.get("put_wall")
        max_pain = opt_ctx.get("max_pain")

        p_opt_score = 0.0
        # PCR pressure: PCR > 1.0 indicates bullish put accumulation; PCR < 1.0 indicates bearish call writing
        # Center around 1.0: (PCR - 1.0) * 80.0
        pcr_component = max(-50.0, min(50.0, (pcr_oi - 1.0) * 80.0))
        p_opt_score += pcr_component

        # Gravitational pull to Max Pain:
        if max_pain and max_pain > 0:
            pain_dist_pct = ((max_pain - current_price) / current_price) * 100.0
            p_opt_score += max(-25.0, min(25.0, pain_dist_pct * 15.0))

        # Wall proximity bounce / rejection:
        if call_wall and call_wall > current_price:
            call_dist_pct = ((call_wall - current_price) / current_price) * 100.0
            if call_dist_pct < 0.3:  # Pinning / resistance at call wall
                p_opt_score -= 25.0
        if put_wall and put_wall < current_price:
            put_dist_pct = ((current_price - put_wall) / current_price) * 100.0
            if put_dist_pct < 0.3:  # Bounce support at put wall
                p_opt_score += 25.0

        p_opt = round(max(-100.0, min(100.0, p_opt_score)), 2)

        # -------------------------------------------------------------
        # Vector 3: Participation Pressure (P_part) [-100, +100]
        # -------------------------------------------------------------
        vol_len = min(len(volumes), 20)
        vol_sub = volumes[-vol_len:]
        avg_vol = sum(vol_sub) / vol_len if vol_len > 0 else 1.0
        curr_vol = volumes[-1] if volumes else 1.0
        rel_vol = curr_vol / avg_vol if avg_vol > 0 else 1.0

        # Sign of candle: close >= open is green (+), else red (-)
        candle_sign = 1.0 if closes[-1] >= opens[-1] else -1.0
        # Volume magnitude multiplier: relative vol scaled
        vol_power = min(3.0, max(0.5, rel_vol))
        p_part_score = candle_sign * (vol_power / 3.0) * 100.0
        p_part = round(max(-100.0, min(100.0, p_part_score)), 2)

        # -------------------------------------------------------------
        # Vector 4: Volatility Regime Pressure (P_vol) [-100, +100]
        # -------------------------------------------------------------
        _, _, _, bb_bandwidth, bb_pct_b = calculate_bollinger_bands(closes, 20, 2.0)
        atm_iv = float(opt_ctx.get("atm_iv", 15.0) or 15.0)

        # High IV + expanding bands amplifies momentum; low IV + squeeze dampens
        iv_deviation = (atm_iv - 14.5) * 4.0  # Centered at typical 14.5 NIFTY IV
        bb_expansion = (bb_pct_b - 0.5) * 100.0  # Directional band tilt
        p_vol_score = (0.6 * bb_expansion) + (0.4 * max(-40.0, min(40.0, iv_deviation)))
        p_vol = round(max(-100.0, min(100.0, p_vol_score)), 2)

        # -------------------------------------------------------------
        # Vector 5: Cost / Decay Pressure (P_decay) [-100, +100]
        # -------------------------------------------------------------
        dte = float(opt_ctx.get("days_to_expiry", 2.0) or 2.0)
        atm_theta = float(opt_ctx.get("atm_theta", -10.0) or -10.0)

        # On expiry day (DTE <= 0.5) and high theta, decay heavily penalizes trend continuation
        decay_severity = abs(atm_theta) / (dte + 0.2)
        # Decay pressure is dampening: pulls score toward mean reversion (opposing strong moves)
        decay_dampener = -1.0 * math.copysign(min(50.0, decay_severity), p_dir)
        p_decay = round(max(-100.0, min(100.0, decay_dampener)), 2)

        # -------------------------------------------------------------
        # Composite OMPI Weighted Score
        # -------------------------------------------------------------
        raw_composite = (
            w_dir * p_dir +
            w_opt * p_opt +
            w_part * p_part +
            w_vol * p_vol +
            w_decay * p_decay
        )
        total_weight = w_dir + w_opt + w_part + w_vol + w_decay
        normalized_score = round(max(-100.0, min(100.0, raw_composite / total_weight)), 2)

        # Direction determination
        if normalized_score >= bull_th:
            direction = Direction.BULLISH
        elif normalized_score <= bear_th:
            direction = Direction.BEARISH
        else:
            direction = Direction.NEUTRAL

        # Analytical confidence calculation
        confidence = round(min(1.0, abs(normalized_score) / 60.0), 3)

        # Target and Invalidation
        target_price = round(current_price + (1.6 * atr) if direction == Direction.BULLISH else current_price - (1.6 * atr), 2)
        invalidation_price = round(current_price - (1.0 * atr) if direction == Direction.BULLISH else current_price + (1.0 * atr), 2)

        data_quality = DataQualityStatus.LIVE if opt_ctx.get("available", False) else DataQualityStatus.DEGRADED

        return IndicatorOutput(
            indicator_id=self.indicator_id,
            version=self.version,
            timestamp=context.timestamp,
            instrument=context.instrument,
            timeframe=context.timeframe,
            direction=direction,
            score=normalized_score,
            confidence=confidence,
            raw_value=raw_composite,
            normalized_value=normalized_score,
            component_values={
                "p_dir": p_dir,
                "p_opt": p_opt,
                "p_part": p_part,
                "p_vol": p_vol,
                "p_decay": p_decay,
                "pcr_oi": pcr_oi,
                "relative_volume": round(rel_vol, 2),
                "atm_iv": atm_iv,
                "days_to_expiry": dte,
                "call_wall": call_wall,
                "put_wall": put_wall,
                "max_pain": max_pain,
                "weights": {
                    "w_dir": w_dir,
                    "w_opt": w_opt,
                    "w_part": w_part,
                    "w_vol": w_vol,
                    "w_decay": w_decay,
                },
            },
            regime_context=context.market_regime.value if context.market_regime else None,
            horizon=ForecastHorizon.HORIZON_15M,
            horizon_candles=5,
            target_price=target_price,
            invalidation_price=invalidation_price,
            data_quality=data_quality,
            metadata={"source": "research.indicators.ompi.OMPIIndicator"},
        )
