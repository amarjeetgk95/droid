import pytest
from app.services.regime_service import RegimeService


class TestRegimeService:
    @pytest.mark.asyncio
    async def test_get_technical_indicators(self):
        service = RegimeService()
        indicators = await service.get_technical_indicators("NIFTY")

        assert 0 <= indicators.rsi_14 <= 100
        assert indicators.adx_14 >= 0
        assert indicators.atr_14 > 0
        assert indicators.bollinger_upper > indicators.bollinger_middle > indicators.bollinger_lower
        assert indicators.supertrend_direction in ["BULLISH", "BEARISH"]

    @pytest.mark.asyncio
    async def test_get_key_levels(self):
        service = RegimeService()
        levels = await service.get_key_levels("NIFTY")

        assert levels.classic_pivots.pivot > 0
        assert levels.fibonacci_pivots.pivot > 0
        assert levels.camarilla_pivots.pivot > 0
        assert levels.poc > 0
        assert levels.vah >= levels.poc >= levels.val
        assert levels.nearest_resistance > 0
        assert levels.nearest_support > 0

    @pytest.mark.asyncio
    async def test_get_vix_regime(self):
        service = RegimeService()
        vix_info = await service.get_vix_regime()

        assert vix_info.vix_value > 0
        assert vix_info.regime_category in [
            "LOW_VOLATILITY", "NORMAL_VOLATILITY", "ELEVATED_VOLATILITY", "EXTREME_VOLATILITY"
        ]
        assert len(vix_info.recommended_option_strategy) > 0

    @pytest.mark.asyncio
    async def test_classify_market_regime(self):
        service = RegimeService()
        overview = await service.classify_market_regime("NIFTY")

        assert overview.symbol == "NIFTY"
        assert overview.spot_price > 0
        assert overview.confidence_score > 0
        assert overview.regime_state in [
            "TRENDING_BULLISH", "TRENDING_BEARISH", "RANGEBOUND_LOW_VOL",
            "RANGEBOUND_HIGH_VOL", "VOLATILE_EXPANSION", "COMPRESSION_SQUEEZE"
        ]
        assert len(overview.summary_headline) > 0
