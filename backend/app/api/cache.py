from fastapi import APIRouter
from app.api.envelope import envelope
from app.core.cache import cache_service

router = APIRouter(prefix="/api/v1/cache", tags=["cache"])

_PROVIDER = "system_cache"


@router.get("/stats")
async def get_cache_stats():
    """Retrieve cache hit ratio, eviction metrics, and memory utilization."""
    stats = cache_service.get_stats()
    return envelope(stats, provider=_PROVIDER)


@router.post("/clear")
async def clear_cache():
    """Flush all cached entries."""
    await cache_service.clear()
    return envelope({"cleared": True}, provider=_PROVIDER)
