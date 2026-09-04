import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from app.models.market import (
    IndexCard,
    NormalizedQuote,
    MarketBreadthData,
    MarketStatusResponse,
    MarketSession,
    DataStatus,
)
from app.services.market_service import MarketService
from app.services.market_data_coordinator import market_data_coordinator


@pytest.fixture(autouse=True)
async def reset_coordinator_cache():
    await market_data_coordinator.clear()
    yield
    await market_data_coordinator.clear()


def _sample_card(symbol: str = "NIFTY 50", ltp: float = 25000.0) -> IndexCard:
    return IndexCard(
        symbol=symbol,
        display_name=symbol,
        ltp=ltp,
        open=ltp - 50,
        high=ltp + 50,
        low=ltp - 100,
        previous_close=ltp - 100,
        change=100.0,
        change_percent=0.4,
        volume=1000000,
        sparkline=[ltp - 100, ltp],
        status=DataStatus.LIVE,
        provider="mock",
    )


@pytest.mark.asyncio
async def test_market_service_get_index_cards():
    mock_provider = MagicMock()
    mock_cards = [_sample_card()]
    mock_provider.provider_name = "mock"
    mock_provider.get_index_cards = AsyncMock(return_value=mock_cards)

    service = MarketService(provider=mock_provider)

    # First call - fetches from provider
    cards1 = await service.get_index_cards()
    assert len(cards1) == 1
    assert cards1[0].symbol == "NIFTY 50"
    assert cards1[0].ltp == 25000.0
    assert mock_provider.get_index_cards.call_count == 1

    # Second call - served from coordinator cache
    cards2 = await service.get_index_cards()
    assert len(cards2) == 1
    assert cards2[0].symbol == "NIFTY 50"
    assert mock_provider.get_index_cards.call_count == 1


@pytest.mark.asyncio
async def test_market_service_single_flight_coalescing():
    mock_provider = MagicMock()
    mock_provider.provider_name = "mock"

    call_count = 0

    async def slow_fetch_cards():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)
        return [_sample_card(ltp=25100.0)]

    mock_provider.get_index_cards = slow_fetch_cards
    service = MarketService(provider=mock_provider)

    # Launch 5 concurrent calls
    results = await asyncio.gather(*[service.get_index_cards() for _ in range(5)])

    assert len(results) == 5
    for r in results:
        assert len(r) == 1
        assert r[0].ltp == 25100.0

    # Underlying provider must be called exactly once
    assert call_count == 1


@pytest.mark.asyncio
async def test_market_service_get_quote_and_resolution():
    mock_provider = MagicMock()
    mock_provider.provider_name = "mock"
    mock_provider.get_quote = AsyncMock(
        return_value=NormalizedQuote(
            symbol="NIFTY 50",
            display_name="NIFTY 50",
            timestamp=datetime.now(timezone.utc),
            ltp=25200.0,
            open=25000.0,
            high=25250.0,
            low=24950.0,
            previous_close=25000.0,
            change=200.0,
            change_percent=0.8,
            volume=2000000,
            status=DataStatus.LIVE,
            provider="mock",
        )
    )

    service = MarketService(provider=mock_provider)

    # Resolves NIFTY to NIFTY 50
    quote = await service.get_quote("NIFTY")
    assert quote.symbol == "NIFTY 50"
    assert quote.ltp == 25200.0

    # Invalid symbol raises ValueError
    with pytest.raises(ValueError):
        await service.get_quote("INVALID_UNKNOWN_SYMBOL")


@pytest.mark.asyncio
async def test_market_service_market_breadth_and_status():
    mock_provider = MagicMock()
    mock_provider.provider_name = "mock"
    mock_provider.get_market_breadth = AsyncMock(
        return_value=MarketBreadthData(
            advancing=320,
            declining=180,
            unchanged=0,
            advance_decline_ratio=1.78,
            sentiment="BULLISH",
            sentiment_score=65.0,
            status=DataStatus.LIVE,
            timestamp=datetime.now(timezone.utc),
        )
    )
    mock_provider.get_market_status = AsyncMock(
        return_value=MarketStatusResponse(
            session=MarketSession.OPEN,
            market_time=datetime.now(timezone.utc),
            is_trading_day=True,
            data_status=DataStatus.LIVE,
            provider="mock",
        )
    )

    service = MarketService(provider=mock_provider)

    breadth = await service.get_market_breadth()
    assert breadth.advancing == 320
    assert breadth.sentiment == "BULLISH"

    status = await service.get_market_status()
    assert status.session == MarketSession.OPEN
    assert status.is_trading_day is True


@pytest.mark.asyncio
async def test_market_service_fallback_on_provider_error():
    mock_provider = MagicMock()
    mock_provider.provider_name = "failing_mock"
    mock_provider.get_index_cards = AsyncMock(side_effect=RuntimeError("Provider failure"))

    service = MarketService(provider=mock_provider)

    # Protected by circuit breaker fallback -> returns empty list instead of crashing
    cards = await service.get_index_cards()
    assert cards == []
