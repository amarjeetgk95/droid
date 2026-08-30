from datetime import date
from fastapi import APIRouter, HTTPException, Query
from app.services.contract_master import contract_master_service
from app.models.contracts import ContractType, OptionType, ContractStatus, ExpiryResolution
from app.models.market import ApiResponse, ApiMeta, DataStatus
from datetime import datetime, timezone

router = APIRouter(prefix="/api/v1/contracts", tags=["contracts"])


def _make_meta() -> ApiMeta:
    return ApiMeta(
        provider="fyers",
        timestamp=datetime.now(timezone.utc),
        status=DataStatus.DEMO,
     )


@router.get("/search")
async def search_contracts(
    underlying: str | None = None,
    contract_type: ContractType | None = None,
    expiry: date | None = None,
    strike: float | None = None,
    option_type: OptionType | None = None,
):
    """Query data-driven contract master catalog."""
    contracts = contract_master_service.search_contracts(
        underlying=underlying.upper() if underlying else None,
        contract_type=contract_type,
        expiry=expiry,
        strike=strike,
        option_type=option_type,
    )
    return {
        "data": [c.model_dump(mode="json") for c in contracts],
        "error": None,
        "meta": _make_meta().model_dump(),
    }


@router.get("/{symbol}/expiries")
async def get_contract_expiries(symbol: str):
    """Resolve dynamic expiries without hardcoded weekdays."""
    underlying = symbol.upper().replace(" 50", "")
    resolution = contract_master_service.resolve_expiries(underlying)
    return {
        "data": resolution.model_dump(mode="json"),
        "error": None,
        "meta": _make_meta().model_dump(),
    }


@router.get("/{symbol}/master")
async def get_contract_master(symbol: str):
    """Get contract master details by exact symbol."""
    contract = contract_master_service.get_by_symbol(symbol)
    if not contract:
        raise HTTPException(status_code=404, detail=f"Contract not found: {symbol}")
    return {
        "data": contract.model_dump(mode="json"),
        "error": None,
        "meta": _make_meta().model_dump(),
    }
