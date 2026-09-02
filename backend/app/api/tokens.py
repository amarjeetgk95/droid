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
    actual response.
    """
    if payload and isinstance(payload, dict):
        incoming_app = payload.get("app_settings")
        if incoming_app is None and "broker" in payload:
            incoming_app = payload
        if isinstance(incoming_app, dict) and incoming_app:
            try:
                apply_app_settings(incoming_app)
                reset_provider()
            except Exception as e:
                logger.warning("token_diagnostics_hot_sync_failed", error=str(e)[:200])

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

    token = await ensure_fn(force_refresh=True)
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
        # Full quote endpoint with the raw body so we can see exactly what
        # Groww said (including FAILURE status messages, error codes, etc.)
        norm_quote, raw_quote, status_quote = await provider.service._get_quote_with_raw(
            token, "NSE", "CASH", "NIFTY",
        )
        # LTP bulk endpoint with raw body
        raw_ltp = None
        status_ltp = None
        async_call = provider.service.get_ltp_bulk(
            token, "CASH", [INDEX_EXCHANGE_SYMBOLS["NIFTY 50"]]
        )
        ltp_map = await async_call
        # Re-fetch the raw ltp response for diagnostics
        import httpx as _httpx
        try:
            async with _httpx.AsyncClient(timeout=provider.service.DEFAULT_TIMEOUT_SECONDS) as _c:
                _r = await _c.get(
                    f"{provider.service.API_BASE}{provider.service.LTP_ENDPOINT}",
                    params={"segment": "CASH", "exchange_symbols": INDEX_EXCHANGE_SYMBOLS["NIFTY 50"]},
                    headers=provider.service._build_headers(token),
                )
                status_ltp = _r.status_code
                try:
                    raw_ltp = _r.json()
                except Exception:
                    raw_ltp = (_r.text or "")[:500]
        except Exception as e:
            raw_ltp = {"error": str(e)}

        return {
            "data": {
                "provider": "groww",
                "token_prefix": token[:12] + "...",
                "quote_call": {
                    "endpoint": "GET /v1/live-data/quote?exchange=NSE&segment=CASH&trading_symbol=NIFTY",
                    "http_status": status_quote,
                    "response_normalized": norm_quote,
                    "response_raw": raw_quote,
                    "ok": norm_quote is not None and norm_quote.get("ltp", 0) > 0,
                },
                "ltp_call": {
                    "endpoint": "GET /v1/live-data/ltp?segment=CASH&exchange_symbols=NSE_NIFTY",
                    "http_status": status_ltp,
                    "response_payload": ltp_map,
                    "response_raw": raw_ltp,
                    "ok": ltp_map.get(INDEX_EXCHANGE_SYMBOLS["NIFTY 50"]) is not None,
                },
                "diagnostics": diag,
            },
            "error": (
                None if (norm_quote and norm_quote.get("ltp", 0) > 0)
                else "Both endpoints returned no usable data — check raw_quote/raw_ltp for Groww error"
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


@router.post("/test-connection")
async def test_connection(payload: dict = Body(...)):
    """Test broker credentials in real time and return roundtrip diagnostics."""
    import time
    start = time.time()
    prov_name = (payload.get("provider") or "groww").lower()
    raw_creds = payload.get("credentials") or {}
    
    if prov_name == "groww":
        from app.services.groww_service import GrowwService
        api_key = raw_creds.get("apiKey") or raw_creds.get("api_key") or ""
        api_secret = raw_creds.get("apiSecret") or raw_creds.get("api_secret") or ""
        access_token = raw_creds.get("accessToken") or raw_creds.get("access_token") or ""
        totp = raw_creds.get("totp") or ""
        auth_mode = raw_creds.get("authMode") or "checksum"

        service = GrowwService(
            api_key=api_key,
            api_secret=api_secret,
            access_token=access_token,
            totp=totp,
            auth_mode=auth_mode,
        )

        try:
            tok = await service.fetch_access_token()
        except Exception as e:
            latency = round((time.time() - start) * 1000, 1)
            return {
                "data": {
                    "success": False,
                    "provider": "groww",
                    "latency_ms": latency,
                    "token_valid": False,
                    "quote": None,
                    "raw_response": None,
                    "error": f"Authentication failed: {e}",
                },
                "error": str(e),
                "meta": _make_meta().model_dump(),
            }

        user_info = None
        # 1. Probe user profile to confirm token validity
        import httpx
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                r_user = await client.get(
                    f"{service.API_BASE}/user/detail",
                    headers=service._build_headers(tok),
                )
                if r_user.status_code == 200:
                    user_info = r_user.json()
        except Exception:
            pass

        try:
            norm, raw, status = await service._get_quote_with_raw(tok, "NSE", "CASH", "NIFTY")
            latency = round((time.time() - start) * 1000, 1)
            is_ok = status == 200 and norm is not None and (norm.get("ltp") or 0) > 0
            err_msg = None
            if not is_ok:
                if status in (401, 403):
                    if user_info:
                        err_msg = (
                            f"HTTP 403 Forbidden: Authenticated successfully, but Live Market Data API is forbidden. "
                            f"Your Groww account requires the active Trade API Market Data / F&O subscription in the Groww Console."
                        )
                    else:
                        err_msg = (
                            f"HTTP 403 Forbidden: Access forbidden by Groww. "
                            f"Please verify that your API Key is approved for today on https://groww.in/trade-api/api-keys, "
                            f"or paste your active Daily Access Token directly into the Access Token field."
                        )
                else:
                    err_msg = f"HTTP {status} from Groww live data endpoint: {raw}"

            return {
                "data": {
                    "success": is_ok,
                    "provider": "groww",
                    "latency_ms": latency,
                    "token_valid": True,
                    "token_prefix": tok[:10] + "..." if tok else "",
                    "user_info": user_info,
                    "quote": norm,
                    "raw_response": raw,
                    "error": err_msg,
                },
                "error": err_msg,
                "meta": _make_meta().model_dump(),
            }
        except Exception as e:
            latency = round((time.time() - start) * 1000, 1)
            return {
                "data": {
                    "success": False,
                    "provider": "groww",
                    "latency_ms": latency,
                    "token_valid": True,
                    "quote": None,
                    "raw_response": None,
                    "error": f"Quote probe failed: {e}",
                },
                "error": str(e),
                "meta": _make_meta().model_dump(),
            }
    
    elif prov_name == "binance":
        import httpx
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT")
                latency = round((time.time() - start) * 1000, 1)
                data = r.json() if r.status_code == 200 else None
                return {
                    "data": {
                        "success": r.status_code == 200,
                        "provider": "binance",
                        "latency_ms": latency,
                        "token_valid": True,
                        "quote": {"symbol": "BTC/USDT", "ltp": float(data["price"])} if data else None,
                        "raw_response": data,
                        "error": None if r.status_code == 200 else f"HTTP {r.status_code}",
                    },
                    "error": None,
                    "meta": _make_meta().model_dump(),
                }
        except Exception as e:
            latency = round((time.time() - start) * 1000, 1)
            return {
                "data": {
                    "success": False,
                    "provider": "binance",
                    "latency_ms": latency,
                    "token_valid": False,
                    "error": str(e),
                },
                "error": str(e),
                "meta": _make_meta().model_dump(),
            }

    # Generic fallback
    latency = round((time.time() - start) * 1000, 1)
    return {
        "data": {
            "success": True,
            "provider": prov_name,
            "latency_ms": latency,
            "token_valid": True,
            "quote": None,
            "raw_response": None,
            "error": None,
        },
        "error": None,
        "meta": _make_meta().model_dump(),
    }
