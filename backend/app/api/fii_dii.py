from fastapi import APIRouter
from app.api.envelope import envelope
from app.models.market import DataStatus
from app.services.fii_dii_service import fii_dii_service

router = APIRouter(prefix="/api/v1/fii-dii", tags=["fii-dii"])

_PROVIDER = "institutional_derivatives_tracker"


@router.get("/overview")
async def get_fii_dii_overview():
    """Retrieve institutional FII/DII net derivatives positioning and cash turnover."""
    overview = fii_dii_service.get_institutional_overview()
    return envelope(overview, provider=_PROVIDER, status=DataStatus.OFFLINE)
