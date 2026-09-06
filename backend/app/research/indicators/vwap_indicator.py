"""VWAP Standard Indicator implementation for the Research Laboratory (§46)."""

from typing import Any, Dict
from app.quant.indicators import calculate_atr
from app.research.enums import DataQualityStatus, Direction, ForecastHorizon, IndicatorCategory, IndicatorLifecycle
from app.research.features import calculate_intraday_vwap
from app.research.indicator_base import IndicatorBase
from app.research.models import IndicatorContext, IndicatorOutput


class VWAPIndicator(IndicatorBase):
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
    def default_parameters(self) -> Dict[str, Any]:
        return {"scale_factor": 50.0, "neutral_band_pct": 0.08}

    async def calculate(self, context: IndicatorContext) -> IndicatorOutput:
        scale_factor = float(context.parameters.get("scale_factor", 50.0))
        neutral_band = float(context.parameters.get("neutral_band_pct", 0.08))

        closes = [float(c["close"]) for c in context.candles]
        highs = [float(c["high"]) for c in context.candles]
        lows = [float(c["low"]) for c in context.candles]
        current_price = closes[-1] if closes else context.current_price

        vwap_val = calculate_intraday_vwap(context.candles) or current_price
        dist_pct = ((current_price - vwap_val) / vwap_val) * 100.0 if vwap_val > 0 else 0.0
        score = round(max(-100.0, min(100.0, dist_pct * scale_factor)), 2)

        if dist_pct >= neutral_band:
            direction = Direction.BULLISH
        elif dist_pct <= -neutral_band:
            direction = Direction.BEARISH
        else:
            direction = Direction.NEUTRAL

        confidence = round(min(1.0, abs(dist_pct) / (neutral_band * 5.0)), 3)

        atr = calculate_atr(highs, lows, closes, 14) if len(closes) >= 14 else (current_price * 0.005)
        target_price = round(current_price + (1.5 * atr) if direction == Direction.BULLISH else current_price - (1.5 * atr), 2)
        invalidation_price = round(vwap_val, 2)

        return IndicatorOutput(
            indicator_id=self.indicator_id,
            version=self.version,
            timestamp=context.timestamp,
            instrument=context.instrument,
            timeframe=context.timeframe,
            direction=direction,
            score=score,
            confidence=confidence,
            raw_value=vwap_val,
            normalized_value=score,
            component_values={
                "vwap": vwap_val,
                "current_price": current_price,
                "distance_pct": round(dist_pct, 4),
                "is_above_vwap": current_price > vwap_val,
            },
            regime_context=context.market_regime.value if context.market_regime else None,
            horizon=ForecastHorizon.HORIZON_15M,
            horizon_candles=5,
            target_price=target_price,
            invalidation_price=invalidation_price,
            data_quality=DataQualityStatus.LIVE,
            metadata={"source": "research.features.calculate_intraday_vwap"},
        )
