"""
CommandView v1 composition endpoint — P1-2.

`GET /api/v1/view/command` assembles the frozen `CommandView` envelope from
existing legs only. It is a pure composition surface: every leg reuses an
existing service/computation (no fabricated fallbacks, no duplicated logic)
and every failure is contained to its own section (`value: null`,
`degraded: true`, `errors[section]`) — never zeros, never a synthetic quote.
One failing leg can never fail the endpoint.

Per-section envelope (exactly): `value`, `updated_at` (ISO-8601 UTC),
`freshness_s` (age of the section value in whole seconds), `degraded`,
`version` (content hash-gated, increments only when the value changes).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter

from app.api import dashboard as dashboard_api
from app.api import futures as futures_api
from app.api import health as health_api
from app.api import signals as signals_api
from app.api.dashboard import DashboardSummary, SUMMARY_FRESH_TTL
from app.event_engine.service import event_engine_service
from app.signals.safety.kill_switch import kill_switch

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/view", tags=["view"])

VIEW_NAME = "command"
VIEW_VERSION = 1

#: Frozen section set for CommandView v1 — the contract snapshot.
SECTION_KEYS: tuple[str, ...] = (
    "market",
    "regime",
    "signals",
    "feed_health",
    "kill_switch",
    "ml",
    "risk_events",
)

#: Short TTL for the active-signals leg: it fans out live quote requests and is
#: comparatively heavy, so a 3s cache absorbs concurrent Command-screen loads.
SIGNALS_FRESH_TTL = 3.0
_signals_cache: dict[str, tuple[float, dict[str, Any]]] = {}

#: Slow-moving overlays composed at the stream's ~2s cadence: a 60s TTL keeps
#: broker/event probes out of the hot path while the legs stay honest (null on
#: failure, never zeros).
FUTURES_FRESH_TTL = 60.0
EVENT_RISK_FRESH_TTL = 60.0
FUTURES_SYMBOLS: tuple[str, ...] = ("NIFTY", "BANKNIFTY")
EVENT_RISK_UNDERLYING = "BANKNIFTY"
_futures_cache: dict[str, tuple[float, dict[str, Any], datetime | None]] = {}
_event_risk_cache: dict[str, tuple[float, dict[str, Any] | None, datetime | None]] = {}

#: section -> (sha256(value), version). Single-process asyncio: this map is only
#: touched synchronously (no await between read and update), so no locks needed.
_section_versions: dict[str, tuple[str, int]] = {}


@dataclass
class _Leg:
    """One composition section: value + honest freshness/degradation metadata."""

    value: Any = None
    updated_at: datetime | None = None
    degraded: bool = False
    error: str | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse_time(raw: Any) -> datetime | None:
    """Parse an epoch-ms number or ISO-8601 string into an aware UTC datetime."""
    if raw is None:
        return None
    try:
        if isinstance(raw, (int, float)):
            return datetime.fromtimestamp(float(raw) / 1000.0, tz=timezone.utc)
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except Exception:
        return None


def _join_errors(errors: dict[str, str]) -> str | None:
    if not errors:
        return None
    return "; ".join(f"{k}: {v}" for k, v in errors.items())


def _section_version(section: str, value: Any) -> int:
    """Content-addressed version: stable for identical payloads, +1 on change."""
    digest = hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    prev = _section_versions.get(section)
    if prev is None:
        _section_versions[section] = (digest, 1)
    elif prev[0] != digest:
        _section_versions[section] = (digest, prev[1] + 1)
    return _section_versions[section][1]


async def _get_summary() -> DashboardSummary:
    """Dashboard summary through the same SWR cache the summary endpoint uses.

    Reuses `dashboard_api._summary_cache` / `SUMMARY_FRESH_TTL` verbatim
    (including the startup prewarm): fresh entries are served as-is, stale
    entries are served immediately and refreshed in the background. Behavior of
    `_compute_summary()` is untouched.
    """
    cached = dashboard_api._summary_cache.get("default")
    now = time.monotonic()
    if cached is not None:
        cached_time, data = cached
        if now - cached_time >= SUMMARY_FRESH_TTL:
            dashboard_api._trigger_background_summary_refresh()
        return data
    data = await dashboard_api._compute_summary()
    dashboard_api._summary_cache["default"] = (now, data)
    return data


async def _get_active_signals() -> dict[str, Any]:
    """Active-signals payload with a short TTL (heavy: quote fan-out)."""
    cached = _signals_cache.get("default")
    now = time.monotonic()
    if cached is not None and now - cached[0] < SIGNALS_FRESH_TTL:
        return cached[1]
    payload = await signals_api.build_active_signals_payload()
    _signals_cache["default"] = (time.monotonic(), payload)
    return payload


def _futures_has_data(data: Any) -> bool:
    """True only when the overview carries real broker futures data.

    The endpoint is self-describing: everything is `null`/`UNAVAILABLE` when
    no broker futures feed is wired, so those payloads become `null` upstream
    instead of surfacing placeholder shells as if they were data.
    """
    if not isinstance(data, dict):
        return False
    if data.get("near_future_price") is not None or data.get("basis_pts") is not None:
        return True
    term = data.get("term_structure")
    if (
        isinstance(term, dict)
        and term.get("contracts")
        and term.get("curve_state") not in (None, "UNAVAILABLE", "UNKNOWN")
    ):
        return True
    buildup = data.get("buildup")
    if isinstance(buildup, dict) and buildup.get("buildup_type") not in (None, "UNAVAILABLE", "UNKNOWN"):
        return True
    rollover = data.get("rollover")
    return isinstance(rollover, dict) and rollover.get("rollover_percent") is not None


async def _get_futures_overviews() -> tuple[dict[str, Any], datetime | None]:
    """NIFTY/BANKNIFTY futures overviews, cached 60s, fail-open per instrument.

    Reuses the same composition `GET /api/v1/futures/{symbol}/overview` serves
    (service call, not HTTP). An instrument with no broker futures data maps to
    `None` — never a fabricated basis/OI shell. Returns the oldest live
    observation time so the section can report honest freshness.
    """
    cached = _futures_cache.get("default")
    now = time.monotonic()
    if cached is not None and now - cached[0] < FUTURES_FRESH_TTL:
        return cached[1], cached[2]

    values: dict[str, Any] = {}
    oldest: datetime | None = None
    for symbol in FUTURES_SYMBOLS:
        data: Any = None
        ts: datetime | None = None
        try:
            payload = await futures_api.build_futures_overview(symbol)
            if isinstance(payload, dict):
                data = payload.get("data")
                meta = payload.get("meta")
                if isinstance(meta, dict):
                    ts = _parse_time(meta.get("timestamp"))
        except Exception as exc:
            logger.warning("command_view_futures_failed", symbol=symbol, error=str(exc)[:150])
        if _futures_has_data(data):
            values[symbol] = data
            if ts is not None and (oldest is None or ts < oldest):
                oldest = ts
        else:
            values[symbol] = None

    _futures_cache["default"] = (time.monotonic(), values, oldest)
    return values, oldest


async def _get_event_risk_overlay() -> tuple[dict[str, Any] | None, datetime | None]:
    """Event-aware risk overlay, cached 60s, fail-open to `null`.

    Same service call the `/api/v1/events/risk/overlay` route serves
    (initializer included); a failure caches `None` so the ~2s stream cadence
    does not hammer a broken event engine.
    """
    cached = _event_risk_cache.get("default")
    now = time.monotonic()
    if cached is not None and now - cached[0] < EVENT_RISK_FRESH_TTL:
        return cached[1], cached[2]

    payload: dict[str, Any] | None = None
    ts: datetime | None = None
    try:
        if not event_engine_service._initialized:
            await event_engine_service.initialize()
        result = event_engine_service.get_risk_overlay(underlying=EVENT_RISK_UNDERLYING)
        if hasattr(result, "model_dump"):
            result = result.model_dump(mode="json")
        if isinstance(result, dict):
            payload = result
            ts = _parse_time(payload.get("evaluated_at"))
    except Exception as exc:
        logger.warning("command_view_event_risk_failed", error=str(exc)[:150])

    _event_risk_cache["default"] = (time.monotonic(), payload, ts)
    return payload, ts


async def _leg_market() -> _Leg:
    summary = await _get_summary()
    leg_errors = {
        key: summary.errors[key]
        for key in ("cards", "breadth", "status")
        if key in summary.errors
    }
    if not summary.cards and "cards" not in leg_errors:
        leg_errors["cards"] = "Index cards unavailable"
    if summary.breadth is None and "breadth" not in leg_errors:
        leg_errors["breadth"] = "Market breadth unavailable"
    if summary.market_status is None and "status" not in leg_errors:
        leg_errors["status"] = "Market status unavailable"
    return _Leg(
        value={
            "cards": summary.cards,
            "breadth": summary.breadth,
            "market_status": summary.market_status,
        },
        updated_at=_parse_time(summary.generated_at),
        degraded=bool(leg_errors),
        error=_join_errors(leg_errors),
    )


async def _leg_regime() -> _Leg:
    summary = await _get_summary()
    futures, futures_ts = await _get_futures_overviews()
    leg_errors = {
        key: summary.errors[key]
        for key in ("regime", "options")
        if key in summary.errors
    }
    if summary.regime_overview is None and "regime" not in leg_errors:
        leg_errors["regime"] = "Regime classification unavailable"
    if summary.options_analytics is None and "options" not in leg_errors:
        leg_errors["options"] = "Options analytics unavailable"
    # Futures is an optional overlay: the engine self-describes as UNAVAILABLE
    # until a broker feed is wired, and `value.futures` carries explicit nulls.
    # Deliberately not section-degrading — a permanent degraded badge on the
    # regime card for an optional leg would train operators to ignore
    # degradation signals.
    updated_at = _parse_time(summary.generated_at)
    if futures_ts is not None and (updated_at is None or futures_ts < updated_at):
        updated_at = futures_ts

    return _Leg(
        value={
            "regime_overview": summary.regime_overview,
            "options_analytics": summary.options_analytics,
            "futures": futures,
        },
        updated_at=updated_at,
        degraded=bool(leg_errors),
        error=_join_errors(leg_errors),
    )


async def _leg_ml() -> _Leg:
    summary = await _get_summary()
    leg_errors = {"ml": summary.errors["ml"]} if "ml" in summary.errors else {}
    if summary.ml_prediction is None and not leg_errors:
        leg_errors["ml"] = "ML prediction unavailable"
    return _Leg(
        value={"ml_prediction": summary.ml_prediction},
        updated_at=_parse_time(summary.generated_at),
        degraded=bool(leg_errors),
        error=_join_errors(leg_errors),
    )


async def _leg_risk_events() -> _Leg:
    summary = await _get_summary()
    event_risk, event_ts = await _get_event_risk_overlay()
    leg_errors = {"fii_dii": summary.errors["fii_dii"]} if "fii_dii" in summary.errors else {}
    if summary.fii_dii is None and not leg_errors:
        leg_errors["fii_dii"] = "FII/DII data unavailable"
    if event_risk is None:
        leg_errors["event_risk"] = "Event risk overlay unavailable"

    updated_at = _parse_time(summary.generated_at)
    if event_ts is not None and (updated_at is None or event_ts < updated_at):
        updated_at = event_ts

    return _Leg(
        value={"fii_dii": summary.fii_dii, "event_risk": event_risk},
        updated_at=updated_at,
        degraded=bool(leg_errors),
        error=_join_errors(leg_errors),
    )


async def _leg_signals() -> _Leg:
    payload = await _get_active_signals()
    quote_errors = payload.get("errors") or {}
    degraded = bool(quote_errors) or bool(payload.get("degraded_underlyings")) or (
        str(payload.get("data_quality", "")).upper() == "DEGRADED"
    )
    return _Leg(
        value=payload,
        updated_at=_parse_time(payload.get("timestamp_ms")),
        degraded=degraded,
        error=_join_errors(quote_errors) or ("Active signal quotes degraded" if degraded else None),
    )


async def _leg_feed_health() -> _Leg:
    payload = await health_api.health_subsystems()
    return _Leg(value=payload, updated_at=_parse_time(payload.get("timestamp")))


async def _leg_kill_switch() -> _Leg:
    # Same call the `/api/v1/signals/kill-switch` endpoint serves.
    return _Leg(value=kill_switch.status(), updated_at=_now())


_LEGS: dict[str, Callable[[], Awaitable[_Leg]]] = {
    "market": _leg_market,
    "regime": _leg_regime,
    "signals": _leg_signals,
    "feed_health": _leg_feed_health,
    "kill_switch": _leg_kill_switch,
    "ml": _leg_ml,
    "risk_events": _leg_risk_events,
}


async def _compose_command_view() -> dict[str, Any]:
    """Gather every leg independently; one failure never breaks the view."""
    now = _now()
    names = list(SECTION_KEYS)
    results = await asyncio.gather(*(_LEGS[name]() for name in names), return_exceptions=True)

    sections: dict[str, Any] = {}
    errors: dict[str, str] = {}
    degraded = False

    for name, result in zip(names, results):
        if isinstance(result, BaseException):
            if isinstance(result, asyncio.CancelledError):
                raise result
            logger.warning("command_view_leg_failed", section=name, error=str(result)[:200])
            leg = _Leg(
                value=None,
                updated_at=now,
                degraded=True,
                error=f"{type(result).__name__}: {str(result)[:150]}",
            )
        else:
            leg = result

        updated_at = leg.updated_at or now
        sections[name] = {
            "value": leg.value,
            "updated_at": _iso(updated_at),
            "freshness_s": int(max(0.0, (now - updated_at).total_seconds())),
            "degraded": leg.degraded,
            "version": _section_version(name, leg.value),
        }
        if leg.degraded:
            degraded = True
            errors[name] = leg.error or "Section unavailable"

    return {
        "view": VIEW_NAME,
        "view_version": VIEW_VERSION,
        "generated_at": _iso(now),
        "sections": sections,
        "hints": [],
        "errors": errors,
        "degraded": degraded,
    }


async def compose_command_view() -> dict[str, Any]:
    """Public composition entry point for the app stream broadcaster.

    Returns exactly the same envelope as ``GET /api/v1/view/command`` — it is a
    thin alias over ``_compose_command_view`` so the endpoint's response
    semantics cannot drift from the stream's section view.
    """
    return await _compose_command_view()


@router.get("/command")
async def get_command_view() -> dict[str, Any]:
    """Frozen CommandView v1 — fail-open per section, never fabricates data."""
    return await _compose_command_view()
