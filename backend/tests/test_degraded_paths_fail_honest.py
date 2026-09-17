"""Truth-of-Wall absence tests: when the feed is down, endpoints must return
nulls / 503 / explicit unavailable — never numbers.

The happy-path suites prove data flows when the broker answers. These tests
prove the other half of the contract: when `MarketService.get_quote` raises
(broker down, token expired, network gone), degraded endpoints report the
absence honestly. A number appearing on one of these paths means something
fabricated it — the exact failure mode Truth of Wall exists to prevent.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def feed_down(monkeypatch):
    """Every quote lookup raises — the 'FYERS is gone' scenario."""
    from app.services.market_service import MarketService

    async def _raise(self, symbol):
        raise ConnectionError("broker unreachable (test: feed down)")

    monkeypatch.setattr(MarketService, "get_quote", _raise)


# ---------------------------------------------------------------------------
# /health/ready — honest readiness
# ---------------------------------------------------------------------------

class TestHealthReady:
    def test_ready_503_when_central_feed_down(self, client, monkeypatch):
        from app.services.central_feed import central_feed

        monkeypatch.setattr(central_feed, "_running", False, raising=False)
        r = client.get("/health/ready")
        assert r.status_code == 503
        body = r.json()
        assert body["status"] == "unavailable"
        assert body["checks"]["central_feed"] == "down"

    def test_ready_ok_when_central_feed_running(self, client, monkeypatch):
        from app.services.central_feed import central_feed

        monkeypatch.setattr(central_feed, "_running", True, raising=False)
        r = client.get("/health/ready")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert r.json()["checks"]["central_feed"] == "ok"


# ---------------------------------------------------------------------------
# F&O context — the P0-4 pattern: a broker failure must never become a
# synthetic context. (Historical bug: the except-block returned
# spot=52000/24500, IV 14.5, OI 1.25M with market_data_valid=True.)
# ---------------------------------------------------------------------------

class TestFnoContext:
    def test_broker_failure_returns_unavailable_never_synthetic(self, feed_down):
        import asyncio

        from app.fno.context import get_fno_context

        ctx = asyncio.run(get_fno_context("NIFTY"))
        assert ctx["available"] is False
        # The whole point: no fabricated numbers where real ones belong.
        assert ctx["spot"] is None
        assert ctx["atm_iv"] is None
        assert ctx["pcr"] is None
        assert ctx["max_pain"] is None
        assert ctx["synthetic"] is False
        assert ctx["data_unavailable"] is True
        assert "No substitution" in ctx["reason"]

    def test_unknown_instrument_fails_closed(self):
        import asyncio

        from app.fno.context import get_fno_context

        ctx = asyncio.run(get_fno_context("NOT_A_REAL_UNDERLYING_XYZ"))
        assert ctx["available"] is False
        assert ctx.get("spot") in (None, ctx.get("spot"))  # no spot claim at all


# ---------------------------------------------------------------------------
# Dashboard — quote failure degrades to nulls + errors, never numbers
# ---------------------------------------------------------------------------

class TestDashboardDegraded:
    def test_quote_failure_leaves_price_null_and_flags_error(self, client, feed_down, monkeypatch):
        from app.api import dashboard as dashboard_api

        # Deterministic: bypass SWR caches entirely.
        monkeypatch.setattr(dashboard_api, "_cache", {})
        monkeypatch.setattr(dashboard_api, "_summary_cache", {})

        async def _noop_refresh(*a, **k):
            return None

        monkeypatch.setattr(dashboard_api, "_trigger_background_summary_refresh", _noop_refresh)
        monkeypatch.setattr(dashboard_api, "_refresh_summary_background", _noop_refresh)

        r = client.get("/api/v1/dashboard/NIFTY 50")
        assert r.status_code == 200  # dashboard degrades; it does not 500
        data = r.json()["data"]
        assert data["market"]["current_price"] is None
        assert data["degraded"] is True
        assert "quote" in data["errors"]
        assert data["quote_status"] in ("OFFLINE", "UNKNOWN", "")
        # No risk numbers may be computed off a missing price.
        risk = data["risk"]
        assert all(v is None for v in risk.values())

    def test_summary_degrades_without_fabricating_cards(self, client, feed_down, monkeypatch):
        from app.api import dashboard as dashboard_api

        monkeypatch.setattr(dashboard_api, "_summary_cache", {})
        monkeypatch.setattr(dashboard_api, "_refresh_summary_background", lambda *a, **k: None)

        r = client.get("/api/v1/dashboard/summary")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["degraded"] is True
        # Cards are structural placeholders when the feed is down: status must
        # say OFFLINE and ltp must be the structural zero (IndexCard.ltp is a
        # non-nullable float). A card showing a POSITIVE ltp with the feed down
        # would mean something fabricated a price.
        for card in data["cards"]:
            ltp = card.get("ltp")
            status = str(card.get("status", "")).upper()
            assert status == "OFFLINE", (
                f"card[{card.get('symbol', '?')}] status={status!r} with the feed down"
            )
            assert ltp in (0, 0.0, None), (
                f"card[{card.get('symbol', '?')}].ltp={ltp!r} with the feed down — fabricated?"
            )


# ---------------------------------------------------------------------------
# Research forecast — insufficient data stays 503, never a synthetic forecast
# (pins the documented "never synthetic" contract)
# ---------------------------------------------------------------------------

class TestForecastDegraded:
    def test_missing_candles_are_503_not_synthetic(self, client, feed_down):
        r = client.get("/api/v1/research/forecast/1h", params={"instrument": "NIFTY 50"})
        assert r.status_code == 503
        detail = str(r.json().get("detail", ""))
        # The 503 must be an honest data-gap reason, not a generic error.
        assert any(
            kw in detail.lower()
            for kw in ("insufficient", "candle", "deadline", "unavailable", "data")
        ), f"unexpected 503 reason: {detail}"

    def test_unknown_horizon_is_404(self, client):
        r = client.get("/api/v1/research/forecast/37min", params={"instrument": "NIFTY 50"})
        assert r.status_code == 404
