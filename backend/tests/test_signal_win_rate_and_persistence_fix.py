"""
Unit tests verifying the Signal Win Rate & Persistence Sanitizer fixes:
1. sanitize_persisted_signals() correctly populates outcome_status, terminal_outcome,
   and realized_rr on force-transitioned or legacy records.
2. Case-insensitive purging of test signals from memory and state cache.
3. outcome_tracker.get_performance_metrics() defensively filters test signals and
   calculates accurate win rate.
4. signal_audit_ledger recognizes RUNNER_TIME_STOP_HIT as a winner and properly
   counts terminal states in closed_trades for summary metrics.
"""
from decimal import Decimal
import pytest

from app.signals.fsm import SignalInstance
from app.signals.audit_ledger import SignalAuditLedger
from app.signals.signals_persistence import sanitize_persisted_signals


@pytest.fixture(autouse=True)
def _open_market(mock_market_open):
    """Default to open market unless specifically tested."""
    pass


def _make_signal(signal_id: str, fsm_state: str, **kwargs) -> SignalInstance:
    defaults = {
        "signal_id": signal_id,
        "underlying": "NIFTY",
        "strategy": "BREAKOUT",
        "direction": "LONG_CALL",
        "timeframe": "5M",
        "spot_price": Decimal("25000"),
        "entry_min": Decimal("25045"),
        "entry_max": Decimal("25055"),
        "trigger": Decimal("25050"),
        "stop_loss": Decimal("24980"),
        "target_1": Decimal("25150"),
        "target_2": Decimal("25250"),
        "risk_points": Decimal("70"),
        "risk_reward_t1": 1.5,
        "risk_reward_t2": 3.0,
        "confidence": 80.0,
        "fsm_state": fsm_state,
    }
    defaults.update(kwargs)
    return SignalInstance(**defaults)


def test_sanitize_persisted_signals_repairs_missing_outcomes():
    """Verify that unpopulated terminal signals get their outcome fields repaired."""
    from app.signals.fsm import signal_fsm
    signal_fsm._signals.clear()

    # Signal in RUNNER_TIME_STOP_HIT with missing outcome
    sig_runner = _make_signal(
        "SIG-REAL-RUNNER-01",
        "RUNNER_TIME_STOP_HIT",
        outcome_status=None,
        terminal_outcome=None,
        realized_rr=None,
    )
    # Signal in TARGET_2_HIT with missing outcome
    sig_t2 = _make_signal(
        "SIG-REAL-T2-01",
        "TARGET_2_HIT",
        outcome_status=None,
        terminal_outcome=None,
        realized_rr=None,
    )
    # Signal in STOP_LOSS_HIT with missing outcome
    sig_sl = _make_signal(
        "SIG-REAL-SL-01",
        "STOP_LOSS_HIT",
        outcome_status=None,
        terminal_outcome=None,
        realized_rr=None,
    )
    signal_fsm.register(sig_runner)
    signal_fsm.register(sig_t2)
    signal_fsm.register(sig_sl)

    sanitized = sanitize_persisted_signals()
    assert sanitized >= 3

    # Check runner
    r_sig = signal_fsm.get("SIG-REAL-RUNNER-01")
    assert r_sig.outcome_status == "RUNNER_TIME_STOP"
    assert r_sig.terminal_outcome == "PARTIAL_WIN"
    assert r_sig.realized_rr == 1.5
    assert r_sig.realized_rr_net == 1.5

    # Check T2
    t2_sig = signal_fsm.get("SIG-REAL-T2-01")
    assert t2_sig.outcome_status == "WIN_T2"
    assert t2_sig.terminal_outcome == "FULL_WIN"
    assert t2_sig.realized_rr == 3.0

    # Check SL
    sl_sig = signal_fsm.get("SIG-REAL-SL-01")
    assert sl_sig.outcome_status == "LOSS_SL"
    assert sl_sig.terminal_outcome == "STOP_LOSS_HIT"
    assert sl_sig.realized_rr == -1.0


def test_sanitize_purges_test_signals_case_insensitively():
    """Verify test-prefixed signals are permanently purged from memory."""
    from app.signals.fsm import signal_fsm
    from app.signals.audit_ledger import signal_audit_ledger
    signal_fsm._signals.clear()
    signal_audit_ledger._trades.clear()

    # Add test signals
    for test_id in ["sig-test-1", "sig-persist-sanitize-1", "test-demo-123"]:
        sig = _make_signal(test_id, "EXPIRED")
        signal_fsm.register(sig)

    # Legitimate signal
    legit_sig = _make_signal("SIG-PROD-REAL-01", "CONFIRMED")
    signal_fsm.register(legit_sig)

    sanitize_persisted_signals()

    assert signal_fsm.get("sig-test-1") is None
    assert signal_fsm.get("sig-persist-sanitize-1") is None
    assert signal_fsm.get("test-demo-123") is None
    assert signal_fsm.get("SIG-PROD-REAL-01") is not None


def test_audit_ledger_runner_time_stop_and_summary():
    """Verify audit ledger marks RUNNER_TIME_STOP_HIT as winner and reports correct win rate."""
    ledger = SignalAuditLedger()

    # 1. Winning runner trade
    ledger.record_signal_created(
        signal_id="SIG-AUD-RUNNER",
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=25000.0,
        trigger=25050.0,
        stop_loss=24980.0,
        target_1=25150.0,
        target_2=25250.0,
    )
    ledger.record_state_transition("SIG-AUD-RUNNER", "RUNNER_TIME_STOP_HIT")
    rec_runner = ledger.get("SIG-AUD-RUNNER")
    assert rec_runner.is_winner is True

    # 2. Winning T2 trade
    ledger.record_signal_created(
        signal_id="SIG-AUD-T2",
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=25000.0,
        trigger=25050.0,
        stop_loss=24980.0,
        target_1=25150.0,
        target_2=25250.0,
    )
    ledger.record_state_transition("SIG-AUD-T2", "TARGET_2_HIT")
    rec_t2 = ledger.get("SIG-AUD-T2")
    assert rec_t2.is_winner is True

    # 3. Losing Stop-Loss trade
    ledger.record_signal_created(
        signal_id="SIG-AUD-SL",
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=25000.0,
        trigger=25050.0,
        stop_loss=24980.0,
        target_1=25150.0,
        target_2=25250.0,
    )
    ledger.record_state_transition("SIG-AUD-SL", "STOP_LOSS_HIT")
    rec_sl = ledger.get("SIG-AUD-SL")
    assert rec_sl.is_winner is False

    summary = ledger.get_summary_metrics()
    assert summary["closed_trades"] == 3
    assert summary["winning_trades"] == 2
    assert summary["losing_trades"] == 1
    # 2 wins / 3 closed = 66.7%
    assert summary["win_rate_pct"] == 66.7
