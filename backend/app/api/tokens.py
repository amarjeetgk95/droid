from fastapi import APIRouter, Body
from app.providers.registry import get_provider, reset_provider
from app.core.broker_runtime import apply_app_settings
from app.core.token_manager import ConnectionState
from app.models.market import ApiMeta, DataStatus
from datetime import datetime, timezone
import structlog

logger = structlog.get_logger()

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
async def refresh_token(payload: dict | None = Body(default=None)):
    """Trigger a manual token refresh / broker re-authentication.

    For key/secret providers that support on-demand auth (Kotak Neo two-step
    TOTP+MPIN, Groww checksum), this drives the login flow and stores the
    resulting access token. OAuth-based providers (Fyers/Upstox) require the
    interactive redirect flow and will report AUTH_EXPIRED when no refreshable
    token is present.

    If the frontend sends its current `app_settings` in the request body
    (dirty local settings not yet saved to Supabase), we apply them first so
    a `Force Refresh` immediately targets the selected provider (e.g. Groww)
    instead of the stale cached provider (e.g. Fyers) — fixes
    "Re-authentication required for fyers" when input is groww.
    """
    # Hot-sync: if frontend supplied fresh app_settings, promote to active config
    if payload and isinstance(payload, dict):
        incoming_app = payload.get("app_settings")
        # Also accept flat broker payload for resilience
        if incoming_app is None and "broker" in payload:
            incoming_app = payload
        if isinstance(incoming_app, dict) and incoming_app:
            try:
                apply_app_settings(incoming_app)
                reset_provider()
                logger.info("token_refresh_hot_sync", provider=incoming_app.get("broker", {}).get("provider"))
            except Exception as e:
                logger.warning("token_refresh_hot_sync_failed", error=str(e)[:200])

    provider = get_provider()
    token_mgr = provider.get_token_manager()

    if token_mgr._refresh_callback is not None:
        try:
            info = await token_mgr._refresh_callback()
            token = info.access_token if info else ""
            return {
                "data": {
                    "refreshed": bool(token),
                    "provider": provider.provider_name,
                    "has_token": bool(token),
                    "auth_method": "programmatic_login",
                },
                "error": None,
                "meta": _make_meta().model_dump(),
            }
        except RuntimeError as e:
            token_mgr.mark_expired(str(e))
            return {
                "data": {
                    "refreshed": False,
                    "provider": provider.provider_name,
                    "has_token": False,
                    "auth_method": "programmatic_login",
                },
                "error": str(e),
                "meta": _make_meta().model_dump(),
            }

    try:
        token = await token_mgr.get_valid_token()
        refreshed = bool(token) and token_mgr.state == ConnectionState.CONNECTED
    except RuntimeError as e:
        return {
            "data": {
                "refreshed": False,
                "provider": provider.provider_name,
                "has_token": False,
                "auth_method": "oauth_callback_required",
                "state": token_mgr.state.value if token_mgr.state else None,
            },
            "error": str(e),
            "meta": _make_meta().model_dump(),
        }

    return {
        "data": {
            "refreshed": refreshed,
            "provider": provider.provider_name,
            "has_token": bool(token),
        },
        "error": None,
        "meta": _make_meta().model_dump(),
    }
