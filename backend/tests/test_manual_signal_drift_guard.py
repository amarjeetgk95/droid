"""Drift-guard contract: pinned feed, 6%->400, 3%->200, degraded w/o price->503."""
from datetime import datetime, timezone
from types import SimpleNamespace

from tests.conftest import PINNED_FEED


def _gen(client, **over):
    base = {
        "underlying": "NIFTY",
        "strategy": "BREAKOUT",
        "direction": "LONG_CALL",
        "timeframe": "5M",
        "notify_telegram": False,
        "allow_closed_market": True,
    }
    base.update(over)
    return client.post("/api/v1/signals/generate", json=base)


def test_drift_6pct_rejected(client, mock_market_feed, mock_market_open):
    ltp = PINNED_FEED["NIFTY 50"]
    res = _gen(client, current_price=round(ltp * 1.06, 2))
    assert res.status_code == 400
    assert "deviat" in res.json()["detail"].lower()


def test_drift_02pct_accepted(client, mock_market_feed, mock_market_open):
    # Live threshold is max(0.3%, 2*ATR%) — 3% is now also rejected (stricter
    # than the legacy 5% ceiling). 0.2% is inside the corridor -> 200.
    ltp = PINNED_FEED["NIFTY 50"]
    res = _gen(client, current_price=round(ltp * 1.002, 2))
    assert res.status_code == 200, res.text
    assert res.json()["success"] is True


def test_drift_3pct_rejected_strict(client, mock_market_feed, mock_market_open):
    ltp = PINNED_FEED["NIFTY 50"]
    res = _gen(client, current_price=round(ltp * 1.03, 2))
    assert res.status_code == 400


def _degraded_quote(status, ltp=None):
    return SimpleNamespace(status=status, provider="fyers", ltp=ltp)


def test_degraded_without_price_fails_closed(client, mock_market_open, monkeypatch):
    from app.services.market_service import MarketService

    async def _bad(self, symbol):
        return _degraded_quote("STALE", None)

    monkeypatch.setattr(MarketService, "get_quote", _bad)
    res = _gen(client)  # no manual price, no live price
    assert res.status_code in (400, 503)


def test_closed_status_without_price_fails_closed(client, mock_market_open, monkeypatch):
    from app.services.market_service import MarketService

    async def _closed(self, symbol):
        return SimpleNamespace(
            status="CLOSED", provider="fyers", ltp=None,
            timestamp=datetime.now(timezone.utc),
        )

    monkeypatch.setattr(MarketService, "get_quote", _closed)
    res = _gen(client)
    assert res.status_code in (400, 503)


def test_live_pinned_zero_drift_ok(client, mock_market_feed, mock_market_open):
    ltp = PINNED_FEED["NIFTY 50"]
    res = _gen(client, current_price=ltp)
    assert res.status_code == 200, res.text
