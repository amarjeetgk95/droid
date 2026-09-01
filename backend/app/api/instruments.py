from fastapi import APIRouter, Query
from app.instruments.search import search
from app.instruments.schemas import InstrumentSearchResponse
from datetime import datetime, timezone
from app.models.market import ApiMeta, DataStatus
from app.instruments.registry import CHART_ANALYSIS_UNIVERSE, get_chart_analysis_universe

router = APIRouter(prefix="/api/v1/instruments", tags=["instruments"])

def _meta():
    return ApiMeta(provider="instrument_registry", timestamp=datetime.now(timezone.utc), status=DataStatus.OFFLINE)

# Allowed selectors for chart-analysis context must be restricted upstream by caller.
# Search itself remains generic (restricted registry is now 7 only), but we
# expose an explicit chart-analysis universe endpoint so frontends cannot
# dynamically discover outside instruments.

@router.get("/chart-analysis-universe")
async def chart_analysis_universe():
    """Fixed 7-instrument universe for Chart Analysis selector (no substitution)."""
    cfgs = get_chart_analysis_universe()
    return {
        "data": {
            "universe": CHART_ANALYSIS_UNIVERSE,
            "instruments": [
                {
                    "symbol": c.symbol,
                    "display_name": c.display_name,
                    "asset_class": c.asset_class,
                    "exchange": c.exchange,
                    "instrument_type": c.instrument_type,
                    "fno_available": c.fno_available,
                    "supported_timeframes": c.supported_timeframes,
                    "data_provider_symbol": c.data_provider_symbol,
                }
                for c in cfgs
            ],
            "timeframes": ["1m", "5m", "15m", "1h", "4h", "1D"],
            "note": "Chart Analysis is permanently restricted to these seven derivatives. Data unavailable → 'Data unavailable' without substitution.",
        },
        "error": None,
        "meta": _meta().model_dump(mode="json"),
    }

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
