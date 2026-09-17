"""Shared scaffolding for the built-in research indicators (§46).

The concrete indicators in this package repeat the same skeleton: parameter
coercion, OHLC extraction with None/length guards, ATR fallback, threshold to
Direction classification, confidence scaling, bracket price construction and
IndicatorOutput assembly. :class:`BuiltinIndicator` owns that skeleton so each
indicator module only implements its own math.

Semantics are intentionally preserved exactly as written in the individual
indicators (same guards, same rounding, same NaN propagation) — this module
deduplicates the shape, it does not "fix" any behavior.
"""

from typing import Any

from app.quant.indicators import calculate_atr
from app.research.enums import DataQualityStatus, Direction, ForecastHorizon
from app.research.indicator_base import IndicatorBase
from app.research.models import IndicatorContext, IndicatorOutput


class BuiltinIndicator(IndicatorBase):
    """Base class owning the shared built-in indicator skeleton.

    Subclasses keep their own metadata and math. Provided helpers:
      * ``_int_param`` / ``_float_param`` — parameter coercion guards
      * ``_extract_series`` — closes/highs/lows + last-close/current_price guard
      * ``_extract_opens`` / ``_extract_volumes`` — OHLCV guards
      * ``_guarded_atr`` — ATR with the short-series fallback
      * ``_last`` / ``_rate_of_change`` — rolling-window primitives
      * ``_resolve_direction`` — threshold classification
      * ``_resolve_confidence`` — confidence scaling
      * ``_bracket_prices`` / ``_trend_prices`` — target/invalidation brackets
      * ``_build_output`` — common IndicatorOutput field assembly
    """

    @staticmethod
    def _int_param(context: IndicatorContext, key: str, default: Any) -> int:
        return int(context.parameters.get(key, default))

    @staticmethod
    def _float_param(context: IndicatorContext, key: str, default: Any) -> float:
        return float(context.parameters.get(key, default))

    @staticmethod
    def _extract_series(
        context: IndicatorContext,
    ) -> tuple[list[float], list[float], list[float], float]:
        candles = context.candles
        closes = [float(c["close"]) for c in candles]
        highs = [float(c["high"]) for c in candles]
        lows = [float(c["low"]) for c in candles]
        current_price = closes[-1] if closes else context.current_price
        return closes, highs, lows, current_price

    @staticmethod
    def _extract_opens(candles: list[dict[str, Any]]) -> list[float]:
        return [float(c["open"]) for c in candles]

    @staticmethod
    def _extract_volumes(candles: list[dict[str, Any]]) -> list[float]:
        return [float(c.get("volume", 0.0) or 0.0) for c in candles]

    @staticmethod
    def _guarded_atr(
        highs: list[float],
        lows: list[float],
        closes: list[float],
        current_price: float,
        period: int = 14,
    ) -> float:
        return (
            calculate_atr(highs, lows, closes, period)
            if len(closes) >= period
            else (current_price * 0.005)
        )

    @staticmethod
    def _last(values: list[Any], count: int) -> list[Any]:
        return values[-count:] if count > 0 else []

    @staticmethod
    def _rate_of_change(closes: list[float], period: int) -> float:
        if len(closes) > period and closes[-(period + 1)] > 0:
            return ((closes[-1] - closes[-(period + 1)]) / closes[-(period + 1)]) * 100.0
        return 0.0

    @staticmethod
    def _resolve_direction(
        value: float,
        bull_threshold: float,
        bear_threshold: float,
        *,
        strict: bool = False,
    ) -> Direction:
        if strict:
            if value > bull_threshold:
                return Direction.BULLISH
            if value < bear_threshold:
                return Direction.BEARISH
            return Direction.NEUTRAL
        if value >= bull_threshold:
            return Direction.BULLISH
        if value <= bear_threshold:
            return Direction.BEARISH
        return Direction.NEUTRAL

    @staticmethod
    def _resolve_confidence(value: float, divisor: float) -> float:
        return round(min(1.0, abs(value) / divisor), 3)

    @staticmethod
    def _bracket_prices(
        current_price: float,
        atr: float,
        direction: Direction,
        target_multiplier: float = 1.5,
        stop_multiplier: float = 1.0,
    ) -> tuple[float | None, float | None]:
        if direction == Direction.BULLISH:
            return (
                round(current_price + (target_multiplier * atr), 2),
                round(current_price - (stop_multiplier * atr), 2),
            )
        if direction == Direction.BEARISH:
            return (
                round(current_price - (target_multiplier * atr), 2),
                round(current_price + (stop_multiplier * atr), 2),
            )
        return None, None

    @staticmethod
    def _trend_prices(
        current_price: float,
        atr: float,
        direction: Direction,
        target_multiplier: float = 1.5,
        stop_multiplier: float = 1.0,
    ) -> tuple[float, float]:
        """Target/invalidation with the bullish-else-bearish fallthrough.

        Trend indicators treat every non-BULLISH direction (including NEUTRAL)
        as the bearish branch; that quirk is deliberate and preserved.
        """
        target_price = round(
            current_price + (target_multiplier * atr)
            if direction == Direction.BULLISH
            else current_price - (target_multiplier * atr),
            2,
        )
        invalidation_price = round(
            current_price - (stop_multiplier * atr)
            if direction == Direction.BULLISH
            else current_price + (stop_multiplier * atr),
            2,
        )
        return target_price, invalidation_price

    def _build_output(
        self,
        context: IndicatorContext,
        *,
        direction: Direction,
        score: float,
        confidence: float,
        raw_value: Any = None,
        component_values: dict[str, Any] | None = None,
        target_price: float | None = None,
        invalidation_price: float | None = None,
        data_quality: DataQualityStatus = DataQualityStatus.LIVE,
        metadata: dict[str, Any] | None = None,
    ) -> IndicatorOutput:
        return IndicatorOutput(
            indicator_id=self.indicator_id,
            version=self.version,
            timestamp=context.timestamp,
            instrument=context.instrument,
            timeframe=context.timeframe,
            direction=direction,
            score=score,
            confidence=confidence,
            raw_value=raw_value,
            normalized_value=score,
            component_values=component_values if component_values is not None else {},
            regime_context=context.market_regime.value if context.market_regime else None,
            horizon=ForecastHorizon.HORIZON_15M,
            horizon_candles=5,
            target_price=target_price,
            invalidation_price=invalidation_price,
            data_quality=data_quality,
            metadata=metadata if metadata is not None else {},
        )
