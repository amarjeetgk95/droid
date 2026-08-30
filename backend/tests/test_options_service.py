import pytest
from app.services.options_service import OptionsService


class TestOptionsService:
    @pytest.mark.asyncio
    async def test_get_option_chain_matrix(self):
        service = OptionsService()
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
        max_pain = await service.calculate_max_pain("NIFTY")

        assert max_pain.symbol == "NIFTY"
        assert max_pain.max_pain_strike > 0
        assert len(max_pain.strikes) == len(max_pain.payouts)
        assert len(max_pain.strikes) > 0
