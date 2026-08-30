import pytest
from app.providers.mock import MockProvider


class TestMockProviderDeterministic:
    """Test that seed=42 produces reproducible output."""

    @pytest.mark.asyncio
    async def test_deterministic_quotes(self):
        p1 = MockProvider(mode="deterministic", seed=42)
        p2 = MockProvider(mode="deterministic", seed=42)
        q1 = await p1.get_quotes()
        q2 = await p2.get_quotes()
        for a, b in zip(q1, q2):
            assert a.ltp == b.ltp
            assert a.symbol == b.symbol

    @pytest.mark.asyncio
    async def test_deterministic_candles(self):
        p1 = MockProvider(mode="deterministic", seed=42)
        p2 = MockProvider(mode="deterministic", seed=42)
        c1 = await p1.get_candles("NIFTY 50", "5m")
        c2 = await p2.get_candles("NIFTY 50", "5m")
        assert len(c1) == len(c2)
        for a, b in zip(c1, c2):
            assert a.timestamp == b.timestamp
            assert a.close == b.close


class TestMockProviderQuotes:
    @pytest.mark.asyncio
    async def test_all_symbols_present(self):
        provider = MockProvider(mode="deterministic", seed=42)
        quotes = await provider.get_quotes()
        symbols = {q.symbol for q in quotes}
        assert "NIFTY 50" in symbols
        assert "BANKNIFTY" in symbols
        assert "FINNIFTY" in symbols
        assert "SENSEX" in symbols
        assert "INDIA VIX" in symbols

    @pytest.mark.asyncio
    async def test_single_quote(self):
        provider = MockProvider(mode="deterministic", seed=42)
        quote = await provider.get_quote("NIFTY 50")
        assert quote.symbol == "NIFTY 50"
        assert quote.ltp > 0
        assert quote.status.value == "DEMO"  # Never LIVE for mock

    @pytest.mark.asyncio
    async def test_vix_has_no_oi(self):
        provider = MockProvider(mode="deterministic", seed=42)
        quote = await provider.get_quote("INDIA VIX")
        assert quote.open_interest is None

    @pytest.mark.asyncio
    async def test_invalid_symbol_raises(self):
        provider = MockProvider(mode="deterministic", seed=42)
        with pytest.raises(ValueError):
            await provider.get_quote("INVALID_SYMBOL")

    @pytest.mark.asyncio
    async def test_status_never_live(self):
        provider = MockProvider(mode="deterministic", seed=42)
        quotes = await provider.get_quotes()
        for q in quotes:
            assert q.status.value != "LIVE"


class TestMockProviderCandles:
    @pytest.mark.asyncio
    async def test_candle_data_integrity(self):
        provider = MockProvider(mode="deterministic", seed=42)
        candles = await provider.get_candles("NIFTY 50", "5m")
        assert len(candles) > 0
        for c in candles:
            assert c.high >= max(c.open, c.close), f"High {c.high} < max(O={c.open}, C={c.close})"
            assert c.low <= min(c.open, c.close), f"Low {c.low} > min(O={c.open}, C={c.close})"
            assert c.volume >= 0

    @pytest.mark.asyncio
    async def test_candle_timestamps_ordered(self):
        provider = MockProvider(mode="deterministic", seed=42)
        candles = await provider.get_candles("BANKNIFTY", "15m")
        for i in range(1, len(candles)):
            assert candles[i].timestamp > candles[i - 1].timestamp

    @pytest.mark.asyncio
    async def test_no_duplicate_timestamps(self):
        provider = MockProvider(mode="deterministic", seed=42)
        candles = await provider.get_candles("NIFTY 50", "1m")
        timestamps = [c.timestamp for c in candles]
        assert len(timestamps) == len(set(timestamps))

    @pytest.mark.asyncio
    async def test_timeframe_sizes(self):
        provider = MockProvider(mode="deterministic", seed=42)
        c_1m = await provider.get_candles("NIFTY 50", "1m")
        c_5m = await provider.get_candles("NIFTY 50", "5m")
        c_15m = await provider.get_candles("NIFTY 50", "15m")
        c_1h = await provider.get_candles("NIFTY 50", "1h")
        assert len(c_1m) > len(c_5m) > len(c_15m) > len(c_1h)


class TestMockProviderHealth:
    @pytest.mark.asyncio
    async def test_health_is_demo(self):
        provider = MockProvider(mode="deterministic", seed=42)
        health = await provider.get_health()
        assert health.status == "HEALTHY"
        assert health.provider == "mock"
        assert health.mode == "DEMO"

    @pytest.mark.asyncio
    async def test_provider_name(self):
        provider = MockProvider(mode="deterministic", seed=42)
        assert provider.provider_name == "mock"


class TestMockProviderBreadth:
    @pytest.mark.asyncio
    async def test_breadth_data(self):
        provider = MockProvider(mode="deterministic", seed=42)
        breadth = await provider.get_market_breadth()
        assert breadth.advancing >= 0
        assert breadth.declining >= 0
        assert breadth.unchanged >= 0
        assert breadth.status.value == "DEMO"
        assert len(breadth.sectors) > 0
