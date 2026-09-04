"""
Regime Detector — §2, §4

Stateless, pure function of market context.
Detects standardized regime per §4 specification.
"""
from __future__ import annotations

from app.ai.schemas import Regime, Direction, VolatilityLevel, RegimeObject


class RegimeDetector:
    """
    Pure function regime detection from market context.

    Per §4: Standardized regime object with TREND/RANGE/BREAKOUT/REVERSAL/HIGH_VOLATILITY/LOW_VOLATILITY/UNKNOWN.
    Per §2: Stateless, no I/O.
    """

    TREND_THRESHOLD_ADX = 22.0
    TREND_THRESHOLD_RSI_LOW = 48.0
    TREND_THRESHOLD_RSI_HIGH = 52.0
    VOLATILE_THRESHOLD_BW = 4.5
    VOLATILE_THRESHOLD_VIX = 18.0
    SQUEEZE_THRESHOLD_BW = 2.2
    SQUEEZE_THRESHOLD_ADX = 20.0

    def detect(
        self,
        adx_14: float = 20.0,
        rsi_14: float = 50.0,
        supertrend_direction: str = "FLAT",
        bollinger_bandwidth: float = 3.0,
        vix_value: float = 14.0,
        ema_20: float = 0.0,
        current_price: float = 0.0,
        ema_slope: float = 0.0,
        volume_percentile: float = 50.0,
        atr_percentile: float = 50.0,
    ) -> RegimeObject:
        """
        Detect market regime from technical indicators.

        Args:
            adx_14: ADX indicator (trend strength)
            rsi_14: RSI indicator (momentum)
            supertrend_direction: BULLISH/BEARISH/FLAT
            bollinger_bandwidth: Volatility measure
            vix_value: India VIX value
            ema_20: 20-period EMA
            current_price: Current price
            ema_slope: EMA slope direction
            volume_percentile: Volume relative to average
            atr_percentile: ATR relative to average

        Returns:
            RegimeObject with standardized regime classification
        """
        if hasattr(adx_14, "regime") and hasattr(adx_14, "current_price"):
            ctx = adx_14
            if ctx.regime and getattr(ctx.regime, "regime", None) != Regime.UNKNOWN:
                return ctx.regime
            return self.detect(
                adx_14=getattr(ctx, "momentum", 20.0) or 20.0,
                current_price=getattr(ctx, "current_price", 0.0) or 0.0,
            )
        elif isinstance(adx_14, dict):
            return self.detect_from_context(adx_14)

        is_strong_trend = adx_14 >= self.TREND_THRESHOLD_ADX
        is_bullish_rsi = rsi_14 >= self.TREND_THRESHOLD_RSI_HIGH
        is_bearish_rsi = rsi_14 <= self.TREND_THRESHOLD_RSI_LOW
        is_squeeze = bollinger_bandwidth <= self.SQUEEZE_THRESHOLD_BW and adx_14 < self.SQUEEZE_THRESHOLD_ADX
        is_expansion = bollinger_bandwidth >= self.VOLATILE_THRESHOLD_BW or vix_value >= self.VOLATILE_THRESHOLD_VIX

        is_bullish_structure = (
            is_strong_trend
            and is_bullish_rsi
            and supertrend_direction == "BULLISH"
            and (ema_20 == 0 or current_price >= ema_20)
        )

        is_bearish_structure = (
            is_strong_trend
            and is_bearish_rsi
            and supertrend_direction == "BEARISH"
            and (ema_20 == 0 or current_price <= ema_20)
        )

        if is_squeeze:
            regime = Regime.BREAKOUT
            direction = Direction.NEUTRAL
            strength = min(100, int(50 + (self.SQUEEZE_THRESHOLD_BW - bollinger_bandwidth) * 20))
            volatility = VolatilityLevel.LOW
            confidence = 88
        elif is_expansion:
            regime = Regime.HIGH_VOLATILITY
            direction = Direction.NEUTRAL
            strength = min(100, int(50 + (bollinger_bandwidth - self.VOLATILE_THRESHOLD_BW) * 15))
            volatility = VolatilityLevel.HIGH
            confidence = 82
        elif is_bullish_structure:
            regime = Regime.TREND
            direction = Direction.BULLISH
            strength = min(100, int(adx_14 * 4))
            volatility = VolatilityLevel.MEDIUM
            confidence = 90
        elif is_bearish_structure:
            regime = Regime.TREND
            direction = Direction.BEARISH
            strength = min(100, int(adx_14 * 4))
            volatility = VolatilityLevel.MEDIUM
            confidence = 90
        elif vix_value < 14.5:
            regime = Regime.LOW_VOLATILITY
            direction = Direction.NEUTRAL
            strength = min(100, int((20 - adx_14) * 3))
            volatility = VolatilityLevel.LOW
            confidence = 80
        elif adx_14 < 20 and bollinger_bandwidth < 3.5:
            regime = Regime.RANGE
            direction = Direction.NEUTRAL
            strength = min(100, int((20 - adx_14) * 5))
            volatility = VolatilityLevel.MEDIUM
            confidence = 78
        else:
            regime = Regime.UNKNOWN
            direction = Direction.NEUTRAL
            strength = 0
            volatility = VolatilityLevel.MEDIUM
            confidence = 50

        return RegimeObject(
            regime=regime,
            direction=direction,
            strength=strength,
            volatility=volatility,
            confidence=confidence,
        )

    def detect_from_context(self, context: dict) -> RegimeObject:
        """
        Detect regime from pre-built context dict.
        Convenience method for pipeline integration.
        """
        return self.detect(
            adx_14=context.get("adx_14", 20.0),
            rsi_14=context.get("rsi_14", 50.0),
            supertrend_direction=context.get("supertrend_direction", "FLAT"),
            bollinger_bandwidth=context.get("bollinger_bandwidth", 3.0),
            vix_value=context.get("vix_value", 14.0),
            ema_20=context.get("ema_20", 0.0),
            current_price=context.get("current_price", 0.0),
            ema_slope=context.get("ema_slope", 0.0),
            volume_percentile=context.get("volume_percentile", 50.0),
            atr_percentile=context.get("atr_percentile", 50.0),
        )


regime_detector = RegimeDetector()
