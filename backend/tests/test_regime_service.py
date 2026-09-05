from datetime import datetime, timezone
from unittest.mock import AsyncMock
import pytest
from app.services.regime_service import RegimeService
from app.models.market import NormalizedCandle, NormalizedQuote, DataStatus


def _create_sample_candles(base: float = 24000.0, count: int = 30) -> list[NormalizedCandle]:
    candles = []
    now = datetime.now(timezone.utc)
    for i in range(count):
        p = base + (i * 10.0)
        candles.append(
            NormalizedCandle(
                timestamp=now,
                open=p - 5.0,
                high=p + 15.0,
                low=p - 10.0,
                close=p,
                volume=10000.0,
            )
        )
    return candles


class TestRegimeService:
    @pytest.mark.asyncio
    async def test_get_technical_indicators(self):
        service = RegimeService()
        service.market_service.get_candles = AsyncMock(return_value=_create_sample_candles(24000.0, 30))

        indicators = await service.get_technical_indicators("NIFTY")

        assert 0 <= indicators.rsi_14 <= 100
        assert indicators.adx_14 >= 0
        assert indicators.atr_14 > 0
        assert indicators.bollinger_upper > indicators.bollinger_middle > indicators.bollinger_lower
        assert indicators.supertrend_direction in ["BULLISH", "BEARISH"]

    @pytest.mark.asyncio
    async def test_get_key_levels(self):
        service = RegimeService()
        service.market_service.get_quote = AsyncMock(return_value=NormalizedQuote(
            symbol="NIFTY", display_name="NIFTY", timestamp=datetime.now(timezone.utc),
            ltp=24000.0, open=23900.0, high=24100.0, low=23850.0, previous_close=23950.0,
            change=50.0, change_percent=0.2, volume=1000000, status=DataStatus.LIVE, provider="test",
        ))
        service.market_service.get_candles = AsyncMock(return_value=_create_sample_candles(24000.0, 30))

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
        service.market_service.get_quote = AsyncMock(return_value=NormalizedQuote(
            symbol="INDIA VIX", display_name="INDIA VIX", timestamp=datetime.now(timezone.utc),
            ltp=14.5, open=14.0, high=15.0, low=13.8, previous_close=14.2,
            change=0.3, change_percent=2.1, volume=0, status=DataStatus.LIVE, provider="test",
        ))

        vix_info = await service.get_vix_regime()

        assert vix_info.vix_value == 14.5
        assert vix_info.regime_category in [
            "LOW_VOLATILITY", "NORMAL_VOLATILITY", "ELEVATED_VOLATILITY", "EXTREME_VOLATILITY"
        ]
        assert len(vix_info.recommended_option_strategy) > 0

    @pytest.mark.asyncio
    async def test_classify_market_regime(self):
        service = RegimeService()
        service.market_service.get_quote = AsyncMock(return_value=NormalizedQuote(
            symbol="NIFTY", display_name="NIFTY", timestamp=datetime.now(timezone.utc),
            ltp=24000.0, open=23900.0, high=24100.0, low=23850.0, previous_close=23950.0,
            change=50.0, change_percent=0.2, volume=1000000, status=DataStatus.LIVE, provider="test",
        ))
        service.market_service.get_candles = AsyncMock(return_value=_create_sample_candles(24000.0, 30))

        overview = await service.classify_market_regime("NIFTY")

        assert overview.symbol == "NIFTY"
        assert overview.spot_price > 0
        assert overview.confidence_score > 0
        assert overview.regime_state in [
            "TRENDING_BULLISH", "TRENDING_BEARISH", "RANGEBOUND_LOW_VOL",
            "RANGEBOUND_HIGH_VOL", "VOLATILE_EXPANSION", "COMPRESSION_SQUEEZE"
        ]
        assert len(overview.summary_headline) > 0

    @pytest.mark.asyncio
    async def test_offline_empty_behavior(self):
        service = RegimeService()
        service.market_service.get_candles = AsyncMock(return_value=[])
        service.market_service.get_quote = AsyncMock(return_value=NormalizedQuote(
            symbol="NIFTY", display_name="NIFTY", timestamp=datetime.now(timezone.utc),
            ltp=0.0, open=0.0, high=0.0, low=0.0, previous_close=0.0,
            change=0.0, change_percent=0.0, volume=0, status=DataStatus.OFFLINE, provider="test",
        ))

        indicators = await service.get_technical_indicators("NIFTY")
        assert indicators.atr_14 == 0.0
        assert indicators.bollinger_upper == 0.0
