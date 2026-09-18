"""P1-2 contract tests for GET /api/v1/view/command (frozen CommandView v1).

Follows the existing dashboard-summary test pattern: bare TestClient (no
lifespan), caches cleared per test, and every heavy leg monkeypatched so the
suite never touches the network or the ambient provider.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.api import dashboard as dashboard_api
from app.api import health as health_api
from app.api import signals as signals_api
from app.api import view as view_api
from app.api.dashboard import DashboardSummary
from app.main import app

client = TestClient(app)

# ── Contract snapshot (literal) ──────────────────────────────────────────
EXPECTED_SECTIONS = {
    "market",
    "regime",
    "signals",
    "feed_health",
    "kill_switch",
    "ml",
    "risk_events",
}
ENVELOPE_KEYS = {"value", "updated_at", "freshness_s", "degraded", "version"}

FIXED_CARDS = [{"symbol": "NIFTY 50", "ltp": 24870.0, "status": "LIVE"}]
FIXED_BREADTH = {"advances": 30, "declines": 20, "status": "LIVE"}
FIXED_STATUS = {"session": "REGULAR", "status": "LIVE"}
FIXED_REGIME = {"regime_state": "TRENDING_UP"}
FIXED_OPTIONS = {"pcr_oi": 1.1, "available": True}
FIXED_ML = {"prob_up": 0.61}
FIXED_FII = {"fii_net_crores": -1200.0}

FIXED_GENERATED_AT = "2026-09-18T07:22:01+00:00"
FIXED_SIGNALS_PAYLOAD = {
    "signals": [{"signal_id": "sig-1", "underlying": "NIFTY"}],
    "count": 1,
    "data_quality": "LIVE",
    "degraded_underlyings": [],
    "errors": {},
    "timestamp_ms": 1758189721000,
}
FIXED_HEALTH_PAYLOAD = {
    "status": "ok",
    "elements": {"server": True, "central_feed": True},
    "timestamp": FIXED_GENERATED_AT,
}


@pytest.fixture(autouse=True)
def _clear_view_state():
    dashboard_api._summary_cache.clear()
    view_api._signals_cache.clear()
    view_api._section_versions.clear()
    yield
    dashboard_api._summary_cache.clear()
    view_api._signals_cache.clear()
    view_api._section_versions.clear()


def _fixed_summary(**overrides) -> DashboardSummary:
    base = dict(
        cards=FIXED_CARDS,
        breadth=FIXED_BREADTH,
        market_status=FIXED_STATUS,
        ml_prediction=FIXED_ML,
        fii_dii=FIXED_FII,
        regime_overview=FIXED_REGIME,
        options_analytics=FIXED_OPTIONS,
        errors={},
        degraded=False,
        generated_at=FIXED_GENERATED_AT,
    )
    base.update(overrides)
    return DashboardSummary(**base)


@pytest.fixture
def _stable_legs(monkeypatch):
    """Deterministic, network-free replacements for every composition leg."""

    async def _summary():
        return _fixed_summary()

    async def _signals():
        return dict(FIXED_SIGNALS_PAYLOAD)

    async def _health():
        return dict(FIXED_HEALTH_PAYLOAD)

    monkeypatch.setattr(dashboard_api, "_compute_summary", _summary)
    monkeypatch.setattr(signals_api, "build_active_signals_payload", _signals)
    monkeypatch.setattr(health_api, "health_subsystems", _health)


def test_command_view_contract_snapshot(_stable_legs):
    r = client.get("/api/v1/view/command")
    assert r.status_code == 200
    body = r.json()

    assert body["view"] == "command"
    assert body["view_version"] == 1
    assert datetime.fromisoformat(body["generated_at"]).tzinfo is not None

    # Exported contract snapshot must equal the literal expected set.
    assert set(view_api.SECTION_KEYS) == EXPECTED_SECTIONS
    assert set(body["sections"]) == EXPECTED_SECTIONS
    assert body["hints"] == []
    assert body["errors"] == {}
    assert body["degraded"] is False

    now = datetime.now(timezone.utc)
    for name in EXPECTED_SECTIONS:
        section = body["sections"][name]
        assert set(section.keys()) == ENVELOPE_KEYS, f"envelope drift in section {name}"
        assert isinstance(section["freshness_s"], int)
        assert section["freshness_s"] >= 0
        assert isinstance(section["degraded"], bool)
        assert isinstance(section["version"], int)
        assert section["version"] >= 1
        updated_at = datetime.fromisoformat(section["updated_at"])
        assert updated_at.tzinfo is not None
        assert updated_at <= now

    market = body["sections"]["market"]["value"]
    assert market["cards"] == FIXED_CARDS
    assert market["breadth"] == FIXED_BREADTH
    assert market["market_status"] == FIXED_STATUS

    regime = body["sections"]["regime"]["value"]
    assert regime["regime_overview"] == FIXED_REGIME
    assert regime["options_analytics"] == FIXED_OPTIONS

    assert body["sections"]["signals"]["value"] == FIXED_SIGNALS_PAYLOAD
    assert body["sections"]["feed_health"]["value"] == FIXED_HEALTH_PAYLOAD
    assert body["sections"]["kill_switch"]["value"]["active"] is False
    assert body["sections"]["ml"]["value"] == {"ml_prediction": FIXED_ML}
    assert body["sections"]["risk_events"]["value"] == {"fii_dii": FIXED_FII}


def test_command_view_versions_stable_for_identical_data(_stable_legs):
    first = client.get("/api/v1/view/command").json()
    second = client.get("/api/v1/view/command").json()

    for name in EXPECTED_SECTIONS:
        assert first["sections"][name]["value"] == second["sections"][name]["value"]
        assert (
            first["sections"][name]["version"] == second["sections"][name]["version"]
        ), f"version changed for identical payload in section {name}"


def test_command_view_version_increments_only_on_change(_stable_legs, monkeypatch):
    first = client.get("/api/v1/view/command").json()

    async def _changed_signals():
        payload = dict(FIXED_SIGNALS_PAYLOAD)
        payload["signals"] = [{"signal_id": "sig-2", "underlying": "BANKNIFTY"}]
        return payload

    monkeypatch.setattr(signals_api, "build_active_signals_payload", _changed_signals)
    view_api._signals_cache.clear()

    second = client.get("/api/v1/view/command").json()

    assert (
        second["sections"]["signals"]["version"]
        == first["sections"]["signals"]["version"] + 1
    )
    for name in EXPECTED_SECTIONS - {"signals"}:
        assert (
            second["sections"][name]["version"] == first["sections"][name]["version"]
        ), f"unchanged section {name} must not bump its version"


def test_command_view_degraded_leg_isolated_and_honest(_stable_legs, monkeypatch):
    async def _boom():
        raise RuntimeError("signal service unreachable")

    monkeypatch.setattr(signals_api, "build_active_signals_payload", _boom)
    view_api._signals_cache.clear()

    r = client.get("/api/v1/view/command")
    assert r.status_code == 200
    body = r.json()

    assert body["degraded"] is True
    assert "signals" in body["errors"]
    assert "signal service unreachable" in body["errors"]["signals"]

    section = body["sections"]["signals"]
    assert set(section.keys()) == ENVELOPE_KEYS
    assert section["value"] is None
    assert section["degraded"] is True

    # Fail-open: the remaining legs stay healthy and populated.
    assert body["sections"]["market"]["degraded"] is False
    assert body["sections"]["market"]["value"]["market_status"] == FIXED_STATUS
    assert body["sections"]["feed_health"]["degraded"] is False
    assert body["sections"]["kill_switch"]["degraded"] is False
    assert set(body["errors"].keys()) == {"signals"}


def test_command_view_partial_summary_failure_maps_to_own_section(_stable_legs, monkeypatch):
    async def _degraded_summary():
        return _fixed_summary(
            ml_prediction=None,
            errors={"ml": "ML prediction unavailable"},
            degraded=True,
        )

    monkeypatch.setattr(dashboard_api, "_compute_summary", _degraded_summary)
    dashboard_api._summary_cache.clear()

    body = client.get("/api/v1/view/command").json()

    assert body["degraded"] is True
    assert "ML prediction unavailable" in body["errors"]["ml"]
    assert body["sections"]["ml"]["degraded"] is True
    assert body["sections"]["ml"]["value"] == {"ml_prediction": None}

    # A damaged summary leg must not poison the other sections.
    assert "market" not in body["errors"]
    assert body["sections"]["market"]["degraded"] is False
    assert body["sections"]["market"]["value"]["cards"] == FIXED_CARDS
    assert body["sections"]["risk_events"]["degraded"] is False
