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


@router.get("/api/v1/health/market-data")
async def market_data_health():
    """Market data health status."""
    service = MarketService()
    health = await service.get_health()
    return health.model_dump()


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
            cnt_hpi = await session.execute(text("SELECT count(*) FROM hpi_datasets"))
            cnt_algo = await session.execute(text("SELECT count(*) FROM algo_signals"))
            return {
                "status": "ok",
                "connected": True,
                "database": row[0] if row else None,
                "user": row[1] if row else None,
                "server": str(row[2]) if row else None,
                "counts": {
                    "executed_signals": cnt_sig.scalar(),
                    "hpi_datasets": cnt_hpi.scalar(),
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
