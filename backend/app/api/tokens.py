from fastapi import APIRouter
from app.providers.registry import get_provider
from app.models.market import ApiMeta, DataStatus
from datetime import datetime, timezone

router = APIRouter(prefix="/api/v1/tokens", tags=["tokens"])


def _make_meta() -> ApiMeta:
    return ApiMeta(
        provider="system",
        timestamp=datetime.now(timezone.utc),
        status=DataStatus.LIVE,
    )


@router.get("/status")
async def get_token_status():
    """Get active broker token lifecycle status and telemetry."""
    provider = get_provider()
    token_mgr = provider.get_token_manager()
    diagnostics = token_mgr.get_diagnostics()
    return {
        "data": diagnostics,
        "error": None,
        "meta": _make_meta().model_dump(),
    }


@router.post("/refresh")
async def refresh_token():
    """Trigger manual token refresh or check validity."""
    provider = get_provider()
    token_mgr = provider.get_token_manager()
    token = await token_mgr.get_valid_token()
    return {
        "data": {
            "refreshed": True,
            "provider": provider.provider_name,
            "has_token": bool(token),
        },
        "error": None,
        "meta": _make_meta().model_dump(),
    }
