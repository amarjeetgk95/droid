from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from app.services.fii_dii_service import fii_dii_service
from app.models.market import ApiMeta, DataStatus

router = APIRouter(prefix="/api/v1/fii-dii", tags=["fii-dii"])


def _make_meta() -> ApiMeta:
    return ApiMeta(
        provider="institutional_derivatives_tracker",
        timestamp=datetime.now(timezone.utc),
        status=DataStatus.OFFLINE,
    )


@router.get("/overview")
async def get_fii_dii_overview():
    """Retrieve institutional FII/DII net derivatives positioning and cash turnover."""
    try:
        overview = fii_dii_service.get_institutional_overview()
        return {
            "data": overview.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
