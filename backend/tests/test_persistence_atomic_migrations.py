"""Regression tests for the phase-1 atomic_json leftovers.

Covers the two JSON writers migrated onto ``app.core.atomic_json``:
  * ``event_engine.signal_bridge`` shadow-record persistence,
  * ``institutional.drift`` degradation flag.

Pins payload shape, indentation, target paths and the error-swallowing
semantics (failures never raise).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone


def _event():
    from app.event_engine.models import CanonicalEvent

    return CanonicalEvent(
        canonical_event_id="RBI_MPC_20261009",
        title="RBI Monetary Policy Committee",
        event_type="CENTRAL_BANK",
        entity_id="RBI",
        event_timestamp=datetime(2026, 10, 9, 10, 0, tzinfo=timezone.utc),
        temporal_phase="ACTIVE",
    )


# ── event_engine.signal_bridge._save_shadow_records ────────────────────────


def test_shadow_records_write_round_trip(tmp_path):
    from app.event_engine.signal_bridge import EventSignalBridge

    path = tmp_path / "event_shadow_records.json"
    bridge = EventSignalBridge(persist_path=str(path))
    record = bridge.record_shadow_execution(
        signal_id="SIG-ATOMIC-1",
        event=_event(),
        underlying="BANKNIFTY",
        strategy="Breakout",
        direction="LONG_CALL",
        simulated_entry_price=52050.0,
    )

    raw = path.read_text(encoding="utf-8")
    assert "\n" not in raw  # legacy writer used json.dumps without indent
    payload = json.loads(raw)
    assert list(payload) == [record.shadow_signal_id]
    assert payload[record.shadow_signal_id]["execution_mode"] == "SHADOW_MODE"
    assert payload[record.shadow_signal_id]["shadow_status"] == "TRACKING"
    assert payload[record.shadow_signal_id]["canonical_event_id"] == "RBI_MPC_20261009"

    reloaded = EventSignalBridge(persist_path=str(path))
    assert [r.shadow_signal_id for r in reloaded.get_shadow_records()] == [record.shadow_signal_id]


def test_shadow_records_write_failure_is_swallowed(tmp_path):
    from app.event_engine.signal_bridge import EventSignalBridge

    missing_parent = tmp_path / "missing" / "event_shadow_records.json"
    bridge = EventSignalBridge(persist_path=str(missing_parent))
    bridge._save_shadow_records()  # must not raise (legacy swallowed + debug-logged)
    assert not missing_parent.exists()
    assert bridge._shadow_records == {}


# ── institutional.drift._write ─────────────────────────────────────────────


def test_drift_flag_write_preserves_payload_and_indent(tmp_path, monkeypatch):
    from app.institutional import drift

    flag = tmp_path / "data" / "institutional_degraded.flag"
    monkeypatch.setattr(drift, "FLAG", flag)
    payload = {
        "degraded": True,
        "reason": "psi-0.7-shift-1.234",
        "at": "2026-09-18T00:00:00+00:00",
    }

    drift._write(payload)

    raw = flag.read_text(encoding="utf-8")
    assert raw == json.dumps(payload, indent=2)
    assert json.loads(raw) == payload
    assert drift.is_degraded() is True


def test_drift_flag_write_failure_is_swallowed(tmp_path, monkeypatch):
    from app.institutional import drift

    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(drift, "FLAG", blocker / "institutional_degraded.flag")

    drift._write({"degraded": True, "reason": "x", "at": "y"})  # must not raise
