"""
Unit & Integration Test for Signal Persistence Resilience
Validates that FSM signals, audit trade records, and reconciliations are preserved
across container restarts and redeployments, eliminating 'starting from zero'.
"""
import os
from decimal import Decimal
from pathlib import Path
import pytest

from app.signals.fsm import signal_fsm, SignalInstance
from app.signals.audit_ledger import signal_audit_ledger
from app.signals.signals_persistence import (
    save_signals_state_local,
    restore_signals_state_local,
    restore_signals_from_db,
    SIGNALS_STATE_FILE,
)


@pytest.mark.asyncio
async def test_signals_persistence_resilience():
    # 1. Register test signal
    sig = SignalInstance(
        signal_id="SIG-TEST-PERSIST-01",
        underlying="NIFTY",
        strategy="VWAP_SCALP",
        direction="LONG_CALL",
        timeframe="1M",
        spot_price=Decimal("24800"),
        entry_min=Decimal("24800"),
        entry_max=Decimal("24810"),
        trigger=Decimal("24805"),
        stop_loss=Decimal("24780"),
        target_1=Decimal("24850"),
        target_2=Decimal("24900"),
        risk_points=Decimal("25"),
        risk_reward_t1=1.8,
        risk_reward_t2=3.8,
        confidence=85.0,
        is_scalp=True,
        signal_type="SCALP",
        time_stop_seconds=180,
        runner_ttl_seconds=300,
        fsm_state="CONFIRMED",
    )
    signal_fsm.register(sig)

    # 2. Record trade in audit ledger
    signal_audit_ledger.record_signal_created(
        signal_id=sig.signal_id,
        underlying=sig.underlying,
        strategy=sig.strategy,
        direction=sig.direction,
        timeframe=sig.timeframe,
        spot_price=float(sig.spot_price),
        trigger=float(sig.trigger),
        stop_loss=float(sig.stop_loss),
        target_1=float(sig.target_1),
        target_2=float(sig.target_2),
        confidence=float(sig.confidence),
        status="CONFIRMED",
    )

    # 3. Explicitly verify save_signals_state_local works and creates the file
    saved = save_signals_state_local()
    assert saved is True
    assert SIGNALS_STATE_FILE.exists()

    # 4. SIMULATE REDEPLOYMENT / RESTART (Memory wiped clean)
    signal_fsm._signals.clear()
    signal_audit_ledger._trades.clear()
    assert len(signal_fsm._signals) == 0
    assert len(signal_audit_ledger._trades) == 0

    # 5. Call restore_signals_from_db() as done on startup in main.py
    restored_count = await restore_signals_from_db()
    assert restored_count > 0

    # 6. Verify signal is fully restored with v6 fields intact
    restored_sig = signal_fsm.get("SIG-TEST-PERSIST-01")
    assert restored_sig is not None
    assert restored_sig.underlying == "NIFTY"
    assert restored_sig.strategy == "VWAP_SCALP"
    assert restored_sig.is_scalp is True
    assert restored_sig.fsm_state == "CONFIRMED"
    assert restored_sig.risk_reward_t1 == 1.8

    # 7. Verify audit trade is fully restored
    restored_trade = signal_audit_ledger.get("SIG-TEST-PERSIST-01")
    assert restored_trade is not None
    assert restored_trade.underlying == "NIFTY"
    assert restored_trade.status == "CONFIRMED"

    # Cleanup test signal
    signal_fsm.delete("SIG-TEST-PERSIST-01")
    signal_audit_ledger.delete_trade("SIG-TEST-PERSIST-01")
