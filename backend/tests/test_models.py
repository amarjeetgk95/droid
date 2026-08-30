import pytest
from datetime import datetime, timezone
from app.models.market import (
    NormalizedQuote, NormalizedCandle, IndexCard,
    DataStatus, MarketSession,
)


class TestNormalizedQuote:
    def test_valid_quote(self):
        quote = NormalizedQuote(
            symbol="NIFTY 50",
            display_name="NIFTY 50",
            timestamp=datetime.now(timezone.utc),
            ltp=25042.50,
            open=24980.00,
            high=25100.00,
            low=24950.00,
            previous_close=24900.00,
            change=142.50,
            change_percent=0.57,
            volume=1234567,
            open_interest=None,
            status=DataStatus.DEMO,
            provider="mock",
        )
        assert quote.symbol == "NIFTY 50"
        assert quote.status == DataStatus.DEMO

    def test_oi_nullable(self):
        """OI must be None for indices like VIX, not 0."""
        quote = NormalizedQuote(
            symbol="INDIA VIX",
            display_name="India VIX",
            timestamp=datetime.now(timezone.utc),
            ltp=13.42,
            open=13.10,
            high=13.80,
            low=13.00,
            previous_close=13.50,
            change=-0.08,
            change_percent=-0.59,
            volume=0,
            open_interest=None,
        )
        assert quote.open_interest is None

    def test_default_status_is_demo(self):
        quote = NormalizedQuote(
            symbol="TEST",
            display_name="Test",
            timestamp=datetime.now(timezone.utc),
            ltp=100.0,
            open=99.0,
            high=101.0,
            low=98.0,
            previous_close=99.5,
            change=0.5,
            change_percent=0.5,
            volume=1000,
        )
        assert quote.status == DataStatus.DEMO
        assert quote.provider == "mock"


class TestNormalizedCandle:
    def test_valid_candle(self):
        candle = NormalizedCandle(
            timestamp=datetime.now(timezone.utc),
            open=25000.0,
            high=25050.0,
            low=24980.0,
            close=25030.0,
            volume=50000,
            vwap=25010.0,
        )
        assert candle.high >= candle.open
        assert candle.high >= candle.close
        assert candle.low <= candle.open
        assert candle.low <= candle.close

    def test_vwap_optional(self):
        candle = NormalizedCandle(
            timestamp=datetime.now(timezone.utc),
            open=100.0,
            high=105.0,
            low=95.0,
            close=102.0,
            volume=1000,
        )
        assert candle.vwap is None


class TestIndexCard:
    def test_sparkline_default_empty(self):
        card = IndexCard(
            symbol="TEST",
            display_name="Test",
            ltp=100.0,
            change=1.0,
            change_percent=1.0,
            open=99.0,
            high=101.0,
            low=98.0,
            previous_close=99.0,
            volume=1000,
        )
        assert card.sparkline == []
        assert card.status == DataStatus.DEMO
