"""P1-2 contract tests for GET /api/v1/view/command (frozen CommandView v1).

Follows the existing dashboard-summary test pattern: bare TestClient (no
lifespan), caches cleared per test, and every heavy leg monkeypatched so the
suite never touches the network or the ambient provider.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.algo.algo_service import (
    algo_account_service,
    algo_order_service,
    algo_signals_service,
)
from app.api import dashboard as dashboard_api
from app.api import futures as futures_api
from app.api import health as health_api
from app.api import signals as signals_api
from app.api import view as view_api
from app.api.dashboard import DashboardSummary
from app.event_engine.risk_overlay import EventRiskParameters
from app.event_engine.service import event_engine_service
from app.main import app
from app.ml.predictor import ml_predictor
from app.models.options import OptionChainResponse, OptionsAnalytics
from app.models.paper import PortfolioSummary, VirtualPosition
from app.research.enums import Direction, ForecastHorizon
from app.research.models import ResearchPrediction
from app.research.predictions import PredictionService
from app.research.trend_forecast import trend_forecaster
from app.services.options_service import options_service
from app.services.paper_service import paper_service
from app.services.regime_service import regime_service
from app.signals.portfolio_greeks import PortfolioGreeksSummary, portfolio_greeks_ledger

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
    "paper",
    "forecast",
    "algo",
}
ENVELOPE_KEYS = {"value", "updated_at", "freshness_s", "degraded", "version"}

FIXED_CARDS = [{"symbol": "NIFTY 50", "ltp": 24870.0, "status": "LIVE"}]
FIXED_BREADTH = {"advances": 30, "declines": 20, "status": "LIVE"}
FIXED_STATUS = {"session": "REGULAR", "status": "LIVE"}
FIXED_REGIME = {"regime_state": "TRENDING_UP"}
FIXED_OPTIONS = {"pcr_oi": 1.1, "available": True}
FIXED_ML = {"prob_up": 0.61}
FIXED_FII = {"fii_net_crores": -1200.0}

# ── D7 per-instrument maps: regime / ml / forecast ───────────────────────
FIXED_ML_BY_SYMBOL = {
    "NIFTY": {"symbol": "NIFTY", "predicted_bias": "BULLISH", "confidence_score": 0.61},
    "BANKNIFTY": {"symbol": "BANKNIFTY", "predicted_bias": "BEARISH", "confidence_score": 0.54},
    "SENSEX": {"symbol": "SENSEX", "predicted_bias": "NEUTRAL", "confidence_score": 0.50},
}

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
FIXED_FEED_CIRCUITS = {
    "status": "LIVE",
    "is_healthy_for_trading": True,
    "states": {
        "NIFTY": {"instrument_id": "NIFTY", "health": "HEALTHY"},
        "BANKNIFTY": {"instrument_id": "BANKNIFTY", "health": "HEALTHY"},
    },
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

# ── P3 additive sections: paper / forecast / algo ────────────────────────
FIXED_PAPER_PORTFOLIO = {
    "virtual_capital": 1000000.0,
    "available_margin": 890000.0,
    "used_margin": 110000.0,
    "margin_utilization_pct": 11.0,
    "total_realized_pnl": 4200.0,
    "total_unrealized_pnl": -1150.0,
    "total_portfolio_pnl": 3050.0,
    "open_positions_count": 1,
}
FIXED_PAPER_POSITION = {
    "position_id": "pos-1",
    "symbol": "NIFTY24DEC24000CE",
    "underlying": "NIFTY",
    "instrument_type": "OPTION",
    "side": "BUY",
    "product": "INTRADAY",
    "quantity": 75,
    "average_price": 120.5,
    "ltp": 105.25,
    "unrealized_pnl": -1143.75,
    "realized_pnl": 0.0,
    "used_margin": 9037.5,
    "is_open": True,
}

FIXED_PREDICTION_TS = "2026-09-18T07:20:00+00:00"
FIXED_FORECAST_PAYLOAD = {
    "instrument": "NIFTY 50",
    "timeframe": "1h",
    "forecast_horizon": "1h",
    "direction": "BULLISH",
    "score": 42.0,
    "confidence": 0.7,
    "status": "RESEARCH",
    "current_price": 24710.0,
    "data_quality": "HEALTHY",
}

FIXED_ALGO_ACCOUNT = {
    "account_id": "00000000-0000-0000-0000-0000000000a1",
    "mode": "PAPER",
    "is_active": True,
    "display_name": "Signal Book",
    "capital": {
        "investment_limit": "3000.00",
        "available": "3000.00",
        "reserved": "0.00",
        "deployed": "0.00",
        "daily_loss": "0.00",
        "daily_loss_limit": "500.00",
        "is_breached": False,
    },
    "kill_switch": {"is_killed": False, "kill_level": "NONE"},
    "consent": {"acknowledged": True, "disclosure_version": "v1.0-2026-08-31"},
}
FIXED_ALGO_EXPOSURE = {
    "gross_exposure": "110000.00",
    "net_exposure": "110000.00",
    "long_exposure": "110000.00",
    "short_exposure": "0.00",
    "portfolio_delta": "75.5",
    "portfolio_gamma": "0.4",
    "portfolio_theta": "-850.0",
    "portfolio_vega": "2100.0",
    "by_underlying": {"NIFTY": "110000.00"},
    "by_strategy": {"unknown": "110000.00"},
}
FIXED_ALGO_ORDER = {
    "client_order_id": "0f6b8f8e-0000-4000-8000-000000000001",
    "symbol": "NIFTY24DEC24000CE",
    "side": "BUY",
    "quantity": 75,
    "price": "120.50",
    "order_type": "LIMIT",
    "status": "PENDING",
    "fill_price": None,
    "fill_quantity": 0,
    "broker_order_id": None,
    "is_paper": True,
    "rejection_reason": None,
    "created_at": FIXED_PREDICTION_TS,
}
FIXED_PORTFOLIO_GREEKS = {
    "total_delta": 75.5,
    "total_gamma": 0.4,
    "total_theta_day": -850.0,
    "total_vega": 2100.0,
    "gross_delta": 75.5,
    "gross_gamma": 0.4,
    "gross_theta_day": 850.0,
    "gross_vega": 2100.0,
    "total_open_positions": 1,
}


def _fixed_prediction(instrument: str = "NIFTY 50", prediction_id: str = "pred-1") -> ResearchPrediction:
    return ResearchPrediction(
        prediction_id=prediction_id,
        indicator_id="trend_forecast_1h",
        indicator_version="v1",
        instrument=instrument,
        timeframe="1h",
        timestamp=datetime.fromisoformat(FIXED_PREDICTION_TS),
        current_price=24710.0,
        direction=Direction.BULLISH,
        score=42.0,
        confidence=0.7,
        forecast_horizon=ForecastHorizon.HORIZON_1H,
        horizon_candles=1,
    )


def _fixed_regime_overview(symbol: str) -> dict:
    return {
        "symbol": symbol,
        "regime_state": "TRENDING_UP" if symbol == "NIFTY" else "RANGEBOUND",
        "confidence_score": 0.8,
        "key_levels": {
            "nearest_support": 24600.0,
            "nearest_resistance": 25100.0,
        },
    }


def _fixed_options_analytics(symbol: str) -> OptionsAnalytics:
    return OptionsAnalytics(
        symbol=symbol,
        spot_price=24870.0,
        futures_price=24951.0,
        expiry="2026-09-24",
        atm_strike=24900.0,
        atm_iv=13.85,
        pcr_oi=1.12,
        pcr_volume=1.05,
        max_pain_strike=24900.0,
    )


def _fixed_option_chain(symbol: str) -> OptionChainResponse:
    return OptionChainResponse(
        underlying=symbol,
        spot_price=24870.0,
        futures_price=24951.0,
        expiry="2026-09-24",
        analytics=_fixed_options_analytics(symbol),
    )


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
    view_api._paper_cache.clear()
    view_api._forecast_cache.clear()
    view_api._algo_cache.clear()
    view_api._feed_circuits_cache.clear()
    view_api._regime_by_symbol_cache.clear()
    view_api._ml_by_symbol_cache.clear()
    view_api._section_versions.clear()
    yield
    dashboard_api._summary_cache.clear()
    view_api._signals_cache.clear()
    view_api._futures_cache.clear()
    view_api._event_risk_cache.clear()
    view_api._paper_cache.clear()
    view_api._forecast_cache.clear()
    view_api._algo_cache.clear()
    view_api._feed_circuits_cache.clear()
    view_api._regime_by_symbol_cache.clear()
    view_api._ml_by_symbol_cache.clear()
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

    def _feed_circuits():
        return dict(FIXED_FEED_CIRCUITS)

    async def _paper_portfolio(session=None, user_id=None):
        return PortfolioSummary(**FIXED_PAPER_PORTFOLIO)

    async def _paper_positions(session=None, user_id=None):
        return [VirtualPosition(**FIXED_PAPER_POSITION)]

    async def _forecast(**kwargs):
        return dict(FIXED_FORECAST_PAYLOAD)

    async def _predictions(indicator_id=None, instrument=None, limit=50, session=None):
        return [_fixed_prediction(instrument=instrument or "NIFTY 50")]

    async def _regime(symbol: str = "NIFTY"):
        return _fixed_regime_overview(symbol)

    async def _options_chain(symbol: str = "NIFTY", expiry_str=None):
        return _fixed_option_chain(symbol)

    async def _ml(symbol: str = "NIFTY", horizon_minutes=60):
        return dict(FIXED_ML_BY_SYMBOL[symbol])

    async def _account(session=None, user_id=None):
        return dict(FIXED_ALGO_ACCOUNT)

    async def _exposure(session=None, user_id=None):
        return dict(FIXED_ALGO_EXPOSURE)

    async def _orders(session=None, user_id=None, status=None, symbol=None, limit=50):
        return [dict(FIXED_ALGO_ORDER)]

    def _greeks():
        return PortfolioGreeksSummary(**FIXED_PORTFOLIO_GREEKS)

    monkeypatch.setattr(dashboard_api, "_compute_summary", _summary)
    monkeypatch.setattr(signals_api, "build_active_signals_payload", _signals)
    monkeypatch.setattr(health_api, "health_subsystems", _health)
    monkeypatch.setattr(signals_api, "get_feed_health", _feed_circuits)
    monkeypatch.setattr(futures_api, "build_futures_overview", _live_futures_overview)
    monkeypatch.setattr(event_engine_service, "get_risk_overlay", _fixed_event_risk)
    monkeypatch.setattr(event_engine_service, "_initialized", True)
    monkeypatch.setattr(regime_service, "classify_market_regime", _regime)
    monkeypatch.setattr(options_service, "get_option_chain_matrix", _options_chain)
    monkeypatch.setattr(ml_predictor, "predict_probabilities", _ml)
    monkeypatch.setattr(paper_service, "get_portfolio_summary", _paper_portfolio)
    monkeypatch.setattr(paper_service, "get_positions", _paper_positions)
    monkeypatch.setattr(trend_forecaster, "forecast", _forecast)
    monkeypatch.setattr(PredictionService, "list_predictions", _predictions)
    monkeypatch.setattr(algo_account_service, "get_account_detail", _account)
    monkeypatch.setattr(algo_signals_service, "get_exposure", _exposure)
    monkeypatch.setattr(algo_order_service, "list_orders", _orders)
    monkeypatch.setattr(portfolio_greeks_ledger, "get_summary", _greeks)


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
    regime_by_symbol = regime["by_symbol"]
    assert set(regime_by_symbol) == {"NIFTY", "BANKNIFTY", "SENSEX"}
    for symbol, entry in regime_by_symbol.items():
        assert set(entry) == {"regime_overview", "options_analytics"}, f"shape drift for {symbol}"
    assert regime_by_symbol["NIFTY"]["regime_overview"] == FIXED_REGIME
    assert regime_by_symbol["BANKNIFTY"]["regime_overview"] == _fixed_regime_overview("BANKNIFTY")
    assert regime_by_symbol["SENSEX"]["regime_overview"] == _fixed_regime_overview("SENSEX")
    for symbol in ("NIFTY", "BANKNIFTY", "SENSEX"):
        assert regime_by_symbol[symbol]["options_analytics"] == _fixed_options_analytics(
            symbol
        ).model_dump(mode="json")

    assert body["sections"]["signals"]["value"] == FIXED_SIGNALS_PAYLOAD
    feed_health = body["sections"]["feed_health"]["value"]
    assert feed_health["subsystems"] == FIXED_HEALTH_PAYLOAD
    assert feed_health["feed_circuits"] == FIXED_FEED_CIRCUITS
    assert body["sections"]["kill_switch"]["value"]["active"] is False
    ml = body["sections"]["ml"]["value"]
    assert ml["ml_prediction"] == FIXED_ML
    assert ml["by_symbol"] == FIXED_ML_BY_SYMBOL

    paper = body["sections"]["paper"]["value"]
    assert paper["portfolio"] == FIXED_PAPER_PORTFOLIO
    assert paper["positions"] == [FIXED_PAPER_POSITION]

    forecast = body["sections"]["forecast"]["value"]
    assert forecast["forecast"] == FIXED_FORECAST_PAYLOAD
    assert forecast["predictions"] == [_fixed_prediction().model_dump(mode="json")]
    assert forecast["by_instrument"] == {
        instrument: [_fixed_prediction(instrument=instrument).model_dump(mode="json")]
        for instrument in ("NIFTY 50", "BANKNIFTY", "SENSEX")
    }

    algo = body["sections"]["algo"]["value"]
    assert algo["account"] == FIXED_ALGO_ACCOUNT
    assert algo["exposure"] == FIXED_ALGO_EXPOSURE
    assert algo["orders"] == [FIXED_ALGO_ORDER]
    assert algo["portfolio_greeks"] == PortfolioGreeksSummary(
        **FIXED_PORTFOLIO_GREEKS
    ).model_dump(mode="json")

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


def test_feed_health_circuits_failure_is_null_and_honest(_stable_legs, monkeypatch):
    def _boom():
        raise RuntimeError("feed circuit monitor unreachable")

    monkeypatch.setattr(signals_api, "get_feed_health", _boom)
    view_api._feed_circuits_cache.clear()

    r = client.get("/api/v1/view/command")
    assert r.status_code == 200
    body = r.json()

    section = body["sections"]["feed_health"]
    assert section["value"]["subsystems"] == FIXED_HEALTH_PAYLOAD
    assert section["value"]["feed_circuits"] is None
    assert section["degraded"] is True
    assert "feed circuit" in body["errors"]["feed_health"].lower()

    # No fabricated circuit states, and the failure is contained to the section.
    assert body["sections"]["market"]["degraded"] is False
    assert set(body["errors"]) == {"feed_health"}


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
    assert body["sections"]["ml"]["value"]["ml_prediction"] is None
    assert set(body["sections"]["ml"]["value"]["by_symbol"]) == {"NIFTY", "BANKNIFTY", "SENSEX"}

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


# ── P3 additive sections: paper / forecast / algo ────────────────────────


def test_new_section_ttls_match_poll_cadence():
    assert 0.0 < view_api.PAPER_FRESH_TTL <= 4.0
    assert view_api.FORECAST_FRESH_TTL >= 60.0
    assert 0.0 < view_api.ALGO_FRESH_TTL <= 5.0


def test_new_sections_reuse_cached_sources_within_ttl(_stable_legs, monkeypatch):
    calls: dict[str, int] = {}

    def _count(name: str) -> None:
        calls[name] = calls.get(name, 0) + 1

    async def _paper_portfolio(session=None, user_id=None):
        _count("paper_portfolio")
        return PortfolioSummary(**FIXED_PAPER_PORTFOLIO)

    async def _paper_positions(session=None, user_id=None):
        _count("paper_positions")
        return [VirtualPosition(**FIXED_PAPER_POSITION)]

    async def _forecast(**kwargs):
        _count("forecast")
        return dict(FIXED_FORECAST_PAYLOAD)

    async def _predictions(indicator_id=None, instrument=None, limit=50, session=None):
        _count("predictions")
        return [_fixed_prediction(instrument=instrument or "NIFTY 50")]

    async def _regime(symbol: str = "NIFTY"):
        _count("regime")
        return _fixed_regime_overview(symbol)

    async def _options_chain(symbol: str = "NIFTY", expiry_str=None):
        _count("options")
        return _fixed_option_chain(symbol)

    async def _ml(symbol: str = "NIFTY", horizon_minutes=60):
        _count("ml")
        return dict(FIXED_ML_BY_SYMBOL[symbol])

    async def _account(session=None, user_id=None):
        _count("account")
        return dict(FIXED_ALGO_ACCOUNT)

    async def _exposure(session=None, user_id=None):
        _count("exposure")
        return dict(FIXED_ALGO_EXPOSURE)

    async def _orders(session=None, user_id=None, status=None, symbol=None, limit=50):
        _count("orders")
        return [dict(FIXED_ALGO_ORDER)]

    def _greeks():
        _count("greeks")
        return PortfolioGreeksSummary(**FIXED_PORTFOLIO_GREEKS)

    monkeypatch.setattr(paper_service, "get_portfolio_summary", _paper_portfolio)
    monkeypatch.setattr(paper_service, "get_positions", _paper_positions)
    monkeypatch.setattr(trend_forecaster, "forecast", _forecast)
    monkeypatch.setattr(PredictionService, "list_predictions", _predictions)
    monkeypatch.setattr(regime_service, "classify_market_regime", _regime)
    monkeypatch.setattr(options_service, "get_option_chain_matrix", _options_chain)
    monkeypatch.setattr(ml_predictor, "predict_probabilities", _ml)
    monkeypatch.setattr(algo_account_service, "get_account_detail", _account)
    monkeypatch.setattr(algo_signals_service, "get_exposure", _exposure)
    monkeypatch.setattr(algo_order_service, "list_orders", _orders)
    monkeypatch.setattr(portfolio_greeks_ledger, "get_summary", _greeks)

    first = client.get("/api/v1/view/command").json()
    second = client.get("/api/v1/view/command").json()

    # The ~2s stream cadence must hit each source once per TTL window, not once
    # per compose. NIFTY reuses the summary regime leg; NIFTY 50 reuses the
    # top-level prediction rows.
    assert calls == {
        "paper_portfolio": 1,
        "paper_positions": 1,
        "forecast": 1,
        "predictions": 3,
        "regime": 2,
        "options": 3,
        "ml": 3,
        "account": 1,
        "exposure": 1,
        "orders": 1,
        "greeks": 1,
    }
    for name in ("paper", "forecast", "algo", "regime", "ml"):
        assert first["sections"][name]["value"] == second["sections"][name]["value"]


def test_paper_section_degrades_leg_independently(_stable_legs, monkeypatch):
    async def _boom(session=None, user_id=None):
        raise RuntimeError("paper positions store unreachable")

    monkeypatch.setattr(paper_service, "get_positions", _boom)
    view_api._paper_cache.clear()

    r = client.get("/api/v1/view/command")
    assert r.status_code == 200
    body = r.json()

    paper = body["sections"]["paper"]
    assert paper["value"]["portfolio"] == FIXED_PAPER_PORTFOLIO
    assert paper["value"]["positions"] is None
    assert paper["degraded"] is True
    assert "paper positions store unreachable" in body["errors"]["paper"]

    # No fabricated numbers where the source failed, and the other sections
    # stay healthy.
    assert body["sections"]["forecast"]["degraded"] is False
    assert body["sections"]["algo"]["degraded"] is False


def test_forecast_section_degrades_honestly(_stable_legs, monkeypatch):
    async def _boom(**kwargs):
        raise RuntimeError("forecast engine offline")

    monkeypatch.setattr(trend_forecaster, "forecast", _boom)
    view_api._forecast_cache.clear()

    r = client.get("/api/v1/view/command")
    assert r.status_code == 200
    body = r.json()

    forecast = body["sections"]["forecast"]
    assert forecast["value"]["forecast"] is None
    assert forecast["value"]["predictions"] == [_fixed_prediction().model_dump(mode="json")]
    assert forecast["degraded"] is True
    assert "forecast engine offline" in body["errors"]["forecast"]

    assert body["sections"]["paper"]["degraded"] is False
    assert body["sections"]["algo"]["degraded"] is False


def test_algo_section_degrades_leg_independently(_stable_legs, monkeypatch):
    async def _boom(session=None, user_id=None):
        raise RuntimeError("exposure service unavailable")

    monkeypatch.setattr(algo_signals_service, "get_exposure", _boom)
    view_api._algo_cache.clear()

    r = client.get("/api/v1/view/command")
    assert r.status_code == 200
    body = r.json()

    algo = body["sections"]["algo"]
    assert algo["value"]["account"] == FIXED_ALGO_ACCOUNT
    assert algo["value"]["exposure"] is None
    assert algo["value"]["orders"] == [FIXED_ALGO_ORDER]
    assert algo["value"]["portfolio_greeks"] == PortfolioGreeksSummary(
        **FIXED_PORTFOLIO_GREEKS
    ).model_dump(mode="json")
    assert algo["degraded"] is True
    assert "exposure service unavailable" in body["errors"]["algo"]

    assert body["sections"]["paper"]["degraded"] is False
    assert body["sections"]["forecast"]["degraded"] is False


# ── D7: per-instrument maps for regime / ml / forecast ───────────────────


def test_per_instrument_maps_cover_all_instruments(_stable_legs):
    body = client.get("/api/v1/view/command").json()

    regime = body["sections"]["regime"]["value"]["by_symbol"]
    ml = body["sections"]["ml"]["value"]["by_symbol"]
    forecast = body["sections"]["forecast"]["value"]["by_instrument"]

    assert set(regime) == {"NIFTY", "BANKNIFTY", "SENSEX"}
    assert set(ml) == {"NIFTY", "BANKNIFTY", "SENSEX"}
    assert set(forecast) == {"NIFTY 50", "BANKNIFTY", "SENSEX"}

    for symbol, entry in regime.items():
        assert set(entry) == {"regime_overview", "options_analytics"}, f"shape drift for {symbol}"
        assert entry["regime_overview"] is not None
        assert entry["options_analytics"] is not None

    assert regime["NIFTY"]["regime_overview"] == FIXED_REGIME
    assert regime["BANKNIFTY"]["regime_overview"] == _fixed_regime_overview("BANKNIFTY")
    assert regime["SENSEX"]["regime_overview"] == _fixed_regime_overview("SENSEX")
    for symbol in ("NIFTY", "BANKNIFTY", "SENSEX"):
        assert regime[symbol]["options_analytics"] == _fixed_options_analytics(
            symbol
        ).model_dump(mode="json")

    assert ml == FIXED_ML_BY_SYMBOL
    for instrument in ("NIFTY 50", "BANKNIFTY", "SENSEX"):
        assert forecast[instrument] == [
            _fixed_prediction(instrument=instrument).model_dump(mode="json")
        ]


def test_regime_by_symbol_nifty_reuses_summary_without_service_call(_stable_legs, monkeypatch):
    calls: list[str] = []

    async def _regime(symbol: str = "NIFTY"):
        calls.append(symbol)
        return _fixed_regime_overview(symbol)

    monkeypatch.setattr(regime_service, "classify_market_regime", _regime)

    body = client.get("/api/v1/view/command").json()

    # NIFTY is already classified by the summary SWR; only the siblings probe.
    assert calls == ["BANKNIFTY", "SENSEX"]
    assert (
        body["sections"]["regime"]["value"]["by_symbol"]["NIFTY"]["regime_overview"]
        == FIXED_REGIME
    )


def test_per_instrument_maps_fail_open_per_symbol(_stable_legs, monkeypatch):
    async def _regime(symbol: str = "NIFTY"):
        if symbol == "SENSEX":
            raise RuntimeError("SENSEX regime feed down")
        return _fixed_regime_overview(symbol)

    async def _ml(symbol: str = "NIFTY", horizon_minutes=60):
        if symbol == "BANKNIFTY":
            raise RuntimeError("BANKNIFTY ML model unavailable")
        return dict(FIXED_ML_BY_SYMBOL[symbol])

    async def _predictions(indicator_id=None, instrument=None, limit=50, session=None):
        if instrument == "SENSEX":
            raise RuntimeError("SENSEX predictions store down")
        return [_fixed_prediction(instrument=instrument or "NIFTY 50")]

    monkeypatch.setattr(regime_service, "classify_market_regime", _regime)
    monkeypatch.setattr(ml_predictor, "predict_probabilities", _ml)
    monkeypatch.setattr(PredictionService, "list_predictions", _predictions)

    r = client.get("/api/v1/view/command")
    assert r.status_code == 200
    body = r.json()

    regime = body["sections"]["regime"]
    assert regime["value"]["by_symbol"]["SENSEX"]["regime_overview"] is None
    # One failed source only nulls its own leg — options analytics still lands.
    assert regime["value"]["by_symbol"]["SENSEX"]["options_analytics"] is not None
    assert regime["value"]["by_symbol"]["NIFTY"]["regime_overview"] == FIXED_REGIME
    assert (
        regime["value"]["by_symbol"]["BANKNIFTY"]["regime_overview"]
        == _fixed_regime_overview("BANKNIFTY")
    )

    ml = body["sections"]["ml"]
    assert ml["value"]["by_symbol"]["BANKNIFTY"] is None
    assert ml["value"]["by_symbol"]["NIFTY"] == FIXED_ML_BY_SYMBOL["NIFTY"]
    assert ml["value"]["by_symbol"]["SENSEX"] == FIXED_ML_BY_SYMBOL["SENSEX"]

    forecast = body["sections"]["forecast"]
    assert forecast["value"]["by_instrument"]["SENSEX"] is None
    assert forecast["value"]["by_instrument"]["NIFTY 50"] == [
        _fixed_prediction().model_dump(mode="json")
    ]
    assert forecast["value"]["by_instrument"]["BANKNIFTY"] == [
        _fixed_prediction(instrument="BANKNIFTY").model_dump(mode="json")
    ]

    # A missing optional instrument is not a section fault: neither the
    # sections nor the view degrade, and no fabricated payloads appear.
    assert body["degraded"] is False
    assert body["errors"] == {}
    for name in ("regime", "ml", "forecast"):
        assert body["sections"][name]["degraded"] is False, f"{name} must stay healthy"


def test_per_instrument_map_ttls_match_poll_cadence():
    assert 0.0 < view_api.REGIME_BY_SYMBOL_FRESH_TTL <= 45.0
    assert 0.0 < view_api.ML_BY_SYMBOL_FRESH_TTL <= 15.0
    assert view_api.FORECAST_BY_INSTRUMENT_FRESH_TTL >= 60.0
