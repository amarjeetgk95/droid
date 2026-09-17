"""
Phase 0 Characterization Test: Financial Parity Snapshots
Captures the exact current terminal outcome financial math from fsm.py L606-L699:
  - TARGET_1_HIT
  - TARGET_2_HIT
  - STOP_LOSS_HIT (normal and breakeven ratcheted)
  - TIME_STOP_HIT
  - RUNNER_TIME_STOP_HIT
  - EXPIRED / INVALIDATED
"""
from decimal import Decimal
import pytest
from app.signals.fsm import (
    SignalFSMManager,
    SignalInstance,
    compute_option_friction_r,
)


def _create_confirmed_signal(breakeven_activated: bool = False) -> SignalInstance:
    sig = SignalInstance(
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("24000.0"),
        entry_min=Decimal("24010.0"),
        entry_max=Decimal("24020.0"),
        trigger=Decimal("24015.0"),
        stop_loss=Decimal("23950.0"),
        target_1=Decimal("24100.0"),
        target_2=Decimal("24180.0"),
        risk_points=Decimal("65.0"),
        risk_reward_t1=1.3077,
        risk_reward_t2=2.5385,
        confidence=82.0,
        lots=2,
        quantity=130,
        actual_fill_price=Decimal("120.0"),
        fsm_state="CONFIRMED",
        breakeven_activated=breakeven_activated,
        option_contract={
            "broker_symbol": "NSE:NIFTY26SEP24000CE",
            "strike": 24000,
            "option_type": "CE",
            "dte": 3.0,
            "lot_size": 65,
        },
    )
    return sig


def _seed_exit_mark(price: float) -> None:
    """Publish the real chain mark the exit leg prices from.

    Friction is premium-vs-premium and fail-closed: without a broker mark for
    the exact contract the FSM records no net-R at all (cost_breakdown_r=None).
    The parity assertions derive expected_net from the breakdown itself, so
    any positive mark keeps them self-consistent — the scenario price just
    keeps the premium direction honest (wins above the 120 fill, losses below).
    """
    from tests.conftest import seed_chain_mark

    seed_chain_mark("NSE:NIFTY26SEP24000CE", price, underlying="NIFTY", strike=24000.0, option_type="CE")


def test_target_1_hit_financial_parity():
    fsm = SignalFSMManager()
    sig = _create_confirmed_signal()
    fsm._signals[sig.signal_id] = sig

    market_price = Decimal("24105.0")
    _seed_exit_mark(150.0)
    ok, err = fsm.transition(sig.signal_id, "TARGET_1_HIT", market_price=market_price)
    assert ok is True

    assert sig.fsm_state == "TARGET_1_HIT"
    assert sig.t1_hit is True
    assert sig.outcome_status == "WIN_T1"
    assert sig.terminal_outcome == "PARTIAL_WIN"
    assert sig.realized_rr_gross == 1.3077
    assert sig.realized_rr == 1.3077
    assert sig.cost_breakdown_r is not None
    assert "total_friction_inr" in sig.cost_breakdown_r
    assert "friction_r" in sig.cost_breakdown_r
    expected_net = round(sig.realized_rr_gross - sig.cost_breakdown_r["friction_r"], 4)
    assert sig.realized_rr_net == expected_net
    assert sig.breakeven_activated is True


def test_target_2_hit_financial_parity():
    fsm = SignalFSMManager()
    sig = _create_confirmed_signal()
    # Transition to T1 first, then T2
    fsm._signals[sig.signal_id] = sig
    _seed_exit_mark(150.0)
    fsm.transition(sig.signal_id, "TARGET_1_HIT", market_price=Decimal("24105.0"))

    market_price = Decimal("24185.0")
    _seed_exit_mark(190.0)
    ok, err = fsm.transition(sig.signal_id, "TARGET_2_HIT", market_price=market_price)
    assert ok is True

    assert sig.fsm_state == "TARGET_2_HIT"
    assert sig.t2_hit is True
    assert sig.outcome_status == "WIN_T2"
    assert sig.terminal_outcome == "FULL_WIN"
    assert sig.realized_rr_gross == 2.5385
    expected_net = round(sig.realized_rr_gross - sig.cost_breakdown_r["friction_r"], 4)
    assert sig.realized_rr_net == expected_net


def test_stop_loss_hit_standard_financial_parity():
    fsm = SignalFSMManager()
    sig = _create_confirmed_signal(breakeven_activated=False)
    fsm._signals[sig.signal_id] = sig

    market_price = Decimal("23945.0")
    _seed_exit_mark(85.0)
    ok, err = fsm.transition(sig.signal_id, "STOP_LOSS_HIT", market_price=market_price)
    assert ok is True

    assert sig.fsm_state == "STOP_LOSS_HIT"
    assert sig.outcome_status == "LOSS_SL"
    assert sig.terminal_outcome == "STOP_LOSS_HIT"
    assert sig.realized_rr_gross == -1.0
    expected_net = round(-1.0 - sig.cost_breakdown_r["friction_r"], 4)
    assert sig.realized_rr_net == expected_net


def test_stop_loss_hit_breakeven_ratcheted_financial_parity():
    fsm = SignalFSMManager()
    sig = _create_confirmed_signal(breakeven_activated=True)
    fsm._signals[sig.signal_id] = sig

    market_price = Decimal("24010.0")
    _seed_exit_mark(115.0)
    ok, err = fsm.transition(sig.signal_id, "STOP_LOSS_HIT", market_price=market_price)
    assert ok is True

    assert sig.fsm_state == "STOP_LOSS_HIT"
    assert sig.outcome_status == "LOSS_SL"
    assert sig.terminal_outcome == "BREAKEVEN"
    assert sig.realized_rr_gross == 0.0
    expected_net = round(0.0 - sig.cost_breakdown_r["friction_r"], 4)
    assert sig.realized_rr_net == expected_net


def test_time_stop_hit_financial_parity():
    fsm = SignalFSMManager()
    sig = _create_confirmed_signal()
    fsm._signals[sig.signal_id] = sig

    market_price = Decimal("24030.0")
    _seed_exit_mark(123.0)
    ok, err = fsm.transition(sig.signal_id, "TIME_STOP_HIT", market_price=market_price)
    assert ok is True

    assert sig.fsm_state == "TIME_STOP_HIT"
    assert sig.outcome_status == "TIME_STOP"
    assert sig.terminal_outcome == "TIME_STOP_LOSS"
    assert sig.realized_rr_gross == 0.0
    expected_net = round(0.0 - sig.cost_breakdown_r["friction_r"], 4)
    assert sig.realized_rr_net == expected_net


def test_runner_time_stop_hit_financial_parity():
    fsm = SignalFSMManager()
    sig = _create_confirmed_signal()
    fsm._signals[sig.signal_id] = sig
    _seed_exit_mark(150.0)
    fsm.transition(sig.signal_id, "TARGET_1_HIT", market_price=Decimal("24105.0"))

    market_price = Decimal("24140.0")
    _seed_exit_mark(170.0)
    ok, err = fsm.transition(sig.signal_id, "RUNNER_TIME_STOP_HIT", market_price=market_price)
    assert ok is True

    assert sig.fsm_state == "RUNNER_TIME_STOP_HIT"
    assert sig.outcome_status == "RUNNER_TIME_STOP"
    assert sig.terminal_outcome == "PARTIAL_WIN"
    assert sig.realized_rr_gross == 1.3077
    expected_net = round(sig.realized_rr_gross - sig.cost_breakdown_r["friction_r"], 4)
    assert sig.realized_rr_net == expected_net


def test_friction_calculation_direct():
    friction_r, breakdown = compute_option_friction_r(
        entry_premium=100.0,
        exit_premium=150.0,
        lots=1,
        lot_size=65,
        risk_points_premium=20.0,
    )
    assert friction_r > 0
    assert "brokerage_inr" in breakdown
    assert breakdown["brokerage_inr"] == 40.0
    assert breakdown["friction_r"] == friction_r
