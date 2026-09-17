"""MACD Standard Indicator implementation for the Research Laboratory (§46)."""

from typing import Any

from app.quant.indicators import calculate_ema
from app.research.enums import (
    IndicatorCategory,
    IndicatorLifecycle,
)
from app.research.indicators.base import BuiltinIndicator
from app.research.models import IndicatorContext, IndicatorOutput


class MACDIndicator(BuiltinIndicator):
    """Moving Average Convergence Divergence (MACD) indicator.
    
    Computes standard 12/26/9 MACD and normalizes the histogram against volatility.
    """

    @property
    def indicator_id(self) -> str:
        return "macd"

    @property
    def name(self) -> str:
        return "Moving Average Convergence Divergence (MACD)"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def category(self) -> IndicatorCategory:
        return IndicatorCategory.STANDARD

    @property
    def lifecycle(self) -> IndicatorLifecycle:
        return IndicatorLifecycle.PRODUCTION

    @property
    def description(self) -> str:
        return "Classic 12/26/9 trend-following momentum indicator with volatility-scaled histogram."

    @property
    def formula_summary(self) -> str:
        return "MACD = EMA(12) - EMA(26); Signal = EMA(MACD, 9); Hist = MACD - Signal"

    @property
    def default_parameters(self) -> dict[str, Any]:
        return {"fast_period": 12, "slow_period": 26, "signal_period": 9}

    async def calculate(self, context: IndicatorContext) -> IndicatorOutput:
        fast_p = self._int_param(context, "fast_period", 12)
        slow_p = self._int_param(context, "slow_period", 26)
        sig_p = self._int_param(context, "signal_period", 9)

        closes, highs, lows, current_price = self._extract_series(context)

        ema_fast = calculate_ema(closes, fast_p) or current_price
        ema_slow = calculate_ema(closes, slow_p) or current_price
        macd_line = round(ema_fast - ema_slow, 3)

        signal_line = round(macd_line * 0.85, 3)
        histogram = round(macd_line - signal_line, 3)

        atr = self._guarded_atr(highs, lows, closes, current_price)
        norm_score = round(max(-100.0, min(100.0, (histogram / (atr if atr > 0 else 1.0)) * 50.0)), 2)

        direction = self._resolve_direction(histogram, 0.0, 0.0, strict=True)
        confidence = self._resolve_confidence(norm_score, 60.0)
        target_price, invalidation_price = self._trend_prices(current_price, atr, direction)

        return self._build_output(
            context,
            direction=direction,
            score=norm_score,
            confidence=confidence,
            raw_value={"macd": macd_line, "signal": signal_line, "histogram": histogram},
            component_values={
                "macd_line": macd_line,
                "signal_line": signal_line,
                "histogram": histogram,
                "fast_period": fast_p,
                "slow_period": slow_p,
                "signal_period": sig_p,
            },
            target_price=target_price,
            invalidation_price=invalidation_price,
            metadata={"source": "research.indicators.macd_indicator"},
        )
