"""Dirty-state e2e: test rows/ghosts/missing -> sanitize -> /performance exact."""
from decimal import Decimal
from app.signals.fsm import SignalInstance


def _sig(sid, state, **kw):
    base = dict(underlying="NIFTY", strategy="BREAKOUT", direction="LONG_CALL",
                timeframe="5M", spot_price=Decimal("25000"),
                entry_min=Decimal("25045"), entry_max=Decimal("25055"),
                trigger=Decimal("25050"), stop_loss=Decimal("24980"),
                target_1=Decimal("25150"), target_2=Decimal("25250"),
                risk_points=Decimal("70"), risk_reward_t1=1.5,
                risk_reward_t2=3.0, confidence=80.0, fsm_state=state)
    base.update(kw)
    return SignalInstance(signal_id=sid, **base)


def test_dirty_state_sanitized_performance_exact(client, mock_market_open):
    from app.signals.fsm import signal_fsm
    from app.signals.signals_persistence import sanitize_persisted_signals
    signal_fsm._signals.clear()
    signal_fsm.register(_sig("SIG-E2E-WIN-01", "TARGET_2_HIT", realized_rr=3.0,
                             realized_rr_gross=3.0, outcome_status="WIN_T2",
                             terminal_outcome="FULL_WIN"))
    signal_fsm.register(_sig("SIG-E2E-LOSS-01", "STOP_LOSS_HIT", realized_rr=-1.0,
                             realized_rr_gross=-1.0, outcome_status="LOSS_SL",
                             terminal_outcome="STOP_LOSS_HIT"))
    # Dirt: test rows, ghosts, missing outcomes.
    signal_fsm.register(_sig("sig-test-ghost-01", "TARGET_2_HIT"))
    signal_fsm.register(_sig("TEST-DIRTY-02", "STOP_LOSS_HIT"))
    signal_fsm.register(_sig("SIG-E2E-MISS-01", "TARGET_2_HIT"))
    n = sanitize_persisted_signals()
    assert n >= 2  # test rows purged + missing repaired
    assert signal_fsm.get("sig-test-ghost-01") is None
    res = client.get("/api/v1/signals/performance")
    assert res.status_code == 200, res.text
    m = res.json()
    assert m["total_signals"] == 3
    assert m["completed_signals"] == 3
    assert m["winning_signals"] == 2
    assert m["losing_signals"] == 1
    assert m["win_rate_pct"] == 66.7
