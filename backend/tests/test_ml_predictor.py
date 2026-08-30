import pytest
from app.ml.predictor import ml_predictor
from app.ml.feature_extractor import extract_ml_feature_vector
from app.models.regime import TechnicalIndicators


class TestMLPredictor:
    @pytest.mark.asyncio
    async def test_predict_probabilities_nifty(self):
        pred = await ml_predictor.predict_probabilities("NIFTY")
        assert pred.symbol == "NIFTY"
        assert pred.spot_price > 0
        # Probabilities must sum to ~100%
        prob_sum = pred.bullish_pct + pred.neutral_pct + pred.bearish_pct
        assert 99.0 <= prob_sum <= 101.0
        assert 0.0 <= pred.trend_strength <= 100.0
        assert 0.0 <= pred.confidence_score <= 100.0
        assert pred.predicted_bias in ["BULLISH", "NEUTRAL", "BEARISH"]
        assert len(pred.top_features) > 0

    @pytest.mark.asyncio
    async def test_predict_probabilities_sensex(self):
        pred = await ml_predictor.predict_probabilities("SENSEX")
        assert pred.symbol == "SENSEX"
        assert pred.spot_price > 80000
        prob_sum = pred.bullish_pct + pred.neutral_pct + pred.bearish_pct
        assert 99.0 <= prob_sum <= 101.0

    def test_feature_extractor_bounds(self):
        ind = TechnicalIndicators(
            rsi_14=65.0,
            adx_14=28.5,
            plus_di=24.0,
            minus_di=14.0,
            atr_14=120.0,
            supertrend_value=24800.0,
            supertrend_direction="BULLISH",
            bollinger_upper=25200.0,
            bollinger_middle=25000.0,
            bollinger_lower=24800.0,
            bollinger_bandwidth=1.6,
            bollinger_pct_b=0.75,
            ema_20=24950.0,
            ema_50=24800.0,
            sma_200=24200.0,
        )
        features = extract_ml_feature_vector(
            spot_price=25050.0,
            indicators=ind,
            key_levels=None,
            options_analytics=None,
            max_pain=None,
            term_structure=None,
        )
        assert -1.0 <= features.rsi_norm <= 1.0
        assert 0.0 <= features.adx_strength <= 1.0
        assert features.supertrend_signal == 1.0
