"""Multi-Period Momentum & ROC Indicator for the Research Laboratory (§46)."""

from typing import Any, Dict
from app.quant.indicators import calculate_atr
from app.research.enums import DataQualityStatus, Direction, ForecastHorizon, IndicatorCategory, IndicatorLifecycle
from app.research.indicator_base import IndicatorBase
from app.research.models import IndicatorContext, IndicatorOutput


class MomentumIndicator(IndicatorBase):
    """Multi-Period Rate-of-Change (ROC) and Momentum Composite indicator."""

    @property
    def indicator_id(self) -> str:
        return "momentum"

    @property
    def name(self) -> str:
        return "Multi-Period Momentum Composite"

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
        return "Composite momentum score based on weighted short, medium, and long Rate of Change (ROC)."

    @property
    def formula_summary(self) -> str:
        return "Score = 0.5 * ROC(5) + 0.3 * ROC(14) + 0.2 * ROC(20); Normalized to [-100, 100]"

    @property
    def default_parameters(self) -> Dict[str, Any]:
        return {"p_fast": 5, "p_mid": 14, "p_slow": 20, "scale": 100.0}

    async def calculate(self, context: IndicatorContext) -> IndicatorOutput:
        p_fast = int(context.parameters.get("p_fast", 5))
        p_mid = int(context.parameters.get("p_mid", 14))
        p_slow = int(context.parameters.get("p_slow", 20))
        scale = float(context.parameters.get("scale", 100.0))

        closes = [float(c["close"]) for c in context.candles]
        highs = [float(c["high"]) for c in context.candles]
        lows = [float(c["low"]) for c in context.candles]
        current_price = closes[-1] if closes else context.current_price

        def get_roc(period: int) -> float:
            if len(closes) > period and closes[-(period + 1)] > 0:
                return ((closes[-1] - closes[-(period + 1)]) / closes[-(period + 1)]) * 100.0
            return 0.0

        roc_fast = get_roc(p_fast)
        roc_mid = get_roc(p_mid)
        roc_slow = get_roc(p_slow)

        composite_roc = (0.5 * roc_fast) + (0.3 * roc_mid) + (0.2 * roc_slow)
        score = round(max(-100.0, min(100.0, composite_roc * scale)), 2)

        if score >= 15.0:
            direction = Direction.BULLISH
        elif score <= -15.0:
            direction = Direction.BEARISH
        else:
            direction = Direction.NEUTRAL

        confidence = round(min(1.0, abs(score) / 75.0), 3)
        atr = calculate_atr(highs, lows, closes, 14) if len(closes) >= 14 else (current_price * 0.005)
        target_price = round(current_price + (1.5 * atr) if direction == Direction.BULLISH else current_price - (1.5 * atr), 2)
        invalidation_price = round(current_price - (1.0 * atr) if direction == Direction.BULLISH else current_price + (1.0 * atr), 2)

        return IndicatorOutput(
            indicator_id=self.indicator_id,
            version=self.version,
            timestamp=context.timestamp,
            instrument=context.instrument,
            timeframe=context.timeframe,
            direction=direction,
            score=score,
            confidence=confidence,
            raw_value={"roc_fast": roc_fast, "roc_mid": roc_mid, "roc_slow": roc_slow},
            normalized_value=score,
            component_values={
                "roc_5": round(roc_fast, 3),
                "roc_14": round(roc_mid, 3),
                "roc_20": round(roc_slow, 3),
                "composite_roc": round(composite_roc, 3),
            },
            regime_context=context.market_regime.value if context.market_regime else None,
            horizon=ForecastHorizon.HORIZON_15M,
            horizon_candles=5,
            target_price=target_price,
            invalidation_price=invalidation_price,
            data_quality=DataQualityStatus.LIVE,
            metadata={"source": "research.indicators.momentum_indicator"},
        )
