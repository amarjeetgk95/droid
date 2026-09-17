"""
Tests for FeedHealthMonitor — Fail-Closed Truth of Live Market Data Feed.
Ensures the platform never falsely claims 'LIVE' when the market is closed,
broker authentication is missing, or broker ticks/chains are absent.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest

from app.signals.safety.feed_health_monitor import FeedHealthMonitor
from app.services.calendar_service import MarketSessionPermission


@pytest.fixture
def monitor():
    return FeedHealthMonitor()


def test_feed_health_closed_when_market_closed(monitor):
    perm = MarketSessionPermission(
        allowed=False,
        reason="MARKET_CLOSED",
        exchange="NSE",
        session="CLOSED",
        timestamp_ist=datetime.now(timezone.utc),
        market_open=None,
        market_close=None,
    )
    with patch("app.services.calendar_service.calendar_service.can_trade_now", return_value=perm):
        telemetry = monitor.get_telemetry()
        assert telemetry["status"] == "CLOSED"
        assert telemetry["is_healthy_for_trading"] is False
        assert "CLOSED" in telemetry["display_label"]
        assert telemetry["display_tone"] == "idle"


def test_feed_health_auth_required_when_token_missing(monitor):
    perm = MarketSessionPermission(
        allowed=True,
        reason="MARKET_OPEN",
        exchange="NSE",
        session="REGULAR",
        timestamp_ist=datetime.now(timezone.utc),
        market_open=datetime.now(timezone.utc),
        market_close=datetime.now(timezone.utc),
    )
    mock_cfg = MagicMock()
    mock_cfg.credentials = {"app_id": "test_app", "access_token": ""}

    with patch("app.services.calendar_service.calendar_service.can_trade_now", return_value=perm), \
         patch("app.core.broker_runtime.get_config", return_value=mock_cfg), \
         patch("app.core.broker_runtime.is_usable_access_token", return_value=False):
        telemetry = monitor.get_telemetry()
        assert telemetry["status"] == "AUTH_REQUIRED"
        assert telemetry["is_healthy_for_trading"] is False
        assert telemetry["display_tone"] == "down"


def test_feed_health_down_when_no_ticks_during_market_hours(monitor):
    perm = MarketSessionPermission(
        allowed=True,
        reason="MARKET_OPEN",
        exchange="NSE",
        session="REGULAR",
        timestamp_ist=datetime.now(timezone.utc),
        market_open=datetime.now(timezone.utc),
        market_close=datetime.now(timezone.utc),
    )
    mock_cfg = MagicMock()
    mock_cfg.credentials = {"app_id": "test_app", "access_token": "valid_token"}

    mock_cf_health = {
        "is_running": True,
        "last_tick_at": None,
        "tick_age_seconds": None,
        "is_ticking": False,
        "symbols_cached": 0,
    }

    with patch("app.services.calendar_service.calendar_service.can_trade_now", return_value=perm), \
         patch("app.core.broker_runtime.get_config", return_value=mock_cfg), \
         patch("app.core.broker_runtime.is_usable_access_token", return_value=True), \
         patch("app.services.central_feed.central_feed.get_feed_health", return_value=mock_cf_health):
        telemetry = monitor.get_telemetry()
        assert telemetry["status"] == "DOWN"
        assert telemetry["is_healthy_for_trading"] is False
        assert "FEED DOWN" in telemetry["display_label"]


def test_feed_health_chain_unavailable_when_spot_ticks_but_no_option_strikes(monitor):
    perm = MarketSessionPermission(
        allowed=True,
        reason="MARKET_OPEN",
        exchange="NSE",
        session="REGULAR",
        timestamp_ist=datetime.now(timezone.utc),
        market_open=datetime.now(timezone.utc),
        market_close=datetime.now(timezone.utc),
    )
    mock_cfg = MagicMock()
    mock_cfg.credentials = {"app_id": "test_app", "access_token": "valid_token"}

    mock_cf_health = {
        "is_running": True,
        "last_tick_at": datetime.now(timezone.utc).isoformat(),
        "tick_age_seconds": 2.5,
        "is_ticking": True,
        "symbols_cached": 5,
    }

    with patch("app.services.calendar_service.calendar_service.can_trade_now", return_value=perm), \
         patch("app.core.broker_runtime.get_config", return_value=mock_cfg), \
         patch("app.core.broker_runtime.is_usable_access_token", return_value=True), \
         patch("app.services.central_feed.central_feed.get_feed_health", return_value=mock_cf_health), \
         patch("app.signals.live_contract_cache.live_contract_cache.stats", return_value={"strikes": 0, "age_ms": -1}):
        telemetry = monitor.get_telemetry()
        assert telemetry["status"] == "CHAIN_UNAVAILABLE"
        assert telemetry["is_healthy_for_trading"] is False
        assert telemetry["display_label"] == "NO OPTION CHAIN"


def test_feed_health_live_when_everything_healthy(monitor):
    perm = MarketSessionPermission(
        allowed=True,
        reason="MARKET_OPEN",
        exchange="NSE",
        session="REGULAR",
        timestamp_ist=datetime.now(timezone.utc),
        market_open=datetime.now(timezone.utc),
        market_close=datetime.now(timezone.utc),
    )
    mock_cfg = MagicMock()
    mock_cfg.credentials = {"app_id": "test_app", "access_token": "valid_token"}

    mock_cf_health = {
        "is_running": True,
        "last_tick_at": datetime.now(timezone.utc).isoformat(),
        "tick_age_seconds": 1.2,
        "is_ticking": True,
        "symbols_cached": 5,
    }

    with patch("app.services.calendar_service.calendar_service.can_trade_now", return_value=perm), \
         patch("app.core.broker_runtime.get_config", return_value=mock_cfg), \
         patch("app.core.broker_runtime.is_usable_access_token", return_value=True), \
         patch("app.services.central_feed.central_feed.get_feed_health", return_value=mock_cf_health), \
         patch("app.signals.live_contract_cache.live_contract_cache.stats", return_value={"strikes": 42, "age_ms": 5000}), \
         patch("app.signals.option_marks.option_mark_registry.stats", return_value={"marks": 42, "by_source": {"CHAIN_LTP": 42}}):
        telemetry = monitor.get_telemetry()
        assert telemetry["status"] == "LIVE"
        assert telemetry["is_healthy_for_trading"] is True
        assert "LIVE" in telemetry["display_label"]
        assert telemetry["display_tone"] == "on"
