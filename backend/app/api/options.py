from datetime import datetime, timezone
from fastapi import APIRouter, Query, HTTPException
from app.services.options_service import options_service
from app.models.market import ApiMeta, DataStatus

router = APIRouter(prefix="/api/v1/options", tags=["options"])


def _make_meta() -> ApiMeta:
    return ApiMeta(
        provider="options_quant_engine",
        timestamp=datetime.now(timezone.utc),
        status=DataStatus.DEMO,
    )


@router.get("/{symbol}/chain")
async def get_option_chain(
    symbol: str,
    expiry: str | None = Query(default=None, description="Expiry date in YYYY-MM-DD format"),
):
    """Retrieve full interactive option chain strike ladder with Greeks and IV."""
    try:
        chain = await options_service.get_option_chain_matrix(symbol, expiry)
        return {
            "data": chain.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/analytics")
async def get_options_analytics(
    symbol: str,
    expiry: str | None = Query(default=None, description="Expiry date in YYYY-MM-DD format"),
):
    """Retrieve composite options analytics (PCR, Max Pain, ATM IV, Skew)."""
    try:
        chain = await options_service.get_option_chain_matrix(symbol, expiry)
        return {
            "data": chain.analytics.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/max-pain")
async def get_max_pain(
    symbol: str,
    expiry: str | None = Query(default=None, description="Expiry date in YYYY-MM-DD format"),
):
    """Retrieve Max Pain strike and full payout curve across strikes."""
    try:
        max_pain = await options_service.calculate_max_pain(symbol, expiry)
        return {
            "data": max_pain.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
