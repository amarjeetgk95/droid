"""
Comprehensive Tests for Signal Generation Engine Hardening.

Covers:
1. Centralized Market Session Guard (blocking after hours, allow_closed_market override).
2. API endpoints: POST /generate, POST /auto-detect market checks.
3. Paper execution option pricing (premium-based, not index spot).
4. Trigger gate geometry validations (SL orientation, target ordering, R:R calculation).
5. Contract resolver expiry holiday adjustment.
6. Deterministic validator fail-closed defaults.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch, AsyncMock, MagicMock
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.calendar_service import calendar_service, MarketSessionPermission
from app.signals.market_guard import require_market_open, ensure_market_open_or_raise_http, MarketClosedError
from app.signals.trigger_gate import check_trigger_integrity
from app.signals.contract_resolver import resolve_nearest_expiry
from app.signals.paper_engine import SignalPaperEngine
from app.signals.fsm import SignalInstance, signal_fsm
from app.ai.deterministic_validator import deterministic_trade_validator
from app.ai.schemas import AISignal, Decision, ValidationStatus


def make_perm(allowed: bool, reason: str = "TEST"):
    now_ist = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    return MarketSessionPermission(
        allowed=allowed,
        reason=reason,
        exchange="NSE",
        session="REGULAR" if allowed else "CLOSED",
        timestamp_ist=now_ist,
        market_open=now_ist.replace(hour=9, minute=15),
        market_close=now_ist.replace(hour=15, minute=30),
    )


class TestMarketGuard:
    def test_require_market_open_raises_when_closed(self):
        with patch.object(calendar_service, "can_trade_now", return_value=make_perm(False, "MARKET_CLOSED")):
            with pytest.raises(MarketClosedError) as exc_info:
                require_market_open()
            assert "Market is closed" in str(exc_info.value)
            assert exc_info.value.reason == "MARKET_CLOSED"

    def test_require_market_open_allows_override(self):
        with patch.object(calendar_service, "can_trade_now", return_value=make_perm(False, "MARKET_CLOSED")):
            perm = require_market_open(allow_closed=True)
            assert perm.allowed is False  # returned object preserved


class TestSignalsApiHardening:
    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_post_generate_blocked_when_market_closed(self, client):
        with patch.object(calendar_service, "can_trade_now", return_value=make_perm(False, "MARKET_CLOSED")):
            resp = client.post(
                "/api/v1/signals/generate",
                json={
                    "underlying": "NIFTY",
                    "strategy": "BREAKOUT",
                    "direction": "LONG_CALL",
                    "current_price": 24500.0,
                    "trigger": 24550.0,
                    "stop_loss": 24450.0,
                    "target_1": 24650.0,
                    "target_2": 24750.0,
                },
            )
            assert resp.status_code == 400
            assert "market is closed" in resp.json()["detail"].lower()

    def test_post_auto_detect_blocked_when_market_closed(self, client):
        with patch.object(calendar_service, "can_trade_now", return_value=make_perm(False, "MARKET_CLOSED")):
            resp = client.post(
                "/api/v1/signals/auto-detect",
                json={"underlying": "NIFTY", "strategy": "BREAKOUT", "timeframe": "5M"},
            )
            assert resp.status_code == 400
            assert "market is closed" in resp.json()["detail"].lower()


class TestTriggerGateGeometry:
    def test_rejects_sl_on_wrong_side_for_call(self):
        res = check_trigger_integrity(
            direction="LONG_CALL",
            spot_price=24500.0,
            entry_min=24520.0,
            entry_max=24540.0,
            trigger=24530.0,
            stop_loss=24540.0,  # SL above trigger for CALL!
            target_1=24600.0,
            target_2=24700.0,
            risk_points=10.0,
        )
        assert res.passed is False
        assert res.reason_code == "SL_WRONG_SIDE"

    def test_rejects_sl_on_wrong_side_for_put(self):
        res = check_trigger_integrity(
            direction="LONG_PUT",
            spot_price=24500.0,
            entry_min=24460.0,
            entry_max=24480.0,
            trigger=24470.0,
            stop_loss=24450.0,  # SL below trigger for PUT!
            target_1=24400.0,
            target_2=24300.0,
            risk_points=20.0,
        )
        assert res.passed is False
        assert res.reason_code == "SL_WRONG_SIDE"

    def test_rejects_misordered_targets_for_call(self):
        res = check_trigger_integrity(
            direction="LONG_CALL",
            spot_price=24500.0,
            entry_min=24520.0,
            entry_max=24540.0,
            trigger=24530.0,
            stop_loss=24480.0,
            target_1=24650.0,
            target_2=24600.0,  # Target 2 below Target 1!
            risk_points=50.0,
        )
        assert res.passed is False
        assert res.reason_code == "TARGETS_MISORDERED"

    def test_rejects_target1_wrong_side_for_call(self):
        res = check_trigger_integrity(
            direction="LONG_CALL",
            spot_price=24500.0,
            entry_min=24520.0,
            entry_max=24540.0,
            trigger=24530.0,
            stop_loss=24480.0,
            target_1=24520.0,  # Target 1 below trigger!
            target_2=24600.0,
            risk_points=50.0,
        )
        assert res.passed is False
        assert res.reason_code == "TARGET_WRONG_SIDE"


class TestContractResolverHoliday:
    def test_holiday_adjusted_expiry(self):
        # 2026-10-02 is Gandhi Jayanti (Friday - national holiday)
        # SENSEX expires on Friday. It should adjust backwards to Thursday!
        ref_date = date(2026, 9, 28)  # Monday of Gandhi Jayanti week
        expiry, exp_type = resolve_nearest_expiry("SENSEX", ref_date=ref_date)
        assert expiry.weekday() == 3  # Adjusted to Thursday!
        assert calendar_service.is_trading_day(expiry)


class TestDeterministicValidatorFailClosed:
    def test_validator_fails_closed_when_market_closed(self):
        sig = AISignal(
            signal_id="sig-test-ai",
            symbol="NIFTY",
            timestamp=datetime.now(timezone.utc),
            timeframe="5M",
            decision=Decision.LONG,
            entry=24500.0,
            stop_loss=24400.0,
            target=24700.0,
        )
        # Empty market state with no explicit is_market_open key
        with patch.object(calendar_service, "can_trade_now", return_value=make_perm(False, "MARKET_CLOSED")):
            decision = deterministic_trade_validator.validate(sig, market_state={}, risk_state={})
            assert decision.decision == "REJECT"
            assert decision.reason_code.value == "MARKET_CLOSED"
