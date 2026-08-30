import pytest
from app.providers.mock import MockProvider
from app.providers.fyers import FyersProvider
from app.providers.upstox import UpstoxProvider
from app.providers.registry import get_provider


class TestProviders:
    @pytest.mark.asyncio
    async def test_mock_provider_option_chain(self):
        mock = MockProvider(mode="deterministic", seed=42)
        chain = await mock.get_option_chain("NIFTY")
        assert len(chain) > 0
        for quote in chain:
            assert quote.underlying == "NIFTY"
            assert quote.strike > 0
            assert quote.option_type in ["CE", "PE"]
            assert quote.ltp >= 0

    @pytest.mark.asyncio
    async def test_fyers_provider_structure(self):
        fyers = FyersProvider()
        assert fyers.provider_name == "fyers"
        quote = await fyers.get_quote("NIFTY 50")
        assert quote.symbol == "NIFTY 50"
        assert quote.provider == "fyers"

    @pytest.mark.asyncio
    async def test_upstox_provider_structure(self):
        upstox = UpstoxProvider()
        assert upstox.provider_name == "upstox"
        quote = await upstox.get_quote("BANKNIFTY")
        assert quote.symbol == "BANKNIFTY"
        assert quote.provider == "upstox"

    def test_registry_singleton(self):
        p1 = get_provider()
        p2 = get_provider()
        assert p1 is p2
