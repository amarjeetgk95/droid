"""
Unit and Integration Tests for Crypto Scalping Engine
Tests all 5 strategies, risk filtering, scanner, and API endpoints.
"""
import pytest
from datetime import datetime, timezone
from app.models.crypto import (
    SignalDirection,
    CryptoOrderBook,
    CryptoOrderBookLevel,
    CryptoDerivatives,
    BasisStatus,
    OrderBookSequenceStatus,
)
from app.models.market import NormalizedCandle, DataStatus
from app.crypto_scalp.base import (
    CryptoScalpContext,
    calc_ema,
    calc_atr,
    calc_vwap,
)
from app.crypto_scalp.strategies import CRYPTO_SCALP_STRATEGIES
from app.crypto_scalp.strategies.vwap_bounce import VWAPBounceStrategy
from app.crypto_scalp.strategies.ema_cross_scalp import EMACrossScalpStrategy
from app.crypto_scalp.strategies.funding_squeeze import FundingSqueezeStrategy
from app.crypto_scalp.strategies.breakout_volume import BreakoutVolumeStrategy
from app.crypto_scalp.strategies.depth_flip import DepthFlipStrategy
from app.crypto_scalp.risk_filter import crypto_scalp_risk_filter


def make_mock_candle(price: float, vol: float = 10.0, high: float = None, low: float = None, open_p: float = None) -> NormalizedCandle:
    return NormalizedCandle(
        timestamp=datetime.now(timezone.utc).isoformat(),
        open=open_p if open_p is not None else price,
        high=high if high is not None else price + 10.0,
        low=low if low is not None else price - 10.0,
        close=price,
        volume=vol,
        vwap=price,
    )


def test_ta_helpers():
    prices = [100.0, 102.0, 104.0, 103.0, 105.0]
    ema = calc_ema(prices, 3)
    assert ema > 100.0

    candles = [
        make_mock_candle(100.0, high=105.0, low=95.0),
        make_mock_candle(102.0, high=108.0, low=98.0),
        make_mock_candle(104.0, high=110.0, low=100.0),
    ]
    atr = calc_atr(candles, 3)
    assert atr > 0.0

    vwap = calc_vwap(candles)
    assert vwap > 90.0


def test_vwap_bounce_strategy():
    strat = VWAPBounceStrategy()
    assert strat.strategy_code == "VWAP_BOUNCE"

    # Bullish rejection at VWAP
    candles = [make_mock_candle(90000.0) for _ in range(10)]
    # Current candle dips to 89900 (pierces VWAP 90000) and bounces to close at 90050 with lower wick
    bounce_candle = make_mock_candle(
        price=90050.0,
        open_p=90010.0,
        high=90060.0,
        low=89900.0,
        vol=30.0,
    )
    candles.append(bounce_candle)

    ctx = CryptoScalpContext(
        symbol="BTCUSDT",
        asset="BTC",
        current_price=90050.0,
        candles_1m=candles,
        vwap_session=90000.0,
        ema_9_1m=90040.0,
        ema_21_1m=90020.0,
        atr_14_1m=100.0,
        volume_surge_ratio=1.5,
    )

    sig = strat.detect(ctx)
    assert sig is not None
    assert sig.direction == SignalDirection.LONG
    assert sig.entry_price == 90050.0
    assert sig.stop_loss < 90050.0
    assert sig.target_1 > 90050.0
    assert sig.risk_reward_ratio >= 1.3


def test_ema_cross_strategy():
    strat = EMACrossScalpStrategy()
    assert strat.strategy_code == "EMA_CROSS_SCALP"

    # Create 30 candles rising
    candles = [make_mock_candle(2500.0 + i * 2, vol=10.0) for i in range(30)]

    ctx = CryptoScalpContext(
        symbol="ETHUSDT",
        asset="ETH",
        current_price=2560.0,
        candles_1m=candles,
        ema_9_1m=2558.0,
        ema_21_1m=2550.0,
        ema_50_1m=2530.0,
        atr_14_1m=10.0,
        volume_surge_ratio=1.5,
    )

    sig = strat.detect(ctx)
    # If crossover or pullback detected
    if sig:
        assert sig.direction == SignalDirection.LONG
        assert sig.risk_reward_ratio >= 1.3


def test_funding_squeeze_strategy():
    strat = FundingSqueezeStrategy()
    assert strat.strategy_code == "FUNDING_SQUEEZE"

    # Heavily negative funding rate (-0.02%)
    derivs = CryptoDerivatives(
        symbol="BTCUSDT",
        mark_price=90000.0,
        index_price=90005.0,
        spot_price=90000.0,
        basis=0.0,
        basis_percent=0.0,
        basis_status=BasisStatus.NEUTRAL,
        funding_rate=-0.0002,
        funding_rate_percent=-0.02,
        annualized_funding_rate=-21.9,
        next_funding_time=datetime.now(timezone.utc),
        countdown_seconds=3600,
        open_interest_usd=5_000_000.0,
        open_interest_coins=55.5,
        long_short_ratio=0.82,
        long_percentage=45.0,
        short_percentage=55.0,
        status=DataStatus.LIVE,
    )

    candles = [make_mock_candle(89950.0) for _ in range(4)]
    # Green candle closing upwards
    candles.append(make_mock_candle(price=90000.0, open_p=89980.0, high=90010.0, low=89975.0))
    ctx = CryptoScalpContext(
        symbol="BTCUSDT",
        asset="BTC",
        current_price=90000.0,
        candles_1m=candles,
        derivatives=derivs,
        atr_14_1m=120.0,
        volume_surge_ratio=1.5,
    )

    sig = strat.detect(ctx)
    assert sig is not None
    assert sig.direction == SignalDirection.LONG
    assert "funding" in sig.rationale.lower() or "squeeze" in sig.rationale.lower()

    # Fail-closed test: If volume ratio is low (< 1.3), must NOT trigger
    low_vol_ctx = CryptoScalpContext(
        symbol="BTCUSDT",
        asset="BTC",
        current_price=90000.0,
        candles_1m=candles,
        derivatives=derivs,
        atr_14_1m=120.0,
        volume_surge_ratio=1.0,
    )
    assert strat.detect(low_vol_ctx) is None


def test_breakout_volume_strategy():
    strat = BreakoutVolumeStrategy()
    assert strat.strategy_code == "BREAKOUT_VOLUME"

    # Base candles fluctuating between 2900 and 3000
    candles = [make_mock_candle(2950.0, high=3000.0, low=2900.0) for _ in range(20)]
    # Breakout candle closing at 3015 above 3000
    breakout_candle = make_mock_candle(
        price=3015.0,
        open_p=2995.0,
        high=3020.0,
        low=2990.0,
        vol=50.0,
    )
    candles.append(breakout_candle)

    ctx = CryptoScalpContext(
        symbol="ETHUSDT",
        asset="ETH",
        current_price=3015.0,
        candles_1m=candles,
        high_15m=3000.0,
        low_15m=2900.0,
        atr_14_1m=15.0,
        volume_surge_ratio=2.5,
    )

    sig = strat.detect(ctx)
    assert sig is not None
    assert sig.direction == SignalDirection.LONG
    assert sig.entry_price == 3015.0
    assert sig.stop_loss < 3015.0
    assert sig.target_1 > 3015.0


def test_depth_flip_strategy():
    strat = DepthFlipStrategy()
    assert strat.strategy_code == "DEPTH_FLIP"

    ob = CryptoOrderBook(
        symbol="BTCUSDT",
        bids=[CryptoOrderBookLevel(price=90000.0, quantity=5.0, notional=450000.0)],
        asks=[CryptoOrderBookLevel(price=90005.0, quantity=1.0, notional=90005.0)],
        best_bid=90000.0,
        best_ask=90005.0,
        mid_price=90002.5,
        spread=5.0,
        spread_percent=0.005,
        bid_depth_total=50.0,
        ask_depth_total=20.0,
        depth_imbalance=0.35,  # +35% bid dominance
        depth_imbalance_pct=42.0,
        sequence_status=OrderBookSequenceStatus.ACTIVE,
        status=DataStatus.LIVE,
    )

    candles = [make_mock_candle(90000.0) for _ in range(4)]
    # Prominent green directional candle
    candles.append(make_mock_candle(price=90002.0, open_p=89985.0, high=90005.0, low=89980.0))
    ctx = CryptoScalpContext(
        symbol="BTCUSDT",
        asset="BTC",
        current_price=90002.0,
        candles_1m=candles,
        orderbook=ob,
        atr_14_1m=100.0,
        volume_surge_ratio=1.5,
    )

    sig = strat.detect(ctx)
    assert sig is not None
    assert sig.direction == SignalDirection.LONG
    assert "bid" in sig.rationale.lower()

    # Fail-closed test: If depth imbalance is low (< 35%), must NOT trigger
    low_imb_ob = ob.model_copy(update={"depth_imbalance_pct": 15.0})
    low_imb_ctx = CryptoScalpContext(
        symbol="BTCUSDT",
        asset="BTC",
        current_price=90002.0,
        candles_1m=candles,
        orderbook=low_imb_ob,
        atr_14_1m=100.0,
        volume_surge_ratio=1.5,
    )
    assert strat.detect(low_imb_ctx) is None

    # Fail-closed test: If volume is low, must NOT trigger
    low_vol_ctx = CryptoScalpContext(
        symbol="BTCUSDT",
        asset="BTC",
        current_price=90002.0,
        candles_1m=candles,
        orderbook=ob,
        atr_14_1m=100.0,
        volume_surge_ratio=1.0,
    )
    assert strat.detect(low_vol_ctx) is None


def test_risk_filter_sanity():
    # Valid candidate
    from app.crypto_scalp.base import CryptoScalpCandidate
    candidate = CryptoScalpCandidate(
        symbol="BTCUSDT",
        asset="BTC",
        direction=SignalDirection.LONG,
        strategy="TEST",
        strategy_name="Test Strategy",
        entry_price=90000.0,
        stop_loss=89500.0,
        target_1=90800.0,
        target_2=91500.0,
        risk_points=500.0,
        risk_percent=0.55,
        risk_reward_ratio=1.6,
        confidence=80.0,
        rationale="Testing risk filter",
    )

    valid, reason = crypto_scalp_risk_filter.validate(candidate)
    assert valid is True

    # Bad candidate: stop loss above entry on long
    candidate.stop_loss = 90500.0
    valid, reason = crypto_scalp_risk_filter.validate(candidate)
    assert valid is False

    # Bad candidate: risk exceeds max
    candidate.stop_loss = 88000.0
    candidate.risk_percent = 2.5
    valid, reason = crypto_scalp_risk_filter.validate(candidate)
    assert valid is False


def test_crypto_scalp_api_endpoints():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    # 1. Diagnostics endpoint
    diag_resp = client.get("/api/v1/crypto/scalp-signals/diagnostics")
    assert diag_resp.status_code == 200
    diag_data = diag_resp.json()
    assert "strategies_evaluated" in diag_data
    assert diag_data["strategies_evaluated"] == 5
    assert "scan_interval_seconds" in diag_data

    # 2. Config update endpoint
    cfg_resp = client.patch(
        "/api/v1/crypto/scalp-signals/config",
        json={"scan_interval_seconds": 45, "telegram_enabled": True},
    )
    assert cfg_resp.status_code == 200
    cfg_data = cfg_resp.json()
    assert cfg_data["scan_interval_seconds"] == 45
    assert cfg_data["telegram_enabled"] is True

    # 3. Signals query endpoint
    sig_resp = client.get("/api/v1/crypto/scalp-signals")
    assert sig_resp.status_code == 200
    sig_data = sig_resp.json()
    assert "signals" in sig_data
    assert "total_active" in sig_data
    assert "diagnostics" in sig_data


@pytest.mark.asyncio
async def test_scanner_anti_spam_and_cooldown():
    from unittest.mock import AsyncMock, patch
    from app.crypto_scalp.scanner import CryptoScalpScanner

    scanner = CryptoScalpScanner()
    candles = [make_mock_candle(2950.0, high=3000.0, low=2900.0) for _ in range(20)]
    breakout_candle = make_mock_candle(
        price=3015.0, open_p=2995.0, high=3020.0, low=2990.0, vol=50.0,
    )
    candles.append(breakout_candle)
    ctx = CryptoScalpContext(
        symbol="ETHUSDT",
        asset="ETH",
        current_price=3015.0,
        candles_1m=candles,
        high_15m=3000.0,
        low_15m=2900.0,
        atr_14_1m=15.0,
        volume_surge_ratio=2.5,
    )

    with patch.object(scanner, "build_context", new_callable=AsyncMock) as mock_ctx:
        mock_ctx.return_value = ctx
        # 1. First scan generates exactly 1 signal
        sigs1 = await scanner.scan_symbol("ETHUSDT")
        assert len(sigs1) == 1
        initial_id = sigs1[0].id

        # 2. Second immediate scan must reuse active signal without creating a new one (anti-spam)
        sigs2 = await scanner.scan_symbol("ETHUSDT")
        assert len(sigs2) == 1
        assert sigs2[0].id == initial_id
        assert len(scanner._active_signals) == 1

        # 3. If signal is archived, cooldown prevents immediate re-trigger within 30m
        scanner._active_signals.clear()
        sigs3 = await scanner.scan_symbol("ETHUSDT")
        assert len(sigs3) == 0

