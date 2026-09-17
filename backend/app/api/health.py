from fastapi import APIRouter
from fastapi.responses import JSONResponse
from app.services.market_service import MarketService
from datetime import datetime, timezone

router = APIRouter(tags=["health"])


@router.get("/health")
@router.get("/health/live")
async def health_live():
    """Liveness check — process is running."""
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/health/ready")
async def health_ready():
    """Readiness check — dependencies are usable.

    Truth-of-Wall: this is an honest aggregate, never a hardcoded "ok".
    Reuses the same real probes /health/subsystems computes; ready is its
    summarizing gate. The central market-data feed is the hard gate: if it is
    not running, the platform is blind and readiness must say so with a 503
    (so orchestrators, uptime monitors and watchdogs actually see it).

    Broker token status is reported informationally rather than gating: a dev
    environment legitimately runs with no token, and the data layer already
    fails closed to OFFLINE — faking readiness here would defeat both.
    """
    from app.services.central_feed import central_feed
    from app.core.broker_runtime import get_config

    checks: dict[str, object] = {}

    try:
        checks["central_feed"] = "ok" if bool(getattr(central_feed, "_running", False)) else "down"
    except Exception:
        checks["central_feed"] = "unknown"

    try:
        cfg = get_config()
        raw_token = (cfg.credentials.get("access_token") or "")
        try:
            from app.core.broker_runtime import is_usable_access_token
            usable = is_usable_access_token(raw_token)
        except Exception:
            usable = bool(raw_token)
        checks["broker_token"] = "present" if usable else ("placeholder" if raw_token else "missing")
    except Exception:
        checks["broker_token"] = "unknown"

    timestamp = datetime.now(timezone.utc).isoformat()
    if checks["central_feed"] == "ok":
        return {"status": "ok", "timestamp": timestamp, "checks": checks}
    return JSONResponse(
        status_code=503,
        content={"status": "unavailable", "timestamp": timestamp, "checks": checks},
    )


@router.get("/health/subsystems")
async def health_subsystems():
    """Diagnostic check of all running backend elements."""
    from app.services.central_feed import central_feed
    from app.core.config import settings
    from app.core.broker_runtime import get_config

    elements = {
        "server": True,
        "central_feed": False,
        "signal_worker": False,
        "morning_briefing": False,
        "forecast_scheduler": False,
        "flow_scheduler": False,
        "broker_configured": False,
        "token_present": False,
        "telegram_configured": bool(settings.telegram_bot_token),
    }

    try:
        elements["central_feed"] = bool(getattr(central_feed, "_running", False))
    except Exception:
        pass

    try:
        from app.signals.worker import automated_signal_worker
        elements["signal_worker"] = bool(getattr(automated_signal_worker, "_running", False))
    except Exception:
        pass

    try:
        from app.services.morning_briefing_service import morning_briefing_service
        elements["morning_briefing"] = bool(getattr(morning_briefing_service, "_running", False))
    except Exception:
        pass

    try:
        from app.research.scheduler import scheduler_enabled
        elements["forecast_scheduler"] = bool(scheduler_enabled())
    except Exception:
        pass

    try:
        from app.institutional.scheduler import enabled as flow_enabled
        elements["flow_scheduler"] = bool(flow_enabled())
    except Exception:
        pass

    try:
        cfg = get_config()
        elements["broker_configured"] = bool(cfg.credentials.get("app_id"))
        # Fyers-only policy posture: "ok:fyers" | "rejected:<value>" | "unset".
        try:
            from app.providers.registry import get_broker_provider_status
            elements["broker_provider_status"] = get_broker_provider_status()
        except Exception:
            elements["broker_provider_status"] = "unknown"
        raw_token = (cfg.credentials.get("access_token") or "")
        try:
            from app.core.broker_runtime import is_usable_access_token
            usable = is_usable_access_token(raw_token)
        except Exception:
            usable = bool(raw_token)
        elements["token_present"] = bool(usable)
        # Explicit status so dashboards can distinguish "no token" from a
        # stored placeholder (e.g. test fixture) that can never authenticate.
        elements["token_status"] = (
            "present" if usable else ("placeholder" if raw_token else "missing")
        )
    except Exception:
        pass

    # Inbound tick-sanity rejections (Truth of Wall): sustained rejections
    # mean the feed is producing implausible quotes — downstream is seeing
    # gaps, not data. A nonzero value here is a loud, honest signal.
    try:
        from app.providers.registry import get_provider
        elements["tick_sanity_rejections"] = int(get_provider().sanity_rejection_count() or 0)
    except Exception:
        pass

    # ── Chain freshness & mark provenance ──
    # An expired FYERS token makes every signal scan return [] — which is
    # indistinguishable from "no setups today". These fields let a caller tell
    # CHAIN_UNAVAILABLE (we could not price anything) from NO_SETUPS.
    try:
        from app.signals.live_contract_cache import live_contract_cache
        from app.signals.option_marks import option_mark_registry

        stats = live_contract_cache.stats()
        strikes = int(stats.get("strikes", 0) or 0)
        age_ms = int(stats.get("age_ms", -1))
        elements["chain_strikes"] = strikes
        elements["chain_age_ms"] = age_ms
        elements["chain_status"] = (
            "FRESH" if strikes and 0 <= age_ms <= 180_000
            else ("STALE" if strikes else "UNAVAILABLE")
        )

        mark_stats = option_mark_registry.stats()
        by_source = dict(mark_stats.get("by_source", {}) or {})
        elements["option_marks"] = int(mark_stats.get("marks", 0) or 0)
        elements["option_mark_sources"] = by_source
        # MODEL_ONLY is a loud state: marks exist but none is a broker print, so
        # execution will (correctly) reject every signal until the chain returns.
        elements["chain_mark_status"] = (
            "LIVE" if (by_source.get("CHAIN_BIDASK", 0) + by_source.get("CHAIN_LTP", 0)) > 0
            else ("MODEL_ONLY" if by_source.get("MODEL_BLACK76", 0) > 0 else "NONE")
        )
    except Exception:
        pass

    return {
        "status": "ok",
        "elements": elements,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }



@router.get("/api/v1/health/market-data")
async def market_data_health():
    """Market data health status (fail-open: never 500s on degraded feed)."""
    from app.models.market import MarketHealthStatus
    try:
        service = MarketService()
        health = await service.get_health()
        if health is None:
            raise ValueError("health_unavailable")
        # Coordinator cache may hold a plain dict from an older deployment /
        # Redis pickle — accept both so a shape mismatch never looks like the
        # broker gateway is down.
        if isinstance(health, dict):
            return MarketHealthStatus(**health).model_dump()
        return health.model_dump()
    except Exception as e:
        fallback = MarketHealthStatus(
            status="DEGRADED",
            provider="fyers",
            mode="OFFLINE",
            last_update=datetime.now(timezone.utc),
            message=f"Health probe degraded: {str(e)[:150]}",
        )
        return fallback.model_dump()


@router.get("/api/v1/health/database")
@router.get("/health/db")
async def database_health():
    """Verify live Supabase database connectivity and row counts."""
    from app.core.database import get_async_session_factory
    from app.core.config import settings
    from sqlalchemy import text

    factory = get_async_session_factory()
    if factory is None:
        return {
            "status": "error",
            "connected": False,
            "error": "No database factory (DATABASE_URL empty or invalid)",
            "configured": bool(settings.database_url),
        }
    try:
        async with factory() as session:
            res = await session.execute(text("SELECT current_database(), current_user, inet_server_addr()"))
            row = res.first()
            cnt_sig = await session.execute(text("SELECT count(*) FROM executed_signals"))
            cnt_algo = await session.execute(text("SELECT count(*) FROM algo_signals"))
            return {
                "status": "ok",
                "connected": True,
                "database": row[0] if row else None,
                "user": row[1] if row else None,
                "server": str(row[2]) if row else None,
                "counts": {
                    "executed_signals": cnt_sig.scalar(),
                    "algo_signals": cnt_algo.scalar(),
                },
            }
    except Exception as e:
        return {
            "status": "error",
            "connected": False,
            "error": str(e),
            "configured": bool(settings.database_url),
        }
