from fastapi import APIRouter
from app.core.cache import cache_service
from app.models.market import ApiMeta, DataStatus
from datetime import datetime, timezone

router = APIRouter(prefix="/api/v1/cache", tags=["cache"])


def _make_meta() -> ApiMeta:
    return ApiMeta(
        provider="system_cache",
        timestamp=datetime.now(timezone.utc),
        status=DataStatus.LIVE,
    )


@router.get("/stats")
async def get_cache_stats():
    """Retrieve cache hit ratio, eviction metrics, and memory utilization."""
    stats = cache_service.get_stats()
    return {
        "data": stats,
        "error": None,
        "meta": _make_meta().model_dump(),
    }


@router.post("/clear")
async def clear_cache():
    """Flush all cached entries."""
    await cache_service.clear()
    return {
        "data": {"cleared": True},
        "error": None,
        "meta": _make_meta().model_dump(),
    }
