import pytest
from app.ml.predictor import ml_predictor
from app.ml.feature_extractor import extract_ml_feature_vector
from app.models.regime import TechnicalIndicators


from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from app.models.market import NormalizedQuote, DataStatus


class TestMLPredictor:
    @pytest.mark.asyncio
    async def test_predict_probabilities_nifty(self):
        mock_quote = NormalizedQuote(
            symbol="NSE:NIFTY50-INDEX",
            display_name="NIFTY 50",
            timestamp=datetime.now(timezone.utc),
            ltp=25000.0,
            open=24900.0,
            high=25050.0,
            low=24850.0,
            previous_close=24900.0,
            change=100.0,
            change_percent=0.4,
            volume=1000000,
            status=DataStatus.LIVE,
        )
        with patch.object(ml_predictor.market_service, "get_quote", new=AsyncMock(return_value=mock_quote)):
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
        mock_quote = NormalizedQuote(
            symbol="BSE:SENSEX-INDEX",
            display_name="SENSEX",
            timestamp=datetime.now(timezone.utc),
            ltp=75000.0,
            open=74800.0,
            high=75200.0,
            low=74700.0,
            previous_close=74800.0,
            change=200.0,
            change_percent=0.27,
            volume=500000,
            status=DataStatus.LIVE,
        )
        with patch.object(ml_predictor.market_service, "get_quote", new=AsyncMock(return_value=mock_quote)):
            pred = await ml_predictor.predict_probabilities("SENSEX")
            assert pred.symbol == "SENSEX"
            assert pred.spot_price > 50000
            prob_sum = pred.bullish_pct + pred.neutral_pct + pred.bearish_pct
            assert 99.0 <= prob_sum <= 101.0

    @pytest.mark.asyncio
    async def test_predict_probabilities_missing_quote(self):
        with patch.object(ml_predictor.market_service, "get_quote", new=AsyncMock(return_value=None)):
            with pytest.raises(ValueError, match="Market quote unavailable"):
                await ml_predictor.predict_probabilities("NIFTY")

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
