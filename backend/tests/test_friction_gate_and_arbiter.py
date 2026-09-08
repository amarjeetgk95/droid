"""
Unit & Integration Tests for Friction Gate, Cross-Desk Arbiter, PIT Validator, and DSR (§27, §31, §34, §42).
"""
from decimal import Decimal
import pytest
from pydantic import BaseModel

from app.signals.strategies.base import SignalCandidate
from app.signals.risk.friction_gate import friction_gate
from app.signals.risk.cross_desk_arbiter import cross_desk_arbiter
from app.signals.validation.pit_validator import pit_validator
from app.signals.validation.multiple_testing import calculate_deflated_sharpe_ratio


class MockTrade(BaseModel):
    signal_id: str
    underlying: str
    direction: str
    is_scalp: bool = False
    timeframe: str = "5M"
    fsm_state: str = "CONFIRMED"
    r_multiple: float = 0.0


class TestFrictionGate:
    def test_healthy_edge_accepted(self):
        # Target = 60 pts on NIFTY, Risk = 25 pts (large target easily covers ~2-3 pts friction)
        cand = SignalCandidate(
            underlying="NIFTY",
            strategy="VOLATILITY_BREAKOUT",
            direction="LONG_CALL",
            timeframe="5M",
            spot_price=Decimal("25000.0"),
            entry_min=Decimal("25000.0"),
            entry_max=Decimal("25010.0"),
            trigger=Decimal("25010.0"),
            stop_loss=Decimal("24985.0"),
            target_1=Decimal("25070.0"), # 60 pts target
            target_2=Decimal("25120.0"),
            risk_points=Decimal("25.0"),
            risk_reward_t1=2.4,
            risk_reward_t2=4.4,
        )
        res = friction_gate.evaluate(cand)
        assert res.passed is True
        assert res.expected_net_edge_pts > 15.0
        assert res.net_reward_risk_ratio >= 1.10
        assert res.rejection_reason is None

    def test_tiny_scalp_target_rejected_by_friction(self):
        # Target = 2 pts on NIFTY (spread + fees will consume 100% of target)
        cand = SignalCandidate(
            underlying="NIFTY",
            strategy="MICRO_MOMENTUM",
            direction="LONG_CALL",
            timeframe="1M",
            is_scalp=True,
            spot_price=Decimal("25000.0"),
            entry_min=Decimal("25000.0"),
            entry_max=Decimal("25001.0"),
            trigger=Decimal("25001.0"),
            stop_loss=Decimal("24996.0"),
            target_1=Decimal("25003.0"), # Only 2 pts target!
            target_2=Decimal("25005.0"),
            risk_points=Decimal("5.0"),
            risk_reward_t1=0.4,
            risk_reward_t2=0.8,
        )
        res = friction_gate.evaluate(cand)
        assert res.passed is False
        assert "REJECT" in (res.rejection_reason or "")


class TestCrossDeskArbiter:
    def test_flat_allows_scalp(self):
        res = cross_desk_arbiter.arbitrate(
            candidate_is_scalp=True,
            candidate_underlying="NIFTY",
            candidate_direction="LONG_CALL",
            active_trades=[],
        )
        assert res.passed is True
        assert res.action == "ALLOW"

    def test_intraday_in_drawdown_suppresses_opposing_scalp(self):
        # Intraday LONG is down -0.6R -> Opposing SHORT scalp must be hard suppressed
        active = [
            MockTrade(
                signal_id="INT-001",
                underlying="NIFTY",
                direction="LONG_CALL",
                is_scalp=False,
                timeframe="5M",
                r_multiple=-0.60,
            )
        ]
        res = cross_desk_arbiter.arbitrate(
            candidate_is_scalp=True,
            candidate_underlying="NIFTY",
            candidate_direction="LONG_PUT",  # Opposing direction!
            active_trades=active,
        )
        assert res.passed is False
        assert res.action == "SUPPRESS"
        assert "REJECT_CROSS_DESK_CONFLICT" in (res.reason or "")

    def test_intraday_in_profit_issues_harvest_warning_for_opposing_scalp(self):
        # Intraday LONG is up +1.8R -> Opposing SHORT scalp triggers HARVEST_WARNING
        active = [
            MockTrade(
                signal_id="INT-002",
                underlying="NIFTY",
                direction="LONG_CALL",
                is_scalp=False,
                timeframe="5M",
                r_multiple=1.80,
            )
        ]
        res = cross_desk_arbiter.arbitrate(
            candidate_is_scalp=True,
            candidate_underlying="NIFTY",
            candidate_direction="LONG_PUT",
            active_trades=active,
        )
        assert res.passed is True
        assert res.action == "HARVEST_WARNING"
        assert res.suggested_intraday_action == "TIGHTEN_STOP_TO_BE"
        assert res.sizing_multiplier == 0.50


class TestPointInTimeValidator:
    def test_clean_history_passes_pit(self):
        now_ms = 1700000000000
        candles = [
            {"timestamp": now_ms - 120000},
            {"timestamp": now_ms - 60000},
            {"timestamp": now_ms},
        ]
        res = pit_validator.validate_timeline(now_ms, candles, quote_timestamp_ms=now_ms)
        assert res.passed is True
        assert res.leakage_detected is False

    def test_future_candle_fails_pit(self):
        now_ms = 1700000000000
        candles = [
            {"timestamp": now_ms - 60000},
            {"timestamp": now_ms + 60000},  # Future candle!
        ]
        res = pit_validator.validate_timeline(now_ms, candles)
        assert res.passed is False
        assert res.leakage_detected is True
        assert "LOOKAHEAD_VIOLATION" in res.violations[0]


class TestMultipleTestingDSR:
    def test_single_trial_retains_sharpe(self):
        res = calculate_deflated_sharpe_ratio(
            observed_sharpe=2.0,
            num_trials=1,
            sample_length=252,
        )
        assert res.is_statistically_significant is True
        assert res.deflated_sharpe_ratio >= 0.95

    def test_extreme_trials_deflates_spurious_sharpe(self):
        # When 10,000 trials were tested, a modest Sharpe of 0.40 is deflated below significance
        res = calculate_deflated_sharpe_ratio(
            observed_sharpe=0.40,
            num_trials=10000,
            sample_length=100,
        )
        assert res.deflated_sharpe_ratio < 0.95
        assert res.is_statistically_significant is False
        assert res.expected_maximum_sharpe > 0
