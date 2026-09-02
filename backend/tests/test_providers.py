import pytest
from app.providers.fyers import FyersProvider
from app.providers.binance_provider import BinanceProvider
from app.providers.registry import get_provider


class TestProviders:
    @pytest.mark.asyncio
    async def test_fyers_provider_structure(self):
        fyers = FyersProvider()
        assert fyers.provider_name == "fyers"
        quote = await fyers.get_quote("NIFTY 50")
        assert quote.symbol == "NIFTY 50"
        assert quote.provider == "fyers"

    @pytest.mark.asyncio
    async def test_binance_provider_structure(self):
        binance = BinanceProvider()
        assert binance.provider_name == "binance"

    def test_registry_singleton(self):
        p1 = get_provider()
        p2 = get_provider()
        assert p1 is p2