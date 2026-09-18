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
from app.api import futures as futures_api
from app.api import health as health_api
from app.api import signals as signals_api
from app.api import view as view_api
from app.api.dashboard import DashboardSummary
from app.event_engine.risk_overlay import EventRiskParameters
from app.event_engine.service import event_engine_service
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
FIXED_FUTURES_TS = "2026-09-18T07:21:30+00:00"
FIXED_EVENT_RISK_TS = "2026-09-18T07:21:45+00:00"
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

FIXED_FUTURES_BUILDUP = {
    "buildup_type": "LONG_BUILDUP",
    "price_change_pct": 0.42,
    "oi_change_pct": 1.7,
    "interpretation": "Fresh longs",
}
FIXED_FUTURES_ROLLOVER = {
    "rollover_percent": 41.5,
    "rollover_pace": "IN_LINE",
    "previous_month_rollover": 68.0,
}
FIXED_FUTURES_OVERVIEW = {
    "spot_price": 24870.0,
    "near_future_price": 24951.0,
    "basis_pts": 81.0,
    "term_structure": {
        "curve_state": "CONTANGO",
        "contracts": [{"symbol": "FUT-1", "ltp": 24951.0, "basis": 81.0}],
    },
}


def _expected_futures(symbol: str) -> dict:
    return {
        "underlying": symbol,
        "spot_price": FIXED_FUTURES_OVERVIEW["spot_price"],
        "near_future_price": FIXED_FUTURES_OVERVIEW["near_future_price"],
        "basis_pts": FIXED_FUTURES_OVERVIEW["basis_pts"],
        "term_structure": {
            "underlying": symbol,
            "curve_state": "CONTANGO",
            "contracts": FIXED_FUTURES_OVERVIEW["term_structure"]["contracts"],
        },
        "buildup": {"underlying": symbol, **FIXED_FUTURES_BUILDUP},
        "rollover": {"underlying": symbol, **FIXED_FUTURES_ROLLOVER},
    }


async def _live_futures_overview(symbol: str) -> dict:
    """Envelope-shaped fake of `build_futures_overview` carrying real data."""
    return {
        "data": _expected_futures(symbol),
        "error": None,
        "meta": {"provider": "futures_engine", "timestamp": FIXED_FUTURES_TS, "status": "LIVE"},
    }


async def _unavailable_futures_overview(symbol: str) -> dict:
    """The production shape today: self-describing UNAVAILABLE, never numbers."""
    return {
        "data": {
            "underlying": symbol,
            "spot_price": None,
            "near_future_price": None,
            "basis_pts": None,
            "term_structure": {"underlying": symbol, "curve_state": "UNAVAILABLE", "contracts": []},
            "buildup": {
                "underlying": symbol,
                "buildup_type": "UNAVAILABLE",
                "price_change_pct": 0.0,
                "oi_change_pct": 0.0,
                "interpretation": "Authentic broker futures data offline or unavailable.",
            },
            "rollover": {
                "underlying": symbol,
                "rollover_percent": None,
                "rollover_pace": "UNAVAILABLE",
                "previous_month_rollover": None,
            },
        },
        "error": None,
        "meta": {"provider": "futures_engine", "timestamp": FIXED_FUTURES_TS, "status": "OFFLINE"},
    }


def _fixed_event_risk(underlying: str = "BANKNIFTY", now=None) -> EventRiskParameters:
    return EventRiskParameters(
        underlying=underlying,
        proximity_state="NORMAL",
        can_enter=True,
        sizing_multiplier=1.0,
        max_loss_dampener=1.0,
        prohibit_naked_options=False,
        minutes_to_event=None,
        evaluated_at=datetime.fromisoformat(FIXED_EVENT_RISK_TS),
    )


@pytest.fixture(autouse=True)
def _clear_view_state():
    dashboard_api._summary_cache.clear()
    view_api._signals_cache.clear()
    view_api._futures_cache.clear()
    view_api._event_risk_cache.clear()
    view_api._section_versions.clear()
    yield
    dashboard_api._summary_cache.clear()
    view_api._signals_cache.clear()
    view_api._futures_cache.clear()
    view_api._event_risk_cache.clear()
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
    monkeypatch.setattr(futures_api, "build_futures_overview", _live_futures_overview)
    monkeypatch.setattr(event_engine_service, "get_risk_overlay", _fixed_event_risk)
    monkeypatch.setattr(event_engine_service, "_initialized", True)


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
    assert regime["futures"] == {
        "NIFTY": _expected_futures("NIFTY"),
        "BANKNIFTY": _expected_futures("BANKNIFTY"),
    }

    assert body["sections"]["signals"]["value"] == FIXED_SIGNALS_PAYLOAD
    assert body["sections"]["feed_health"]["value"] == FIXED_HEALTH_PAYLOAD
    assert body["sections"]["kill_switch"]["value"]["active"] is False
    assert body["sections"]["ml"]["value"] == {"ml_prediction": FIXED_ML}

    risk_events = body["sections"]["risk_events"]["value"]
    assert risk_events["fii_dii"] == FIXED_FII
    assert risk_events["event_risk"]["underlying"] == "BANKNIFTY"
    assert risk_events["event_risk"]["proximity_state"] == "NORMAL"
    assert risk_events["event_risk"]["can_enter"] is True
    assert risk_events["event_risk"]["sizing_multiplier"] == 1.0
    assert risk_events["event_risk"]["evaluated_at"].startswith("2026-09-18T07:21:45")


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


# ── P1-6a/P1-6c enrichment: futures into regime, event risk into risk_events ──


def test_slow_leg_cache_ttls_are_at_least_60s():
    assert view_api.FUTURES_FRESH_TTL >= 60.0
    assert view_api.EVENT_RISK_FRESH_TTL >= 60.0


def test_futures_and_event_risk_legs_hit_cached_sources_once(_stable_legs, monkeypatch):
    futures_calls: list[str] = []
    overlay_calls: list[str] = []

    async def _counting_futures(symbol):
        futures_calls.append(symbol)
        return await _live_futures_overview(symbol)

    def _counting_overlay(underlying="BANKNIFTY", now=None):
        overlay_calls.append(underlying)
        return _fixed_event_risk(underlying)

    monkeypatch.setattr(futures_api, "build_futures_overview", _counting_futures)
    monkeypatch.setattr(event_engine_service, "get_risk_overlay", _counting_overlay)

    first = client.get("/api/v1/view/command").json()
    second = client.get("/api/v1/view/command").json()

    # One 60s-cached probe per instrument/underlying, not one per ~2s compose.
    assert futures_calls == ["NIFTY", "BANKNIFTY"]
    assert overlay_calls == ["BANKNIFTY"]
    assert first["sections"]["regime"]["value"]["futures"] == second["sections"]["regime"]["value"]["futures"]
    assert (
        first["sections"]["risk_events"]["value"]["event_risk"]
        == second["sections"]["risk_events"]["value"]["event_risk"]
    )


def test_regime_futures_unavailable_payload_is_null_without_degrading(_stable_legs, monkeypatch):
    monkeypatch.setattr(futures_api, "build_futures_overview", _unavailable_futures_overview)

    body = client.get("/api/v1/view/command").json()
    regime = body["sections"]["regime"]

    # No broker futures feed -> null per instrument, never the UNAVAILABLE shell.
    # Regime stays healthy: an optional overlay being absent is not a regime fault.
    assert regime["value"]["futures"] == {"NIFTY": None, "BANKNIFTY": None}
    assert regime["value"]["regime_overview"] == FIXED_REGIME
    assert regime["degraded"] is False
    assert "futures" not in (body["errors"].get("regime") or "").lower()

    # The absence is contained to regime; event risk and the rest stay healthy.
    assert body["sections"]["risk_events"]["degraded"] is False
    assert body["errors"] == {}


def test_regime_futures_source_failure_does_not_fail_endpoint(_stable_legs, monkeypatch):
    async def _boom(symbol):
        raise RuntimeError("broker futures feed down")

    monkeypatch.setattr(futures_api, "build_futures_overview", _boom)

    r = client.get("/api/v1/view/command")
    assert r.status_code == 200
    body = r.json()
    # A broken optional overlay yields explicit nulls; it never fails the view
    # and never poisons the regime health badge.
    assert body["sections"]["regime"]["value"]["futures"] == {"NIFTY": None, "BANKNIFTY": None}
    assert body["sections"]["regime"]["degraded"] is False
    assert "futures" not in (body["errors"].get("regime") or "").lower()


def test_regime_futures_partial_outage_is_fail_open_per_instrument(_stable_legs, monkeypatch):
    async def _partial(symbol):
        if symbol == "NIFTY":
            raise RuntimeError("NIFTY futures feed down")
        return await _live_futures_overview(symbol)

    monkeypatch.setattr(futures_api, "build_futures_overview", _partial)

    body = client.get("/api/v1/view/command").json()
    regime = body["sections"]["regime"]

    # One live instrument is enough: null for the dead leg, no section degradation.
    assert regime["value"]["futures"]["NIFTY"] is None
    assert regime["value"]["futures"]["BANKNIFTY"] == _expected_futures("BANKNIFTY")
    assert regime["degraded"] is False
    assert "regime" not in body["errors"]
    assert body["degraded"] is False


def test_risk_events_event_overlay_failure_is_null_and_isolated(_stable_legs, monkeypatch):
    def _boom(underlying="BANKNIFTY", now=None):
        raise RuntimeError("event engine unreachable")

    monkeypatch.setattr(event_engine_service, "get_risk_overlay", _boom)

    body = client.get("/api/v1/view/command").json()
    risk = body["sections"]["risk_events"]

    assert risk["value"]["fii_dii"] == FIXED_FII
    assert risk["value"]["event_risk"] is None
    assert risk["degraded"] is True
    assert "event risk" in body["errors"]["risk_events"].lower()

    # Fail-open: futures/regime stay healthy and populated.
    assert body["sections"]["regime"]["degraded"] is False
    assert body["sections"]["regime"]["value"]["futures"]["NIFTY"] == _expected_futures("NIFTY")
    assert set(body["errors"]) == {"risk_events"}
