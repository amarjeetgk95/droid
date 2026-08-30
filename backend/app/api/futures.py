from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from app.services.futures_service import futures_service
from app.models.market import ApiMeta, DataStatus

router = APIRouter(prefix="/api/v1/futures", tags=["futures"])


def _make_meta() -> ApiMeta:
    return ApiMeta(
        provider="futures_quant_engine",
        timestamp=datetime.now(timezone.utc),
        status=DataStatus.DEMO,
    )


@router.get("/{symbol}/overview")
async def get_futures_overview(symbol: str):
    """Retrieve composite Futures overview with Term Structure, Buildup, and Rollover."""
    try:
        overview = await futures_service.get_futures_overview(symbol)
        return {
            "data": overview.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/term-structure")
async def get_term_structure(symbol: str):
    """Retrieve Near, Next, and Far term structure curve and calendar spreads."""
    try:
        term = await futures_service.get_term_structure(symbol)
        return {
            "data": term.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/buildup")
async def get_oi_buildup(symbol: str):
    """Retrieve 4-Quadrant Open Interest buildup classification."""
    try:
        overview = await futures_service.get_futures_overview(symbol)
        return {
            "data": overview.buildup.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/rollover")
async def get_rollover(symbol: str):
    """Retrieve Rollover percentage, spread cost, and benchmark pace."""
    try:
        rollover = await futures_service.get_rollover_metrics(symbol)
        return {
            "data": rollover.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
