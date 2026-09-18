"""Multi-Period Momentum & ROC Indicator for the Research Laboratory (§46)."""

from typing import Any

from app.research.enums import (
    IndicatorCategory,
    IndicatorLifecycle,
)
from app.research.indicators.base import BuiltinIndicator, IndicatorMetadata
from app.research.models import IndicatorContext, IndicatorOutput


class MomentumIndicator(BuiltinIndicator):
    """Multi-Period Rate-of-Change (ROC) and Momentum Composite indicator."""

    METADATA = IndicatorMetadata(
        indicator_id="momentum",
        name="Multi-Period Momentum Composite",
        version="1.0.0",
        category=IndicatorCategory.STANDARD,
        lifecycle=IndicatorLifecycle.PRODUCTION,
    )

    @property
    def description(self) -> str:
        return "Composite momentum score based on weighted short, medium, and long Rate of Change (ROC)."

    @property
    def formula_summary(self) -> str:
        return "Score = 0.5 * ROC(5) + 0.3 * ROC(14) + 0.2 * ROC(20); Normalized to [-100, 100]"

    @property
    def default_parameters(self) -> dict[str, Any]:
        return {"p_fast": 5, "p_mid": 14, "p_slow": 20, "scale": 100.0}

    async def calculate(self, context: IndicatorContext) -> IndicatorOutput:
        p_fast = self._int_param(context, "p_fast", 5)
        p_mid = self._int_param(context, "p_mid", 14)
        p_slow = self._int_param(context, "p_slow", 20)
        scale = self._float_param(context, "scale", 100.0)

        closes, highs, lows, current_price = self._extract_series(context)

        roc_fast = self._rate_of_change(closes, p_fast)
        roc_mid = self._rate_of_change(closes, p_mid)
        roc_slow = self._rate_of_change(closes, p_slow)

        composite_roc = (0.5 * roc_fast) + (0.3 * roc_mid) + (0.2 * roc_slow)
        score = round(max(-100.0, min(100.0, composite_roc * scale)), 2)

        direction = self._resolve_direction(score, 15.0, -15.0)
        confidence = self._resolve_confidence(score, 75.0)

        atr = self._guarded_atr(highs, lows, closes, current_price)
        target_price, invalidation_price = self._trend_prices(current_price, atr, direction)

        return self._build_output(
            context,
            direction=direction,
            score=score,
            confidence=confidence,
            raw_value={"roc_fast": roc_fast, "roc_mid": roc_mid, "roc_slow": roc_slow},
            component_values={
                "roc_5": round(roc_fast, 3),
                "roc_14": round(roc_mid, 3),
                "roc_20": round(roc_slow, 3),
                "composite_roc": round(composite_roc, 3),
            },
            target_price=target_price,
            invalidation_price=invalidation_price,
            metadata={"source": "research.indicators.momentum_indicator"},
        )
