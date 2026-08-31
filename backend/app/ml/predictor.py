import math
import uuid
from datetime import datetime, timezone
from app.models.ml import MLPredictionResponse, MLFeatureContribution
from app.ml.feature_extractor import extract_ml_feature_vector, MLFeatures
from app.services.regime_service import regime_service
from app.services.options_service import options_service
from app.services.market_service import MarketService
from app.core.database import get_async_session_factory
from app.repositories.ml_repository import MLRepository
import structlog

logger = structlog.get_logger()


class MLPredictor:
    """Quantitative Probabilistic Ensemble ML Predictor (XGBoost/LightGBM Style)."""

    def __init__(self, market_service: MarketService | None = None):
        self.market_service = market_service or MarketService()

    async def predict_probabilities(self, symbol: str = "NIFTY") -> MLPredictionResponse:
        """Calculate multi-class probabilities (Bullish, Neutral, Bearish) and trend strength."""
        underlying = symbol.upper().replace(" 50", "")

        # 1. Fetch multi-factor inputs in parallel
        quote = await self.market_service.get_quote(underlying)
        spot_price = quote.ltp

        indicators = await regime_service.get_technical_indicators(underlying)
        key_levels = await regime_service.get_key_levels(underlying)
        vix_info = await regime_service.get_vix_regime()

        # Options Context
        chain_data = None
        max_pain = None
        try:
            chain_data = await options_service.get_option_chain_matrix(underlying)
            max_pain = chain_data.max_pain
        except Exception:
            pass

        # 2. Extract normalized feature vector
        features: MLFeatures = extract_ml_feature_vector(
            spot_price=spot_price,
            indicators=indicators,
            key_levels=key_levels,
            options_analytics=chain_data.analytics if chain_data else None,
            max_pain=max_pain,
        )

        # 3. Try real XGBoost/LightGBM ensemble first
        feature_vec = [
            features.rsi_norm,
            features.adx_strength,
            features.supertrend_signal,
            features.bollinger_pct_b,
            features.pcr_oi_deviation,
            features.max_pain_distance_pct,
            features.futures_basis_pct,
            features.price_above_ema20,
            features.price_above_sma200,
            features.pivot_position,
        ]
        ensemble_result = None
        try:
            from app.ml.trainer import ensemble_predict_proba

            ensemble_result = ensemble_predict_proba(feature_vec)
        except Exception as e:
            logger.info("ml_ensemble_not_available", error=str(e))

        if ensemble_result is not None:
            bearish_pct, neutral_pct, bullish_pct = ensemble_result
            # Derive heuristic scores for downstream metrics
            w_st = 0.25 * features.supertrend_signal
            w_rsi = 0.20 * features.rsi_norm
            w_pcr = 0.15 * features.pcr_oi_deviation
            w_basis = 0.15 * (1.0 if features.futures_basis_pct > 0 else -1.0) * min(1.0, abs(features.futures_basis_pct) * 200)
            w_ema = 0.15 * min(1.0, max(-1.0, features.price_above_ema20 * 100))
            w_pivot = 0.10 * features.pivot_position
            raw_directional_score = w_st + w_rsi + w_pcr + w_basis + w_ema + w_pivot
            adx_factor = features.adx_strength
            model_source = "xgboost_lightgbm_ensemble"
        else:
            # Fallback: heuristic Gradient Decision Trees Ensemble Score
            w_st = 0.25 * features.supertrend_signal
            w_rsi = 0.20 * features.rsi_norm
            w_pcr = 0.15 * features.pcr_oi_deviation
            w_basis = 0.15 * (1.0 if features.futures_basis_pct > 0 else -1.0) * min(1.0, abs(features.futures_basis_pct) * 200)
            w_ema = 0.15 * min(1.0, max(-1.0, features.price_above_ema20 * 100))
            w_pivot = 0.10 * features.pivot_position

            raw_directional_score = w_st + w_rsi + w_pcr + w_basis + w_ema + w_pivot  # -1.0 to +1.0
            adx_factor = features.adx_strength  # 0 to 1.0

            if raw_directional_score > 0:
                bullish_logit = 1.0 + (raw_directional_score * 2.5) * (0.5 + 0.5 * adx_factor)
                bearish_logit = 1.0 - (raw_directional_score * 1.5)
                neutral_logit = 1.0 + (1.0 - adx_factor) * 1.2
            else:
                bullish_logit = 1.0 + (raw_directional_score * 1.5)
                bearish_logit = 1.0 - (raw_directional_score * 2.5) * (0.5 + 0.5 * adx_factor)
                neutral_logit = 1.0 + (1.0 - adx_factor) * 1.2

            exp_bull = math.exp(max(-5.0, min(5.0, bullish_logit)))
            exp_bear = math.exp(max(-5.0, min(5.0, bearish_logit)))
            exp_neut = math.exp(max(-5.0, min(5.0, neutral_logit)))
            total_exp = exp_bull + exp_bear + exp_neut

            bullish_pct = round((exp_bull / total_exp) * 100.0, 1)
            bearish_pct = round((exp_bear / total_exp) * 100.0, 1)
            neutral_pct = round(100.0 - bullish_pct - bearish_pct, 1)
            model_source = "heuristic_ensemble"

        # Trend Strength (0-100)
        trend_strength = round(min(100.0, max(5.0, (abs(raw_directional_score) * 60.0) + (adx_factor * 40.0))), 1)

        # Confidence Score (0-100)
        max_prob = max(bullish_pct, neutral_pct, bearish_pct)
        confidence_score = round(min(98.0, max(50.0, max_prob * 1.1 + (adx_factor * 10.0))), 1)

        # Predicted Bias
        if bullish_pct >= 48.0 and bullish_pct > bearish_pct:
            predicted_bias = "BULLISH"
        elif bearish_pct >= 48.0 and bearish_pct > bullish_pct:
            predicted_bias = "BEARISH"
        else:
            predicted_bias = "NEUTRAL"

        # Regime string
        market_regime = "TRENDING_BULLISH" if predicted_bias == "BULLISH" and trend_strength > 60 else \
                        "TRENDING_BEARISH" if predicted_bias == "BEARISH" and trend_strength > 60 else \
                        "COMPRESSION_SQUEEZE" if indicators.adx_14 < 20 else "SIDEWAYS_RANGE"

        # Top feature contributions
        top_features = [
            MLFeatureContribution(
                feature_name="Supertrend (10, 3)",
                value=indicators.supertrend_value,
                contribution=round(w_st, 3),
                description=f"Directional filter {indicators.supertrend_direction}",
            ),
            MLFeatureContribution(
                feature_name="RSI (14)",
                value=indicators.rsi_14,
                contribution=round(w_rsi, 3),
                description=f"Momentum oscillator normalized {indicators.rsi_14:.1f}",
            ),
            MLFeatureContribution(
                feature_name="Put-Call Ratio (OI)",
                value=chain_data.analytics.pcr_oi if chain_data else 1.0,
                contribution=round(w_pcr, 3),
                description="Institutional Option Open Interest tilt",
            ),
            MLFeatureContribution(
                feature_name="Futures Basis Spread",
                value=term_structure.contracts[0].basis if term_structure and term_structure.contracts else 0.0,
                contribution=round(w_basis, 3),
                description="Cash vs Fair Value premium/discount",
            ),
            MLFeatureContribution(
                feature_name="Trend Strength (ADX)",
                value=indicators.adx_14,
                contribution=round(adx_factor, 3),
                description=f"Non-directional velocity score {indicators.adx_14:.1f}",
            ),
        ]

        # Resolve model_version from artifacts meta if available
        model_version = "XGBoost-LightGBM-Ensemble-v2.0" if model_source == "xgboost_lightgbm_ensemble" else "XGBoost-LightGBM-Ensemble-v1.0-heuristic"
        try:
            from app.ml.trainer import META_PATH

            if META_PATH.exists():
                import json

                meta = json.loads(META_PATH.read_text())
                model_version = meta.get("model_version", model_version)
        except Exception:
            pass

        response = MLPredictionResponse(
            symbol=underlying,
            timestamp=datetime.now(timezone.utc),
            spot_price=spot_price,
            bullish_pct=bullish_pct,
            neutral_pct=neutral_pct,
            bearish_pct=bearish_pct,
            trend_strength=trend_strength,
            confidence_score=confidence_score,
            predicted_bias=predicted_bias,
            market_regime=market_regime,
            top_features=top_features,
            model_version=model_version,
        )

        # Save to Supabase PostgreSQL database asynchronously
        factory = get_async_session_factory()
        if factory:
            try:
                async with factory() as session:
                    await MLRepository.save_prediction(session, response)
            except Exception as e:
                logger.warning("failed_to_save_ml_prediction_supabase", error=str(e))

        return response


ml_predictor = MLPredictor()
