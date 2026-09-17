"""VWAP Standard Indicator implementation for the Research Laboratory (§46)."""

from typing import Any

from app.research.enums import (
    IndicatorCategory,
    IndicatorLifecycle,
)
from app.research.features import calculate_intraday_vwap
from app.research.indicators.base import BuiltinIndicator
from app.research.models import IndicatorContext, IndicatorOutput


class VWAPIndicator(BuiltinIndicator):
    """Volume Weighted Average Price (VWAP) indicator.
    
    Measures price deviation and momentum relative to the volume-weighted benchmark.
    Score = clamped((price - vwap) / vwap * 100 * scale_factor, -100, 100).
    """

    @property
    def indicator_id(self) -> str:
        return "vwap"

    @property
    def name(self) -> str:
        return "Volume Weighted Average Price (VWAP)"

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
        return "Intraday volume-weighted average price benchmark with distance-based normalization."

    @property
    def formula_summary(self) -> str:
        return "Distance% = (Price - VWAP) / VWAP * 100; Scaled into [-100, 100]"

    @property
    def default_parameters(self) -> dict[str, Any]:
        return {"scale_factor": 50.0, "neutral_band_pct": 0.08}

    async def calculate(self, context: IndicatorContext) -> IndicatorOutput:
        scale_factor = self._float_param(context, "scale_factor", 50.0)
        neutral_band = self._float_param(context, "neutral_band_pct", 0.08)

        closes, highs, lows, current_price = self._extract_series(context)

        vwap_val = calculate_intraday_vwap(context.candles) or current_price
        dist_pct = ((current_price - vwap_val) / vwap_val) * 100.0 if vwap_val > 0 else 0.0
        score = round(max(-100.0, min(100.0, dist_pct * scale_factor)), 2)

        direction = self._resolve_direction(dist_pct, neutral_band, -neutral_band)
        confidence = self._resolve_confidence(dist_pct, neutral_band * 5.0)

        atr = self._guarded_atr(highs, lows, closes, current_price)
        target_price, _ = self._trend_prices(current_price, atr, direction)
        invalidation_price = round(vwap_val, 2)

        return self._build_output(
            context,
            direction=direction,
            score=score,
            confidence=confidence,
            raw_value=vwap_val,
            component_values={
                "vwap": vwap_val,
                "current_price": current_price,
                "distance_pct": round(dist_pct, 4),
                "is_above_vwap": current_price > vwap_val,
            },
            target_price=target_price,
            invalidation_price=invalidation_price,
            metadata={"source": "research.features.calculate_intraday_vwap"},
        )
