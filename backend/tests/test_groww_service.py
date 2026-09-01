"""Integration test for GrowwService + GrowwProvider quote flow.

Mocks httpx responses to simulate Groww's licensed API, then verifies
that:
  1. The service correctly parses the (string-form) ohlc field.
  2. The provider's _fetch_live_quote returns the normalized quote.
  3. Both /live-data/quote and /live-data/ltp paths work.
"""
import asyncio
import json
import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0, 'backend')

from app.services.groww_service import (
    GrowwService, _normalize_quote_payload, _parse_ohlc_string,
    INDEX_EXCHANGE_SYMBOLS,
)
from app.providers.groww import GrowwProvider
from app.core.token_manager import TokenInfo


class MockResp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body
    def json(self):
        return self._body
    @property
    def text(self):
        return json.dumps(self._body)


async def test_parser_unit():
    """Unit test for ohlc string parsing and quote normalization."""
    print("\n=== Test 1: ohlc string parser ===")
    parsed = _parse_ohlc_string("{open: 24077.55,high: 24143.15,low: 23952.55,close: 24080.4}")
    assert parsed is not None
    assert parsed["open"] == 24077.55
    assert parsed["close"] == 24080.4
    print(f"  parsed: {parsed}")

    parsed_dict = _parse_ohlc_string({"open": 100, "high": 110, "low": 95, "close": 105})
    assert parsed_dict["open"] == 100
    print(f"  dict form: {parsed_dict}")

    parsed_bad = _parse_ohlc_string("garbage")
    assert parsed_bad is None
    print(f"  garbage: {parsed_bad}")

    print("\n=== Test 2: quote payload normalization ===")
    payload = {
        "last_price": 24055.8,
        "day_change": -24.6,
        "day_change_perc": -0.1,
        "ohlc": "{open: 24077.55,high: 24143.15,low: 23952.55,close: 24080.4}",
        "high_trade_range": 24143.15,
        "low_trade_range": 23952.55,
        "volume": 100000,
        "open_interest": 0,
    }
    norm = _normalize_quote_payload(payload)
    assert norm is not None
    assert norm["ltp"] == 24055.8
    assert norm["open"] == 24077.55
    assert norm["prev"] == 24080.4  # ohlc.close = previous_close
    assert norm["volume"] == 100000
    print(f"  normalized: {norm}")

    # Payload missing last_price → None
    norm_bad = _normalize_quote_payload({"ohlc": "{}", "volume": 0})
    assert norm_bad is None
    print(f"  missing last_price: {norm_bad}")


async def test_service_ltp_bulk():
    """Test GrowwService.get_ltp_bulk parses the flat dict response."""
    print("\n=== Test 3: service.get_ltp_bulk (mocked) ===")
    svc = GrowwService(api_key="k", api_secret="s")

    mock_resp = MockResp(200, {
        "status": "SUCCESS",
        "payload": {"NSE_NIFTY": 24055.8, "BSE_SENSEX": 76944.28},
    })

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_resp)):
        result = await svc.get_ltp_bulk("fake-token", "CASH", ["NSE_NIFTY", "BSE_SENSEX"])
        print(f"  result: {result}")
        assert result == {"NSE_NIFTY": 24055.8, "BSE_SENSEX": 76944.28}


async def test_service_get_quote():
    """Test GrowwService.get_quote parses the full quote response."""
    print("\n=== Test 4: service.get_quote (mocked) ===")
    svc = GrowwService(api_key="k", api_secret="s")

    mock_resp = MockResp(200, {
        "status": "SUCCESS",
        "payload": {
            "last_price": 24055.8,
            "ohlc": "{open: 24077.55,high: 24143.15,low: 23952.55,close: 24080.4}",
            "high_trade_range": 24143.15,
            "low_trade_range": 23952.55,
            "volume": 100000,
        }
    })

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_resp)):
        result = await svc.get_quote("fake-token", "NSE", "CASH", "NIFTY")
        print(f"  result: {result}")
        assert result is not None
        assert result["ltp"] == 24055.8
        assert result["open"] == 24077.55


async def test_provider_quote():
    """End-to-end test: GrowwProvider._fetch_live_quote returns real data."""
    print("\n=== Test 5: provider._fetch_live_quote (all 5 indices) ===")
    p = GrowwProvider(api_key="k", api_secret="s")
    p.token_manager.set_token(TokenInfo(access_token="fake-valid-token", provider="groww"))

    # Mock the service methods directly to avoid HTTP entirely
    def mock_ltp(sym):
        return {
            "ltp": 24000.0 + abs(hash(sym)) % 1000,
            "open": 24000.0, "high": 24100.0,
            "low": 23950.0, "prev": 24080.4,
            "volume": 100000, "oi": 0,
        }

    p.service.get_ltp_bulk = AsyncMock(side_effect=lambda token, seg, syms: {syms[0]: mock_ltp(syms[0])["ltp"]} if syms else {})
    p.service.get_quote = AsyncMock(side_effect=lambda token, exch, seg, ts: mock_ltp(ts))

    for sym in ["NIFTY 50", "BANKNIFTY", "FINNIFTY", "SENSEX", "INDIA VIX"]:
        result = await p._fetch_live_quote(sym, "fake-valid-token")
        print(f"  {sym:12s} -> ltp={result['ltp']:>10.2f}")
        assert result is not None
        assert result["ltp"] > 0


async def main():
    await test_parser_unit()
    await test_service_ltp_bulk()
    await test_service_get_quote()
    await test_provider_quote()
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    asyncio.run(main())
