from datetime import datetime, timezone
from unittest.mock import AsyncMock
import pytest
from app.services.options_service import OptionsService
from app.models.market import NormalizedOptionQuote, NormalizedQuote, DataStatus


def _create_sample_chain(underlying: str = "NIFTY", base: float = 24000.0) -> list[NormalizedOptionQuote]:
    now = datetime.now(timezone.utc)
    exp = datetime(2026, 9, 10, tzinfo=timezone.utc)
    quotes = []
    for offset in (-100.0, -50.0, 0.0, 50.0, 100.0):
        strike = base + offset
        quotes.append(NormalizedOptionQuote(
            timestamp=now,
            provider="test",
            instrument="OPT",
            contract_id=f"{underlying}{int(strike)}CE",
            underlying=underlying,
            expiry=exp,
            strike=strike,
            option_type="CE",
            ltp=max(10.0, 200.0 - offset),
            volume=5000,
            oi=20000,
        ))
        quotes.append(NormalizedOptionQuote(
            timestamp=now,
            provider="test",
            instrument="OPT",
            contract_id=f"{underlying}{int(strike)}PE",
            underlying=underlying,
            expiry=exp,
            strike=strike,
            option_type="PE",
            ltp=max(10.0, 200.0 + offset),
            volume=4000,
            oi=18000,
        ))
    return quotes


class TestOptionsService:
    @pytest.mark.asyncio
    async def test_get_option_chain_matrix(self):
        service = OptionsService()
        service.market_service.get_quote = AsyncMock(return_value=NormalizedQuote(
            symbol="NIFTY", display_name="NIFTY", timestamp=datetime.now(timezone.utc),
            ltp=24000.0, open=23950.0, high=24050.0, low=23900.0, previous_close=23900.0,
            change=100.0, change_percent=0.4, volume=1000000, status=DataStatus.LIVE, provider="test",
        ))
        service.market_service.get_option_chain = AsyncMock(return_value=_create_sample_chain("NIFTY", 24000.0))

        chain = await service.get_option_chain_matrix("NIFTY")

        assert chain.underlying == "NIFTY"
        assert chain.spot_price > 0
        assert chain.futures_price > 0
        assert len(chain.strikes) > 0

        # Check ATM strike row
        atm_rows = [r for r in chain.strikes if r.is_atm]
        assert len(atm_rows) == 1
        atm = atm_rows[0]
        assert atm.call is not None
        assert atm.put is not None
        assert atm.call.greeks is not None
        assert atm.put.greeks is not None
        assert atm.call.greeks.delta > 0
        assert atm.put.greeks.delta < 0

    @pytest.mark.asyncio
    async def test_options_analytics_metrics(self):
        service = OptionsService()
        service.market_service.get_quote = AsyncMock(return_value=NormalizedQuote(
            symbol="NIFTY", display_name="NIFTY", timestamp=datetime.now(timezone.utc),
            ltp=24000.0, open=23950.0, high=24050.0, low=23900.0, previous_close=23900.0,
            change=100.0, change_percent=0.4, volume=1000000, status=DataStatus.LIVE, provider="test",
        ))
        service.market_service.get_option_chain = AsyncMock(return_value=_create_sample_chain("NIFTY", 24000.0))

        chain = await service.get_option_chain_matrix("NIFTY")
        analytics = chain.analytics

        assert analytics.pcr_oi > 0
        assert analytics.pcr_volume > 0
        assert analytics.max_pain_strike > 0
        assert analytics.total_call_oi > 0
        assert analytics.total_put_oi > 0

    @pytest.mark.asyncio
    async def test_max_pain_distribution(self):
        service = OptionsService()
        service.market_service.get_quote = AsyncMock(return_value=NormalizedQuote(
            symbol="NIFTY", display_name="NIFTY", timestamp=datetime.now(timezone.utc),
            ltp=24000.0, open=23950.0, high=24050.0, low=23900.0, previous_close=23900.0,
            change=100.0, change_percent=0.4, volume=1000000, status=DataStatus.LIVE, provider="test",
        ))
        service.market_service.get_option_chain = AsyncMock(return_value=_create_sample_chain("NIFTY", 24000.0))

        max_pain = await service.calculate_max_pain("NIFTY")

        assert max_pain.symbol == "NIFTY"
        assert max_pain.max_pain_strike > 0
        assert len(max_pain.strikes) == len(max_pain.payouts)
        assert len(max_pain.strikes) > 0

    @pytest.mark.asyncio
    async def test_empty_chain_when_offline(self):
        service = OptionsService()
        service.market_service.get_quote = AsyncMock(return_value=NormalizedQuote(
            symbol="NIFTY", display_name="NIFTY", timestamp=datetime.now(timezone.utc),
            ltp=24000.0, open=23950.0, high=24050.0, low=23900.0, previous_close=23900.0,
            change=100.0, change_percent=0.4, volume=1000000, status=DataStatus.OFFLINE, provider="test",
        ))
        service.market_service.get_option_chain = AsyncMock(return_value=[])

        chain = await service.get_option_chain_matrix("NIFTY")
        assert len(chain.strikes) == 0
        assert chain.analytics.total_call_oi == 0
        assert chain.analytics.total_put_oi == 0

        max_pain = await service.calculate_max_pain("NIFTY")
        assert len(max_pain.strikes) == 0
        assert max_pain.total_loss_at_max_pain == 0.0
