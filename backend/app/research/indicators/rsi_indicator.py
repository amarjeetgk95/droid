"""RSI Standard Indicator implementation for the Research Laboratory (§46)."""

from datetime import datetime, timezone
from typing import Any, Dict
from app.quant.indicators import calculate_atr, calculate_rsi
from app.research.enums import DataQualityStatus, Direction, ForecastHorizon, IndicatorCategory, IndicatorLifecycle
from app.research.indicator_base import IndicatorBase
from app.research.models import IndicatorContext, IndicatorOutput


class RSIIndicator(IndicatorBase):
    """Relative Strength Index standard indicator.
    
    Normalizes Wilder's smoothed RSI (0-100) to standard research scale (-100 to +100).
    Score = (RSI - 50) * 2.
    """

    @property
    def indicator_id(self) -> str:
        return "rsi"

    @property
    def name(self) -> str:
        return "Relative Strength Index (RSI)"

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
        return "14-period Relative Strength Index with Wilder's smoothing, centered at 0 on [-100, +100]."

    @property
    def formula_summary(self) -> str:
        return "Score = (RSI(14) - 50) * 2; Bullish > 10, Bearish < -10"

    @property
    def default_parameters(self) -> Dict[str, Any]:
        return {"period": 14, "overbought": 70, "oversold": 30, "bull_threshold": 10.0, "bear_threshold": -10.0}

    async def calculate(self, context: IndicatorContext) -> IndicatorOutput:
        period = int(context.parameters.get("period", 14))
        bull_th = float(context.parameters.get("bull_threshold", 10.0))
        bear_th = float(context.parameters.get("bear_threshold", -10.0))

        closes = [float(c["close"]) for c in context.candles]
        highs = [float(c["high"]) for c in context.candles]
        lows = [float(c["low"]) for c in context.candles]
        current_price = closes[-1] if closes else context.current_price

        raw_rsi = calculate_rsi(closes, period=period)
        score = round(max(-100.0, min(100.0, (raw_rsi - 50.0) * 2.0)), 2)

        if score >= bull_th:
            direction = Direction.BULLISH
        elif score <= bear_th:
            direction = Direction.BEARISH
        else:
            direction = Direction.NEUTRAL

        confidence = round(min(1.0, abs(score) / 80.0), 3)

        atr = calculate_atr(highs, lows, closes, 14) if len(closes) >= 14 else (current_price * 0.005)
        if direction == Direction.BULLISH:
            target_price = round(current_price + (1.5 * atr), 2)
            invalidation_price = round(current_price - (1.0 * atr), 2)
        elif direction == Direction.BEARISH:
            target_price = round(current_price - (1.5 * atr), 2)
            invalidation_price = round(current_price + (1.0 * atr), 2)
        else:
            target_price = None
            invalidation_price = None

        return IndicatorOutput(
            indicator_id=self.indicator_id,
            version=self.version,
            timestamp=context.timestamp,
            instrument=context.instrument,
            timeframe=context.timeframe,
            direction=direction,
            score=score,
            confidence=confidence,
            raw_value=raw_rsi,
            normalized_value=score,
            component_values={
                "rsi": raw_rsi,
                "period": period,
                "overbought": context.parameters.get("overbought", 70),
                "oversold": context.parameters.get("oversold", 30),
            },
            regime_context=context.market_regime.value if context.market_regime else None,
            horizon=ForecastHorizon.HORIZON_15M,
            horizon_candles=5,
            target_price=target_price,
            invalidation_price=invalidation_price,
            data_quality=DataQualityStatus.LIVE,
            metadata={"source": "quant.indicators.calculate_rsi"},
        )
