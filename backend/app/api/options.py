from fastapi import APIRouter, Query

from app.api.envelope import envelope
from app.models.market import DataStatus
from app.services.options_service import options_service

router = APIRouter(prefix="/api/v1/options", tags=["options"])

_PROVIDER = "options_quant_engine"


@router.get("/{symbol}/chain")
async def get_option_chain(
    symbol: str,
    expiry: str | None = Query(default=None, description="Expiry date in YYYY-MM-DD format"),
):
    """Retrieve full interactive option chain strike ladder with Greeks and IV."""
    chain = await options_service.get_option_chain_matrix(symbol, expiry)
    return envelope(chain, provider=_PROVIDER, status=DataStatus.OFFLINE)


@router.get("/{symbol}/analytics")
async def get_options_analytics(
    symbol: str,
    expiry: str | None = Query(default=None, description="Expiry date in YYYY-MM-DD format"),
):
    """Retrieve composite options analytics (PCR, Max Pain, ATM IV, Skew)."""
    chain = await options_service.get_option_chain_matrix(symbol, expiry)
    return envelope(chain.analytics, provider=_PROVIDER, status=DataStatus.OFFLINE)


@router.get("/{symbol}/max-pain")
async def get_max_pain(
    symbol: str,
    expiry: str | None = Query(default=None, description="Expiry date in YYYY-MM-DD format"),
):
    """Retrieve Max Pain strike and full payout curve across strikes."""
    max_pain = await options_service.calculate_max_pain(symbol, expiry)
    return envelope(max_pain, provider=_PROVIDER, status=DataStatus.OFFLINE)


@router.get("/{symbol}/institutional-flow")
async def get_institutional_flow(
    symbol: str,
    expiry: str | None = Query(default=None, description="Expiry date in YYYY-MM-DD format"),
):
    """Retrieve strike-by-strike institutional build-ups, unwinding, and net flow sentiment."""
    flow = await options_service.get_institutional_oi_flow(symbol, expiry)
    return envelope(flow, provider=_PROVIDER, status=DataStatus.OFFLINE)
