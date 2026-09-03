import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.crypto_signal_engine import crypto_signal_engine
from app.models.crypto import (
    CryptoTicker,
    CryptoOrderBook,
    CryptoOrderBookLevel,
    CryptoDerivatives,
    CryptoPairComparison,
    RelativeStrengthStatus,
    SignalDirection,
    BasisStatus,
)
from app.models.market import DataStatus


@pytest.fixture
def client():
    return TestClient(app)


def test_crypto_signal_engine_depth_imbalance():
    ticker = CryptoTicker(
        symbol="BTCUSDT",
        asset="BTC",
        display_name="Bitcoin",
        price=85000.0,
        change_24h=1500.0,
        change_percent_24h=1.8,
        high_24h=86000.0,
        low_24h=83500.0,
        volume_24h_quote=1500000000.0,
        volume_24h_base=18000.0,
        sparkline=[84000.0, 85000.0],
    )
    # Heavy bid imbalance: bids 15M, asks 5M -> +50% imbalance
    ob = CryptoOrderBook(
        symbol="BTCUSDT",
        bids=[CryptoOrderBookLevel(price=84990.0, quantity=5.0, notional=424950.0, cumulative_notional=15000000.0)],
        asks=[CryptoOrderBookLevel(price=85010.0, quantity=2.0, notional=170020.0, cumulative_notional=5000000.0)],
        spread=20.0,
        spread_percent=0.023,
        mid_price=85000.0,
        best_bid=84990.0,
        best_ask=85010.0,
        bid_depth_total=15000000.0,
        ask_depth_total=5000000.0,
        depth_imbalance=10000000.0,
        depth_imbalance_pct=50.0,
    )

    signals = crypto_signal_engine.generate_signals_for_pair(ticker=ticker, orderbook=ob)
    assert len(signals) >= 1
    depth_sig = next(s for s in signals if s.strategy == "DEPTH_IMBALANCE_FLOW")
    assert depth_sig.direction == SignalDirection.LONG
    assert depth_sig.asset == "BTC"
    assert depth_sig.target_1 > depth_sig.entry_price
    assert depth_sig.stop_loss < depth_sig.entry_price
    assert depth_sig.risk_reward_ratio >= 1.5


def test_crypto_signal_engine_funding_squeeze():
    ticker = CryptoTicker(
        symbol="ETHUSDT",
        asset="ETH",
        display_name="Ethereum",
        price=2600.0,
        change_24h=50.0,
        change_percent_24h=2.0,
        high_24h=2650.0,
        low_24h=2550.0,
        volume_24h_quote=600000000.0,
        volume_24h_base=230000.0,
        sparkline=[2550.0, 2600.0],
    )
    derivs = CryptoDerivatives(
        symbol="ETHUSDT",
        mark_price=2600.0,
        index_price=2600.0,
        funding_rate=-0.00015,  # -0.015%
        funding_rate_percent=-0.015,
        annualized_funding_rate=-16.425,
        next_funding_time="2026-09-03T16:00:00Z",
        countdown_seconds=12400,
        open_interest_usd=1200000000.0,
        open_interest_coins=461538.0,
        long_short_ratio=0.82,
        long_percentage=45.0,
        short_percentage=55.0,
    )

    signals = crypto_signal_engine.generate_signals_for_pair(ticker=ticker, derivatives=derivs)
    fund_sig = next(s for s in signals if s.strategy == "FUNDING_SQUEEZE")
    assert fund_sig.direction == SignalDirection.LONG
    assert fund_sig.confidence >= 80.0
    assert "Negative Funding Rate" in fund_sig.confluence_factors[0]


def test_crypto_signals_api_endpoints(client):
    # Test GET /api/v1/crypto/signals
    resp = client.get("/api/v1/crypto/signals")
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert "signals" in body["data"]
    assert "total_active" in body["data"]

    # Test GET /api/v1/crypto/BTCUSDT/signals
    btc_resp = client.get("/api/v1/crypto/BTCUSDT/signals")
    assert btc_resp.status_code == 200
    btc_body = btc_resp.json()
    assert "signals" in btc_body["data"]
    for s in btc_body["data"]["signals"]:
        assert s["symbol"] == "BTCUSDT"

    # Test rejecting unsupported symbol for signals
    bad_resp = client.get("/api/v1/crypto/SOLUSDT/signals")
    assert bad_resp.status_code == 400
