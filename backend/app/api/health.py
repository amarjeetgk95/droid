from fastapi import APIRouter
from app.services.market_service import MarketService
from datetime import datetime, timezone

router = APIRouter(tags=["health"])


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
