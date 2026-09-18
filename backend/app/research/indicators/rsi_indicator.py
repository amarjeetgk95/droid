"""RSI Standard Indicator implementation for the Research Laboratory (§46)."""

from typing import Any

from app.quant.indicators import calculate_rsi
from app.research.enums import (
    IndicatorCategory,
    IndicatorLifecycle,
)
from app.research.indicators.base import BuiltinIndicator, IndicatorMetadata
from app.research.models import IndicatorContext, IndicatorOutput


class RSIIndicator(BuiltinIndicator):
    """Relative Strength Index standard indicator.
    
    Normalizes Wilder's smoothed RSI (0-100) to standard research scale (-100 to +100).
    Score = (RSI - 50) * 2.
    """

    METADATA = IndicatorMetadata(
        indicator_id="rsi",
        name="Relative Strength Index (RSI)",
        version="1.0.0",
        category=IndicatorCategory.STANDARD,
        lifecycle=IndicatorLifecycle.PRODUCTION,
    )

    @property
    def description(self) -> str:
        return "14-period Relative Strength Index with Wilder's smoothing, centered at 0 on [-100, +100]."

    @property
    def formula_summary(self) -> str:
        return "Score = (RSI(14) - 50) * 2; Bullish > 10, Bearish < -10"

    @property
    def default_parameters(self) -> dict[str, Any]:
        return {"period": 14, "overbought": 70, "oversold": 30, "bull_threshold": 10.0, "bear_threshold": -10.0}

    async def calculate(self, context: IndicatorContext) -> IndicatorOutput:
        period = self._int_param(context, "period", 14)
        bull_th = self._float_param(context, "bull_threshold", 10.0)
        bear_th = self._float_param(context, "bear_threshold", -10.0)

        closes, highs, lows, current_price = self._extract_series(context)

        raw_rsi = calculate_rsi(closes, period=period)
        score = round(max(-100.0, min(100.0, (raw_rsi - 50.0) * 2.0)), 2)

        direction = self._resolve_direction(score, bull_th, bear_th)
        confidence = self._resolve_confidence(score, 80.0)

        atr = self._guarded_atr(highs, lows, closes, current_price)
        target_price, invalidation_price = self._bracket_prices(current_price, atr, direction)

        return self._build_output(
            context,
            direction=direction,
            score=score,
            confidence=confidence,
            raw_value=raw_rsi,
            component_values={
                "rsi": raw_rsi,
                "period": period,
                "overbought": context.parameters.get("overbought", 70),
                "oversold": context.parameters.get("oversold", 30),
            },
            target_price=target_price,
            invalidation_price=invalidation_price,
            metadata={"source": "quant.indicators.calculate_rsi"},
        )
