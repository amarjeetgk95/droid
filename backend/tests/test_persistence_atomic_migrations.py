"""Regression tests for the phase-1 atomic_json leftovers.

Covers the three JSON writers migrated onto ``app.core.atomic_json``:
  * ``event_engine.signal_bridge`` shadow-record persistence,
  * ``institutional.drift`` degradation flag,
  * ``swing.persistence`` legacy v1 backup + reset.

Pins payload shape, indentation, target paths and the legacy error-swallowing
semantics (failures never raise; backup failure does not block the reset;
reset failure still returns the legacy-safe fallback dict).
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


# ── swing.persistence legacy v1 migration ──────────────────────────────────


def test_legacy_swing_state_migration_writes_backup_and_reset(tmp_path, monkeypatch):
    from app.swing import persistence

    monkeypatch.chdir(tmp_path)
    state_file = tmp_path / "swing_state.json"
    legacy = {"schema_version": 1, "positions": [{"symbol": "NIFTY", "qty": 75}]}
    state_file.write_text(json.dumps(legacy), encoding="utf-8")
    monkeypatch.setattr(persistence, "SWING_STATE_FILE", state_file)

    state = persistence.load_swing_state()

    assert state["schema_version"] == persistence.SWING_STATE_SCHEMA_VERSION
    assert state["setups"] == []
    assert state["open_positions"] == []
    assert state["closed_positions"] == []
    assert state["regime"] is None
    assert isinstance(state["updated_at_utc"], int)

    on_disk = json.loads(state_file.read_text(encoding="utf-8"))
    assert on_disk["schema_version"] == 2
    assert on_disk["setups"] == []

    backups = sorted(tmp_path.glob("swing_state_legacy_backup_*.json"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == json.dumps(legacy, indent=2)


def test_legacy_backup_failure_still_resets_state(tmp_path, monkeypatch):
    from app.swing import persistence

    monkeypatch.chdir(tmp_path)
    state_file = tmp_path / "swing_state.json"
    state_file.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    monkeypatch.setattr(persistence, "SWING_STATE_FILE", state_file)

    real = persistence.atomic_write_json
    calls = {"n": 0}

    def _fail_backup_only(path, payload, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return False
        return real(path, payload, **kwargs)

    monkeypatch.setattr(persistence, "atomic_write_json", _fail_backup_only)

    state = persistence.load_swing_state()

    assert state["schema_version"] == 2
    assert isinstance(state["updated_at_utc"], int)
    assert json.loads(state_file.read_text(encoding="utf-8"))["schema_version"] == 2
    assert calls["n"] == 2  # backup attempted, reset still executed
    assert not list(tmp_path.glob("swing_state_legacy_backup_*.json"))


def test_legacy_reset_failure_returns_original_fallback(tmp_path, monkeypatch):
    from app.swing import persistence

    monkeypatch.chdir(tmp_path)
    state_file = tmp_path / "swing_state.json"
    state_file.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    monkeypatch.setattr(persistence, "SWING_STATE_FILE", state_file)
    monkeypatch.setattr(persistence, "atomic_write_json", lambda *a, **k: False)

    state = persistence.load_swing_state()

    # Pre-migration path: the reset write raised, the outer handler logged
    # load_swing_state_failed and returned the fallback (no updated_at_utc).
    assert state == {
        "schema_version": persistence.SWING_STATE_SCHEMA_VERSION,
        "setups": [],
        "open_positions": [],
        "closed_positions": [],
        "regime": None,
    }
    assert json.loads(state_file.read_text(encoding="utf-8")) == {"schema_version": 1}
