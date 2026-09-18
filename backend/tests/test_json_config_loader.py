"""Tests for the single JSON config loader (app/core/json_config.py) and the
failure posture of every migrated caller.

Covers:
  - canonical path-search precedence,
  - required=True raises with a clear message,
  - required=False logs a warning and returns the default,
  - caching + copy-on-read mutation isolation,
  - per-caller posture: confluence fail-closed, signal_fusion non-fatal but
    loud, risk_engine/scoring_service non-fatal built-in defaults.
"""
from __future__ import annotations

import importlib
import json
from decimal import Decimal
from pathlib import Path

import pytest
from structlog.testing import capture_logs

from app.core.json_config import (
    DEFAULT_SEARCH_DIRS,
    JSONConfigError,
    clear_json_config_cache,
    load_json_config,
)


@pytest.fixture(autouse=True)
def _clean_config_cache():
    clear_json_config_cache()
    yield
    clear_json_config_cache()


# ── path search ──────────────────────────────────────────────────────

def test_cwd_search_prefers_backend_config_over_config(tmp_path, monkeypatch):
    name = "loader_precedence_probe.json"
    (tmp_path / "backend" / "config").mkdir(parents=True)
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "config" / name).write_text(json.dumps({"winner": "cwd-config"}), encoding="utf-8")
    (tmp_path / "backend" / "config" / name).write_text(
        json.dumps({"winner": "cwd-backend-config"}), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    assert load_json_config(name)["winner"] == "cwd-backend-config"


def test_cwd_search_falls_back_to_config_dir(tmp_path, monkeypatch):
    name = "loader_config_dir_probe.json"
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "config" / name).write_text(json.dumps({"winner": "cwd-config"}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert load_json_config(name)["winner"] == "cwd-config"


def test_default_search_dirs_order():
    # 1) backend/config (module-relative, canonical first), 2) repo/config,
    # 3) cwd backend/config, 4) cwd config — the historical winning order.
    backend_root = Path(__file__).resolve().parents[1]
    repo_root = Path(__file__).resolve().parents[2]
    assert DEFAULT_SEARCH_DIRS[0] == backend_root / "config"
    assert DEFAULT_SEARCH_DIRS[1] == repo_root / "config"
    assert DEFAULT_SEARCH_DIRS[2] == Path("backend") / "config"
    assert DEFAULT_SEARCH_DIRS[3] == Path("config")


def test_explicit_search_dir_precedes_canonical(tmp_path):
    name = "loader_override_probe.json"
    custom_dir = tmp_path / "custom"
    custom_dir.mkdir()
    (custom_dir / name).write_text(json.dumps({"winner": "custom-dir"}), encoding="utf-8")

    assert load_json_config(name, search_paths=[custom_dir])["winner"] == "custom-dir"


def test_explicit_search_file_path_precedes_canonical(tmp_path):
    custom_file = tmp_path / "my_weights.json"
    custom_file.write_text(json.dumps({"winner": "custom-file"}), encoding="utf-8")

    assert load_json_config("scoring_weights.json", search_paths=[custom_file])["winner"] == "custom-file"


def test_default_search_loads_repo_config_with_logged_path():
    with capture_logs() as logs:
        data = load_json_config("scoring_weights.json")

    assert data["thresholds"]["armed"] == 78.0
    loaded = [e for e in logs if e["event"] == "json_config_loaded"]
    assert loaded and loaded[0]["path"].endswith("scoring_weights.json")


# ── required / fallback policy ───────────────────────────────────────

def test_required_true_raises_with_clear_message(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(JSONConfigError, match=r"absent_probe\.json") as exc:
        load_json_config("absent_probe.json", required=True)

    message = str(exc.value)
    assert "required=True" in message
    assert "searched" in message
    # Legacy callers catch RuntimeError — JSONConfigError must remain one.
    assert isinstance(exc.value, RuntimeError)


def test_required_false_logs_warning_and_returns_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with capture_logs() as logs:
        data = load_json_config("absent_probe.json", required=False, default={"fallback": True})

    assert data == {"fallback": True}
    fallbacks = [e for e in logs if e["event"] == "json_config_fallback_default"]
    assert len(fallbacks) == 1
    assert fallbacks[0]["log_level"] == "warning"
    assert fallbacks[0]["name"] == "absent_probe.json"
    assert any("absent_probe.json" in p for p in fallbacks[0]["searched"])

    # Default is deep-copied: mutating the result cannot poison later calls.
    data["fallback"] = False
    data["extra"] = 1
    with capture_logs():
        again = load_json_config("absent_probe.json", required=False, default={"fallback": True})
    assert again == {"fallback": True}


def test_corrupt_json_raises_when_required_and_falls_back_otherwise(tmp_path):
    bad = tmp_path / "corrupt_probe.json"
    bad.write_text("{not json", encoding="utf-8")

    with pytest.raises(JSONConfigError, match="corrupt_probe.json"):
        load_json_config("corrupt_probe.json", required=True, search_paths=[bad])

    with capture_logs() as logs:
        assert load_json_config("corrupt_probe.json", required=False, search_paths=[bad], default={}) == {}
    assert any(e["event"] == "json_config_read_error" for e in logs)


def test_non_mapping_root_is_rejected(tmp_path):
    bad = tmp_path / "list_probe.json"
    bad.write_text("[]", encoding="utf-8")

    with pytest.raises(JSONConfigError, match="list_probe.json"):
        load_json_config("list_probe.json", required=True, search_paths=[bad])

    with capture_logs() as logs:
        assert load_json_config("list_probe.json", required=False, search_paths=[bad], default={}) == {}
    assert any(e["event"] == "json_config_invalid_root" for e in logs)


# ── caching + mutation isolation ─────────────────────────────────────

def test_cache_serves_deep_copy_and_survives_file_removal(tmp_path):
    path = tmp_path / "cache_probe.json"
    path.write_text(json.dumps({"v": 1}), encoding="utf-8")

    first = load_json_config("cache_probe.json", search_paths=[path])
    first["v"] = 999
    first["extra"] = True

    path.unlink()
    second = load_json_config("cache_probe.json", search_paths=[path])
    assert second == {"v": 1}
    assert second is not first


def test_cache_false_rereads_disk(tmp_path):
    path = tmp_path / "uncached_probe.json"
    path.write_text(json.dumps({"v": 1}), encoding="utf-8")
    assert load_json_config("uncached_probe.json", search_paths=[path], cache=False)["v"] == 1

    path.write_text(json.dumps({"v": 2}), encoding="utf-8")
    assert load_json_config("uncached_probe.json", search_paths=[path], cache=False)["v"] == 2


def test_cache_true_does_not_reread_disk(tmp_path):
    path = tmp_path / "cached_probe.json"
    path.write_text(json.dumps({"v": 1}), encoding="utf-8")
    assert load_json_config("cached_probe.json", search_paths=[path])["v"] == 1

    path.write_text(json.dumps({"v": 2}), encoding="utf-8")
    assert load_json_config("cached_probe.json", search_paths=[path])["v"] == 1


# ── migrated caller postures ─────────────────────────────────────────

def test_confluence_fail_closed_without_thresholds():
    confluence = importlib.import_module("app.signals.confluence")

    for bad in ({}, {"thresholds": {}}, {"weights_fraction": {"technical": 0.4}}):
        with pytest.raises(RuntimeError, match="fail-closed startup"):
            confluence._validate_confluence_config(bad)

    validated = confluence._validate_confluence_config({"thresholds": {"armed": 78.0}})
    assert validated["thresholds"]["armed"] == 78.0


def test_confluence_loader_required_raises_when_file_missing(tmp_path, monkeypatch):
    import app.core.json_config as json_config

    confluence = importlib.import_module("app.signals.confluence")
    monkeypatch.setattr(json_config, "DEFAULT_SEARCH_DIRS", (tmp_path / "nowhere",))
    clear_json_config_cache()

    with pytest.raises(RuntimeError, match="scoring_weights.json"):
        confluence._load_confluence_config()


def test_signal_fusion_fallback_is_non_fatal_but_logged(tmp_path, monkeypatch):
    import app.core.json_config as json_config

    fusion = importlib.import_module("app.algo.signal_fusion")
    monkeypatch.setattr(json_config, "DEFAULT_SEARCH_DIRS", (tmp_path / "nowhere",))
    clear_json_config_cache()

    with capture_logs() as logs:
        raw = fusion._load_scoring_config()

    assert raw == {}
    fallbacks = [e for e in logs if e["event"] == "json_config_fallback_default"]
    assert fallbacks and fallbacks[0]["log_level"] == "warning"
    assert fallbacks[0]["name"] == "scoring_weights.json"

    weights = fusion._load_scoring_weights_percent(raw)
    assert weights["technical"] == Decimal("40")
    assert weights["mtf"] == Decimal("20")
    assert weights["fno"] == Decimal("15")
    assert weights["regime"] == Decimal("10")
    assert weights["ai"] == Decimal("10")
    assert weights["event_risk"] == Decimal("5")
    assert "ml_max" not in weights


def test_signal_fusion_uses_file_weights_and_thresholds():
    fusion = importlib.import_module("app.algo.signal_fusion")

    assert fusion.WEIGHTS_VERSION == 2
    assert fusion.ARMED_THRESHOLD == Decimal("78.0")
    assert fusion.FUSION_LONG_THRESHOLD == Decimal("62")
    assert fusion.FUSION_SHORT_THRESHOLD == Decimal("38")
    assert fusion._load_scoring_weights_percent({"weights_percent": {"technical": 12.5, "ml_max": 9.0}}) == {
        "technical": Decimal("12.5")
    }


def test_risk_engine_missing_file_falls_back_to_builtin_defaults(tmp_path, monkeypatch):
    import app.core.json_config as json_config

    risk_engine = importlib.import_module("app.signals.risk_engine")
    monkeypatch.setattr(json_config, "DEFAULT_SEARCH_DIRS", (tmp_path / "nowhere",))
    clear_json_config_cache()

    with capture_logs() as logs:
        engine = risk_engine.CentralRiskEngine()

    # Fallback 1m_scalp TTL is 300s; the shipped risk_envelopes.json says 180s.
    rules = engine._config["envelopes"]["NIFTY"]["1m_scalp"]
    assert rules["trigger_ttl_seconds"] == 300
    assert engine._config["lot_sizes"]["NIFTY"] == 75
    assert any(e["event"] == "json_config_fallback_default" for e in logs)


def test_risk_engine_custom_config_file_takes_precedence(tmp_path):
    risk_engine = importlib.import_module("app.signals.risk_engine")
    custom = tmp_path / "custom_risk.json"
    custom.write_text(
        json.dumps({"version": 99, "envelopes": {}, "lot_sizes": {}, "options_scaling": {}}),
        encoding="utf-8",
    )

    engine = risk_engine.CentralRiskEngine(config_file=str(custom))
    assert engine._config["version"] == 99


def test_scoring_service_missing_file_falls_back_to_builtin_defaults(tmp_path, monkeypatch):
    import app.core.json_config as json_config

    scoring_module = importlib.import_module("app.event_engine.scoring_service")
    monkeypatch.setattr(json_config, "DEFAULT_SEARCH_DIRS", (tmp_path / "nowhere",))
    clear_json_config_cache()

    with capture_logs() as logs:
        service = scoring_module.EventScoringService()

    # Fallback maps UNKNOWN source authority to 50.0; the shipped file says 30.0.
    factors = service._config["importance_factors"]["source_authority"]
    assert factors["UNKNOWN"] == 50.0
    assert service._config["version"] == "v3.0.0"
    assert any(e["event"] == "json_config_fallback_default" for e in logs)


def test_scoring_service_custom_config_path_takes_precedence(tmp_path):
    scoring_module = importlib.import_module("app.event_engine.scoring_service")
    custom = tmp_path / "custom_event_scoring.json"
    custom.write_text(json.dumps({"version": "vTEST", "importance_weights": {}}), encoding="utf-8")

    service = scoring_module.EventScoringService(config_path=str(custom))
    assert service._config["version"] == "vTEST"
