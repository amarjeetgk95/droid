"""Tests for Date Chunker and Symbol Translation."""

from datetime import date
import pytest
from app.historical_data.providers.fyers import split_date_range, FYERSHistoricalProvider


def test_split_date_range_one_year():
    start = date(2025, 9, 22)
    end = date(2026, 9, 22)

    chunks = split_date_range(start, end, max_days=95)
    assert len(chunks) >= 4

    # Verify contiguous with no gaps and no overlaps
    assert chunks[0][0] == start
    assert chunks[-1][1] == end

    for i in range(len(chunks) - 1):
        curr_end = chunks[i][1]
        next_start = chunks[i + 1][0]
        assert (next_start - curr_end).days == 1
        assert (curr_end - chunks[i][0]).days < 95


def test_symbol_resolution():
    provider = FYERSHistoricalProvider()

    assert provider.resolve_provider_symbol("SENSEX") == "BSE:SENSEX-INDEX"
    assert provider.resolve_provider_symbol("BSE:SENSEX") == "BSE:SENSEX-INDEX"
    assert provider.resolve_provider_symbol("NIFTY") == "NSE:NIFTY50-INDEX"
    assert provider.resolve_provider_symbol("BANKNIFTY") == "NSE:NIFTYBANK-INDEX"
    assert provider.resolve_provider_symbol("FINNIFTY") == "NSE:FINNIFTY-INDEX"
    assert provider.resolve_provider_symbol("INDIA VIX") == "NSE:INDIAVIX-INDEX"


def test_timeframe_resolution():
    provider = FYERSHistoricalProvider()

    assert provider.resolve_timeframe("1m") == "1"
    assert provider.resolve_timeframe("5m") == "5"
    assert provider.resolve_timeframe("15m") == "15"
    assert provider.resolve_timeframe("1h") == "60"
    assert provider.resolve_timeframe("1D") == "D"

    with pytest.raises(ValueError):
        provider.resolve_timeframe("unknown_tf")
