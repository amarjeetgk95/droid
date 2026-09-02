from fastapi import APIRouter, Query
from app.instruments.search import search
from app.instruments.schemas import InstrumentSearchResponse
from datetime import datetime, timezone
from app.models.market import ApiMeta, DataStatus

router = APIRouter(prefix="/api/v1/instruments", tags=["instruments"])

def _meta():
    return ApiMeta(provider="instrument_registry", timestamp=datetime.now(timezone.utc), status=DataStatus.OFFLINE)

@router.get("/search")
async def search_instruments_endpoint(
    q: str = Query(default="", description="Search query"),
    asset_class: str | None = Query(default=None),
    exchange: str | None = Query(default=None),
    instrument_type: str | None = Query(default=None),
    fno_only: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=50),
):
    query = q.strip() if q else ""
    results = search(query, asset_class, exchange, instrument_type, fno_only, limit)
    # Registry is already restricted to 7; no additional filtering needed.
    return {
        "data": {"query": query, "results": [r.model_dump() for r in results], "total": len(results)},
        "error": None,
        "meta": _meta().model_dump(mode="json"),
    }
