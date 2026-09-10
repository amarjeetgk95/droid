"""Multi-timeframe trend forecast orchestrator for the Research Laboratory.

Assembles every available mechanics layer in the platform into a single
point-in-time directional forecast for horizons 1m / 5m / 15m / 30m / 1h:
  - Multi-timeframe candle features (1m/5m/15m/30m/1h/4h/1D)
  - Technical analysis suite per timeframe
  - Cross-timeframe alignment
  - Research indicators (RSI, VWAP, MACD, Momentum, OMPI) on the primary timeframe
  - Quantitative ML ensemble (5/15/30/60-minute horizons; 1m degrades gracefully)
  - Options/F&O context (PCR, walls, max pain, IV, theta)

Outputs a normalized ResearchPrediction ready for immutable recording.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import structlog
import uuid

from app.ml.predictor import MLPredictor
from app.research.enums import Direction, ForecastHorizon
from app.research.features import FeatureLayer
from app.research.models import IndicatorContext, IndicatorOutput, ResearchPrediction
from app.research.options_context import ResearchOptionsContext
from app.research.predictions import PredictionService
from app.research.registry import IndicatorRegistry
from app.services.market_service import MarketService

logger = structlog.get_logger(__name__)

# Timeframes fetched for a complete multi-timeframe picture
FORECAST_TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1D"]

# Indicator IDs to include in the ensemble
ENSEMBLE_INDICATOR_IDS = ["rsi", "vwap", "macd", "momentum", "ompi"]

# Weight each mechanics layer in final score
LAYER_WEIGHTS = {
    "mtf_alignment": 0.30,
    "indicators": 0.30,
    "ml": 0.25,
    "options": 0.10,
    "structure": 0.05,
}

# Supported forecast horizons. ml_minutes=None means the ML predictor has no
# calibrated artifact for that horizon (see app.ml.targets.SUPPORTED_HORIZONS)
# and the ML layer degrades gracefully to neutral.
HORIZON_CONFIG: Dict[str, Dict[str, Any]] = {
    "1m": {
        "timeframe": "1m",
        "minutes": 1,
        "ml_minutes": None,
        "forecast_horizon": ForecastHorizon.HORIZON_1M,
        "horizon_candles": 1,
        "indicator_id": "trend_forecast_1m",
    },
    "5m": {
        "timeframe": "5m",
        "minutes": 5,
        "ml_minutes": 5,
        "forecast_horizon": ForecastHorizon.HORIZON_5M,
        "horizon_candles": 1,
        "indicator_id": "trend_forecast_5m",
    },
    "15m": {
        "timeframe": "15m",
        "minutes": 15,
        "ml_minutes": 15,
        "forecast_horizon": ForecastHorizon.HORIZON_15M,
        "horizon_candles": 1,
        "indicator_id": "trend_forecast_15m",
    },
    "30m": {
        "timeframe": "30m",
        "minutes": 30,
        "ml_minutes": 30,
        "forecast_horizon": ForecastHorizon.HORIZON_30M,
        "horizon_candles": 1,
        "indicator_id": "trend_forecast_30m",
    },
    "1h": {
        "timeframe": "1h",
        "minutes": 60,
        "ml_minutes": 60,
        "forecast_horizon": ForecastHorizon.HORIZON_1H,
        "horizon_candles": 1,
        "indicator_id": "trend_forecast_1h",
    },
}

SUPPORTED_HORIZONS = tuple(HORIZON_CONFIG.keys())


def _candle_to_dict(c: Any) -> Dict[str, Any]:
    """Normalize a candle object to a plain dict."""
    if isinstance(c, dict):
        return c
    return {
        "open": float(getattr(c, "open", 0.0)),
        "high": float(getattr(c, "high", 0.0)),
        "low": float(getattr(c, "low", 0.0)),
        "close": float(getattr(c, "close", 0.0)),
        "volume": float(getattr(c, "volume", 0.0) or 0.0),
        "timestamp": (
            getattr(c, "timestamp", datetime.now(timezone.utc)).isoformat()
            if hasattr(getattr(c, "timestamp", None), "isoformat")
            else str(getattr(c, "timestamp", ""))
        ),
    }


class TrendForecaster:
    """Orchestrates a multi-timeframe trend forecast using all platform mechanics."""

    def __init__(self, market_service: Optional[MarketService] = None, ml_predictor: Optional[MLPredictor] = None):
        self.market_service = market_service or MarketService()
        self.ml_predictor = ml_predictor or MLPredictor()

    async def fetch_multi_timeframe_candles(
        self,
        instrument: str,
        timeframes: Optional[List[str]] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Fetch candles for all required timeframes in parallel-ish sequence."""
        timeframes = timeframes or FORECAST_TIMEFRAMES
        result: Dict[str, List[Dict[str, Any]]] = {}
        for tf in timeframes:
            try:
                raw = await self.market_service.get_candles(instrument, timeframe=tf)
                result[tf] = [_candle_to_dict(c) for c in raw] if raw else []
            except Exception as e:
                logger.warning("forecast_candle_fetch_failed", instrument=instrument, timeframe=tf, error=str(e))
                result[tf] = []
        return result

    async def run_research_indicators(
        self,
        instrument: str,
        candles: List[Dict[str, Any]],
        options_ctx: Dict[str, Any],
        timeframe: str = "1h",
        forecast_horizon: ForecastHorizon = ForecastHorizon.HORIZON_1H,
        horizon_candles: int = 1,
    ) -> List[IndicatorOutput]:
        """Run all registered research indicators on the primary candle series."""
        outputs: List[IndicatorOutput] = []
        if not candles:
            return outputs

        current_price = float(candles[-1]["close"])
        registry = IndicatorRegistry()

        for ind_id in ENSEMBLE_INDICATOR_IDS:
            indicator = registry.get(ind_id)
            if indicator is None:
                continue
            try:
                ctx = IndicatorContext(
                    instrument=instrument,
                    timeframe=timeframe,
                    timestamp=datetime.now(timezone.utc),
                    candles=candles,
                    current_price=current_price,
                    options_context=options_ctx,
                    parameters={"horizon": forecast_horizon.value},
                )
                output = await indicator.calculate(ctx)
                # Force the output horizon metadata for downstream consistency
                output.horizon = forecast_horizon
                output.horizon_candles = horizon_candles
                outputs.append(output)
            except Exception as e:
                logger.warning("forecast_indicator_failed", indicator_id=ind_id, error=str(e))
        return outputs

    async def get_ml_forecast(self, instrument: str, horizon_minutes: Optional[int]) -> Optional[Dict[str, Any]]:
        """Get the quantitative ML ensemble forecast for a horizon in minutes.

        Returns None when the horizon has no calibrated ML artifact (e.g. 1m)
        so the ensemble can degrade gracefully instead of failing.
        """
        if horizon_minutes is None:
            return None
        try:
            ml_response = await self.ml_predictor.predict_probabilities(
                symbol=instrument,
                horizon_minutes=horizon_minutes,
            )
            return {
                "bullish_pct": ml_response.bullish_pct,
                "neutral_pct": ml_response.neutral_pct,
                "bearish_pct": ml_response.bearish_pct,
                "predicted_bias": ml_response.predicted_bias,
                "trend_strength": ml_response.trend_strength,
                "confidence_score": ml_response.confidence_score,
                "model_source": ml_response.model_source,
                "calibrated": ml_response.calibrated,
            }
        except Exception as e:
            logger.warning("forecast_ml_failed", instrument=instrument, error=str(e))
            return None

    @staticmethod
    def _direction_to_score(direction: Direction) -> float:
        if direction == Direction.BULLISH:
            return 1.0
        if direction == Direction.BEARISH:
            return -1.0
        return 0.0

    def ensemble_forecast(
        self,
        mtf_features: Dict[str, Any],
        indicator_outputs: List[IndicatorOutput],
        ml_forecast: Optional[Dict[str, Any]],
        options_ctx: Dict[str, Any],
        current_price: float,
        horizon: str = "1h",
    ) -> Dict[str, Any]:
        """Combine all mechanics layers into a single directional forecast."""
        cfg = HORIZON_CONFIG.get(horizon, HORIZON_CONFIG["1h"])
        timeframe: str = cfg["timeframe"]
        forecast_horizon: ForecastHorizon = cfg["forecast_horizon"]
        horizon_candles: int = cfg["horizon_candles"]

        # Layer 1: MTF alignment score (-100 to +100)
        alignment = mtf_features.get("alignment", {})
        overall_bias = alignment.get("overall_bias", "NEUTRAL")
        alignment_score = float(alignment.get("alignment_score", 0.0))
        mtf_normalized = alignment_score if overall_bias == "BULLISH" else -alignment_score if overall_bias == "BEARISH" else 0.0

        # Layer 2: Research indicators average
        ind_score = 0.0
        ind_confidence = 0.0
        ind_count = 0
        for out in indicator_outputs:
            ind_score += out.score
            ind_confidence += out.confidence
            ind_count += 1
        if ind_count > 0:
            ind_score = ind_score / ind_count
            ind_confidence = ind_confidence / ind_count

        # Layer 3: ML ensemble
        ml_score = 0.0
        ml_confidence = 0.0
        if ml_forecast:
            bullish = ml_forecast.get("bullish_pct", 33.3)
            bearish = ml_forecast.get("bearish_pct", 33.3)
            neutral = ml_forecast.get("neutral_pct", 33.4)
            ml_score = ((bullish - bearish) / 100.0) * 100.0
            ml_confidence = max(bullish, bearish, neutral) / 100.0

        # Layer 4: Options context
        opt_score = 0.0
        pcr_oi = float(options_ctx.get("pcr_oi", 1.0) or 1.0)
        call_wall = options_ctx.get("call_wall")
        put_wall = options_ctx.get("put_wall")
        max_pain = options_ctx.get("max_pain")
        # PCR > 1 suggests put writing / bullish positioning
        opt_score += max(-30.0, min(30.0, (pcr_oi - 1.0) * 80.0))
        # Gravitational pull toward max pain
        if max_pain and max_pain > 0:
            pain_dist_pct = ((max_pain - current_price) / current_price) * 100.0
            opt_score += max(-20.0, min(20.0, pain_dist_pct * 15.0))
        # Wall proximity
        if call_wall and call_wall > current_price:
            call_dist_pct = ((call_wall - current_price) / current_price) * 100.0
            if call_dist_pct < 0.4:
                opt_score -= 20.0
        if put_wall and put_wall < current_price:
            put_dist_pct = ((current_price - put_wall) / current_price) * 100.0
            if put_dist_pct < 0.4:
                opt_score += 20.0
        opt_score = max(-100.0, min(100.0, opt_score))

        # Layer 5: Primary-timeframe structure
        per_tf = mtf_features.get("per_timeframe", {})
        feat_primary = (per_tf.get(timeframe, {}) or {}).get("features", {})
        if not feat_primary:
            # Fall back to any available timeframe's features
            for tf_payload in per_tf.values():
                if (tf_payload or {}).get("features"):
                    feat_primary = tf_payload["features"]
                    break
        quant_primary = (feat_primary or {}).get("quant", {})
        structure_score = 0.0
        st_dir = quant_primary.get("supertrend_dir", "NEUTRAL")
        if st_dir == "BULLISH":
            structure_score += 30.0
        elif st_dir == "BEARISH":
            structure_score -= 30.0
        rsi_primary = quant_primary.get("rsi_14", 50.0)
        try:
            rsi_primary = float(rsi_primary)
        except (TypeError, ValueError):
            rsi_primary = 50.0
        structure_score += max(-20.0, min(20.0, (rsi_primary - 50.0) * 0.8))
        structure_score = max(-100.0, min(100.0, structure_score))

        # Weighted ensemble
        final_score = (
            LAYER_WEIGHTS["mtf_alignment"] * mtf_normalized +
            LAYER_WEIGHTS["indicators"] * ind_score +
            LAYER_WEIGHTS["ml"] * ml_score +
            LAYER_WEIGHTS["options"] * opt_score +
            LAYER_WEIGHTS["structure"] * structure_score
        )
        final_score = round(max(-100.0, min(100.0, final_score)), 2)

        # Composite confidence
        alignment_confidence = alignment_score / 100.0
        confidence_inputs = [alignment_confidence, ind_confidence, ml_confidence]
        confidence = round(sum(confidence_inputs) / len(confidence_inputs), 3)

        # Direction & targets (ATR of the primary timeframe scales naturally)
        if final_score >= 20.0:
            direction = Direction.BULLISH
        elif final_score <= -20.0:
            direction = Direction.BEARISH
        else:
            direction = Direction.NEUTRAL

        atr_primary = quant_primary.get("atr_14", current_price * 0.005)
        try:
            atr_primary = float(atr_primary)
        except (TypeError, ValueError):
            atr_primary = current_price * 0.005
        if not atr_primary or atr_primary <= 0:
            atr_primary = current_price * 0.005
        if direction == Direction.BULLISH:
            target_price = round(current_price + (1.8 * atr_primary), 2)
            invalidation_price = round(current_price - (1.1 * atr_primary), 2)
        elif direction == Direction.BEARISH:
            target_price = round(current_price - (1.8 * atr_primary), 2)
            invalidation_price = round(current_price + (1.1 * atr_primary), 2)
        else:
            target_price = None
            invalidation_price = None

        return {
            "instrument": mtf_features.get("instrument"),
            "timeframe": timeframe,
            "forecast_horizon": forecast_horizon.value,
            "horizon_candles": horizon_candles,
            "current_price": round(current_price, 2),
            "direction": direction.value,
            "score": final_score,
            "confidence": confidence,
            "target_price": target_price,
            "invalidation_price": invalidation_price,
            "layer_scores": {
                "mtf_alignment": round(mtf_normalized, 2),
                "indicators": round(ind_score, 2),
                "ml": round(ml_score, 2),
                "options": round(opt_score, 2),
                "structure": round(structure_score, 2),
            },
            "ml_forecast": ml_forecast,
            "indicator_outputs": [out.model_dump() for out in indicator_outputs],
            "mtf_features": mtf_features,
            "options_context": options_ctx,
        }

    async def forecast(
        self,
        instrument: str,
        horizon: str = "1h",
        record: bool = True,
    ) -> Dict[str, Any]:
        """Generate a directional forecast for the given horizon and optionally persist it."""
        cfg = HORIZON_CONFIG.get(horizon)
        if cfg is None:
            raise ValueError(f"Unsupported forecast horizon '{horizon}'. Supported: {sorted(HORIZON_CONFIG)}")
        timeframe: str = cfg["timeframe"]
        forecast_horizon: ForecastHorizon = cfg["forecast_horizon"]
        horizon_candles: int = cfg["horizon_candles"]
        indicator_id: str = cfg["indicator_id"]

        logger.info("forecast_start", instrument=instrument, horizon=horizon)

        # 1. Fetch all timeframe candles
        mtf_candles = await self.fetch_multi_timeframe_candles(instrument)
        primary_candles = mtf_candles.get(timeframe, [])
        if not primary_candles:
            raise ValueError(f"Insufficient {timeframe} candle data for {instrument}")

        # 2. Options context
        options_ctx = await ResearchOptionsContext.get_context(instrument)

        # 3. Multi-timeframe features
        mtf_features = FeatureLayer.compute_multi_timeframe_features(
            instrument=instrument,
            timeframe_candles=mtf_candles,
            options_ctx=options_ctx,
        )

        # 4. Research indicators on the primary timeframe
        indicator_outputs = await self.run_research_indicators(
            instrument=instrument,
            candles=primary_candles,
            options_ctx=options_ctx,
            timeframe=timeframe,
            forecast_horizon=forecast_horizon,
            horizon_candles=horizon_candles,
        )

        # 5. ML forecast for this horizon (None for horizons without artifacts)
        ml_forecast = await self.get_ml_forecast(instrument, cfg["ml_minutes"])

        # 6. Ensemble
        current_price = float(primary_candles[-1]["close"])
        result = self.ensemble_forecast(
            mtf_features=mtf_features,
            indicator_outputs=indicator_outputs,
            ml_forecast=ml_forecast,
            options_ctx=options_ctx,
            current_price=current_price,
            horizon=horizon,
        )

        # 7. Record immutable prediction if requested
        if record:
            pred = ResearchPrediction(
                prediction_id=f"forecast_{horizon}_{uuid.uuid4().hex[:12]}",
                indicator_id=indicator_id,
                indicator_version="1.0.0",
                instrument=instrument,
                timeframe=timeframe,
                timestamp=datetime.now(timezone.utc),
                current_price=result["current_price"],
                direction=Direction(result["direction"]),
                score=result["score"],
                confidence=result["confidence"],
                component_values={
                    "layer_scores": result["layer_scores"],
                    "ml_forecast": ml_forecast,
                    "indicator_ids": [out.indicator_id for out in indicator_outputs],
                },
                forecast_horizon=forecast_horizon,
                horizon_candles=horizon_candles,
                target_price=result["target_price"],
                invalidation_price=result["invalidation_price"],
            )
            pred_id = await PredictionService.record_prediction(pred)
            result["prediction_id"] = pred_id

        logger.info(
            "forecast_complete",
            instrument=instrument,
            horizon=horizon,
            direction=result["direction"],
            score=result["score"],
            confidence=result["confidence"],
        )
        return result


class TrendForecast1H(TrendForecaster):
    """Backwards-compatible 1-hour forecaster (thin wrapper over TrendForecaster)."""

    async def get_ml_1h_forecast(self, instrument: str) -> Optional[Dict[str, Any]]:
        """Get the quantitative ML ensemble forecast for a 60-minute horizon."""
        return await self.get_ml_forecast(instrument, 60)

    async def forecast(
        self,
        instrument: str,
        record: bool = True,
    ) -> Dict[str, Any]:
        """Generate a 1-hour trend forecast and optionally persist it immutably."""
        return await super().forecast(instrument=instrument, horizon="1h", record=record)


# Module-level singletons for convenient import
trend_forecaster = TrendForecaster()
trend_forecast_1h = TrendForecast1H()
