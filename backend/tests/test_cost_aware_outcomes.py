import pytest
from decimal import Decimal
import time
from app.signals.fsm import signal_fsm, SignalFSMManager, SignalInstance, compute_option_friction_r
from app.signals.outcome_tracker import SignalOutcomeTracker


def test_compute_option_friction_r():
    """Verify Indian F&O friction calculations (STT, GST, brokerage, slippage)."""
    friction_r, breakdown = compute_option_friction_r(
        entry_premium=100.0,
        exit_premium=150.0,
        lots=2,
        lot_size=65,
        risk_points_premium=25.0,
    )
    assert friction_r > 0.0
    assert breakdown["brokerage_inr"] == 40.0
    assert breakdown["stt_inr"] > 0.0  # STT charged on sell
    assert breakdown["gst_inr"] > 0.0  # 18% GST
    assert breakdown["slippage_cost_inr"] > 0.0
    assert breakdown["total_friction_inr"] > 40.0
    assert friction_r == breakdown["friction_r"]


def test_fsm_cost_aware_transitions():
    """Verify that transitions calculate gross R, net R, and correct terminal outcomes."""
    fsm = SignalFSMManager()
    
    # 1. Test TARGET_1_HIT then RUNNER_TIME_STOP_HIT
    sig = SignalInstance(
        signal_id="test-runner-win",
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("24800"),
        entry_min=Decimal("24800"),
        entry_max=Decimal("24810"),
        trigger=Decimal("24810"),
        stop_loss=Decimal("24785"),
        target_1=Decimal("24850"),
        target_2=Decimal("24890"),
        risk_points=Decimal("25"),
        risk_reward_t1=1.6,
        risk_reward_t2=3.2,
        confidence=0.85,
        lots=1,
    )
    fsm.register(sig)
    fsm.transition(sig.signal_id, "VALIDATED")
    fsm.transition(sig.signal_id, "ARMED")
    fsm.transition(sig.signal_id, "TRIGGERED", market_price=Decimal("24812"))
    fsm.transition(sig.signal_id, "CONFIRMED", market_price=Decimal("24815"))
    
    # Hit T1
    fsm.transition(sig.signal_id, "TARGET_1_HIT", market_price=Decimal("24850"))
    assert sig.terminal_outcome == "PARTIAL_WIN"
    assert sig.realized_rr_gross == 1.6
    assert sig.realized_rr_net is not None
    assert sig.realized_rr_net < sig.realized_rr_gross  # Net is discounted by friction
    assert sig.cost_breakdown_r is not None
    assert sig.breakeven_activated is True

    # Hit Runner Time Stop
    fsm.transition(sig.signal_id, "RUNNER_TIME_STOP_HIT", market_price=Decimal("24840"))
    assert sig.terminal_outcome == "PARTIAL_WIN"
    assert sig.outcome_status == "RUNNER_TIME_STOP"
    assert sig.realized_rr_gross == 1.6
    assert sig.realized_rr_net is not None


def test_outcome_tracker_runner_time_stop_counted_as_win():
    """Verify that RUNNER_TIME_STOP_HIT signals count as WINS in performance metrics."""
    signal_fsm._signals.clear()
    
    # Create 1 full win (T2)
    s1 = SignalInstance(
        signal_id="sig-win-t2",
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("24800"),
        entry_min=Decimal("24800"),
        entry_max=Decimal("24810"),
        trigger=Decimal("24810"),
        stop_loss=Decimal("24785"),
        target_1=Decimal("24850"),
        target_2=Decimal("24890"),
        risk_points=Decimal("25"),
        risk_reward_t1=1.6,
        risk_reward_t2=3.2,
        confidence=0.85,
        fsm_state="TARGET_2_HIT",
        outcome_status="WIN_T2",
        terminal_outcome="FULL_WIN",
        realized_rr=3.2,
        realized_rr_gross=3.2,
        realized_rr_net=3.05,
    )
    # Create 1 runner time stop (partial win)
    s2 = SignalInstance(
        signal_id="sig-runner-ts",
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("24800"),
        entry_min=Decimal("24800"),
        entry_max=Decimal("24810"),
        trigger=Decimal("24810"),
        stop_loss=Decimal("24785"),
        target_1=Decimal("24850"),
        target_2=Decimal("24890"),
        risk_points=Decimal("25"),
        risk_reward_t1=1.6,
        risk_reward_t2=3.2,
        confidence=0.85,
        fsm_state="RUNNER_TIME_STOP_HIT",
        outcome_status="RUNNER_TIME_STOP",
        terminal_outcome="PARTIAL_WIN",
        realized_rr=1.6,
        realized_rr_gross=1.6,
        realized_rr_net=1.48,
    )
    # Create 1 stop loss hit (loss)
    s3 = SignalInstance(
        signal_id="sig-sl",
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("24800"),
        entry_min=Decimal("24800"),
        entry_max=Decimal("24810"),
        trigger=Decimal("24810"),
        stop_loss=Decimal("24785"),
        target_1=Decimal("24850"),
        target_2=Decimal("24890"),
        risk_points=Decimal("25"),
        risk_reward_t1=1.6,
        risk_reward_t2=3.2,
        confidence=0.85,
        fsm_state="STOP_LOSS_HIT",
        outcome_status="LOSS_SL",
        terminal_outcome="STOP_LOSS_HIT",
        realized_rr=-1.0,
        realized_rr_gross=-1.0,
        realized_rr_net=-1.12,
    )
    
    signal_fsm.register(s1)
    signal_fsm.register(s2)
    signal_fsm.register(s3)
    
    tracker = SignalOutcomeTracker()
    metrics = tracker.get_performance_metrics()
    
    # 2 wins (1 T2 + 1 Runner TS) out of 3 completed trades = 66.7%
    assert metrics.completed_signals == 3
    assert metrics.winning_signals == 2
    assert metrics.losing_signals == 1
    assert metrics.win_rate_pct == 66.7
    assert metrics.runner_time_stop_hits == 1
    assert metrics.target_2_hits == 1
    assert metrics.stop_loss_hits == 1
    assert metrics.profit_factor > 1.0
    assert metrics.realized_rr_net_sum > 0  # Reconciles net R sum
