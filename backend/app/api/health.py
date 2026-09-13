from fastapi import APIRouter
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
    """Readiness check — dependencies are usable."""
    # Phase 1: no external dependencies required
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {
            "provider": "ok",
        }
    }


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
        elements["token_present"] = bool(cfg.credentials.get("access_token"))
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
