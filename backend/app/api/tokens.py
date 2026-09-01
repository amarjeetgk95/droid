from fastapi import APIRouter, Body
from app.providers.registry import get_provider, reset_provider, stop_previous_provider_stream
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


@router.post("/diagnostics")
async def run_token_diagnostics(payload: dict | None = Body(default=None)):
    """Run a live Groww API call with the saved credentials and return the
    actual response — useful when the dashboard shows OFFLINE/0 and you want
    to know whether it's a token problem, an endpoint problem, or something
    else.

    For Groww specifically, this:
      1. Eagerly fetches a fresh access token (bypasses the 30s rate-limit
         guard used by the streaming refresh callback).
      2. Calls /v1/live-data/quote for NIFTY 50 with that token.
      3. Returns the raw Groww response so the caller can see exactly what
         Groww returned (or why it failed).

    For other providers, falls back to a generic refresh test.
    """
    provider = get_provider()
    token_mgr = provider.get_token_manager()
    diag = token_mgr.get_diagnostics()

    if provider.provider_name != "groww":
        # Generic path — just attempt refresh and return
        try:
            info = await token_mgr._refresh_callback() if token_mgr._refresh_callback else None
            return {
                "data": {
                    "provider": provider.provider_name,
                    "refreshed": bool(info),
                    "diagnostics": diag,
                },
                "error": None,
                "meta": _make_meta().model_dump(),
            }
        except Exception as e:
            return {
                "data": {"provider": provider.provider_name, "diagnostics": diag, "refreshed": False},
                "error": str(e),
                "meta": _make_meta().model_dump(),
            }

    # Groww-specific: fetch fresh token, then call /live-data/quote
    ensure_fn = getattr(provider, "ensure_access_token", None)
    if not callable(ensure_fn):
        return {
            "data": {"provider": "groww", "diagnostics": diag},
            "error": "Groww provider does not expose ensure_access_token",
            "meta": _make_meta().model_dump(),
        }

    token = await ensure_fn()
    if not token:
        return {
            "data": {
                "provider": "groww",
                "diagnostics": diag,
                "auth_error": getattr(provider, "_last_auth_error", "unknown"),
            },
            "error": getattr(provider, "_last_auth_error", "failed to fetch Groww access token"),
            "meta": _make_meta().model_dump(),
        }

    # We have a token — try both LTP bulk and full quote endpoints to verify
    # which one Groww actually supports for indices. The LTP bulk docs only
    # show stock examples; the full quote endpoint uses trading_symbol=NIFTY
    # which is the documented path for indices.
    try:
        from app.services.groww_service import INDEX_EXCHANGE_SYMBOLS
        # Try full quote endpoint first (the documented path for indices)
        full_quote = await provider.service.get_quote(
            token, "NSE", "CASH", "NIFTY",
        )
        # Also try LTP bulk for comparison
        ltp_map = await provider.service.get_ltp_bulk(
            token, "CASH", [INDEX_EXCHANGE_SYMBOLS["NIFTY 50"]]
        )
        ltp_val = ltp_map.get(INDEX_EXCHANGE_SYMBOLS["NIFTY 50"])

        return {
            "data": {
                "provider": "groww",
                "token_prefix": token[:12] + "...",
                "quote_call": {
                    "endpoint": "GET /v1/live-data/quote?exchange=NSE&segment=CASH&trading_symbol=NIFTY",
                    "response_normalized": full_quote,
                    "ok": full_quote is not None and full_quote.get("ltp", 0) > 0,
                },
                "ltp_call": {
                    "endpoint": "GET /v1/live-data/ltp?segment=CASH&exchange_symbols=NSE_NIFTY",
                    "response_payload": ltp_map,
                    "ok": ltp_val is not None and ltp_val > 0,
                },
                "diagnostics": diag,
            },
            "error": (
                None if (full_quote and full_quote.get("ltp", 0) > 0)
                else "Both endpoints returned no data for NIFTY 50 — check token scopes/daily approval"
            ),
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        return {
            "data": {
                "provider": "groww",
                "token_prefix": token[:12] + "...",
                "diagnostics": diag,
            },
            "error": f"token fetched but live-data calls failed: {str(e)[:200]}",
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
                # Stop the previous provider's stream before swapping so its
                # background task doesn't keep producing ticks for the discarded
                # instance.
                await stop_previous_provider_stream()
                reset_provider()
                logger.info("token_refresh_hot_sync", provider=incoming_app.get("broker", {}).get("provider"))
            except Exception as e:
                logger.warning("token_refresh_hot_sync_failed", error=str(e)[:200])

    provider = get_provider()
    # Ensure the (possibly newly created) provider's stream is running so
    # MARKET_TICKS resumes immediately after a provider swap (e.g. Fyers -> Groww).
    try:
        if not getattr(provider, "_stream_running", False):
            await provider.start_stream()
    except Exception as e:
        logger.warning("token_refresh_start_stream_failed", error=str(e)[:200])
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
