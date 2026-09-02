from fastapi import APIRouter, Body, Request, Query
from fastapi.responses import HTMLResponse
from app.providers.registry import get_provider, reset_provider, stop_previous_provider_stream
from app.core.broker_runtime import apply_app_settings, get_config
from app.core.token_manager import ConnectionState, TokenInfo
from app.models.market import ApiMeta, DataStatus
from app.core.config import settings as cfg
from datetime import datetime, timezone, timedelta
import hashlib
import httpx
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
    """Run a live API diagnostic call with the saved credentials."""
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


@router.post("/refresh")
async def refresh_token(payload: dict | None = Body(default=None)):
    """Trigger a manual token refresh / broker re-authentication."""
    if payload and isinstance(payload, dict):
        incoming_app = payload.get("app_settings")
        if incoming_app is None and "broker" in payload:
            incoming_app = payload
        if isinstance(incoming_app, dict) and incoming_app:
            try:
                apply_app_settings(incoming_app)
                await stop_previous_provider_stream()
                reset_provider()
                logger.info("token_refresh_hot_sync", provider=incoming_app.get("broker", {}).get("provider"))
            except Exception as e:
                logger.warning("token_refresh_hot_sync_failed", error=str(e)[:200])

    provider = get_provider()
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


@router.get("/fyers/callback")
async def fyers_oauth_callback(
    request: Request,
    auth_code: str | None = Query(default=None),
    code: str | None = Query(default=None),
    s: str | None = Query(default=None),
    state: str | None = Query(default=None),
    message: str | None = Query(default=None),
):
    """Handle FYERS OAuth2 redirect after user authentication.
    
    Exchanges auth_code with appIdHash (SHA-256 of app_id:secret_key)
    via POST https://api-t1.fyers.in/api/v3/validate-authcode.
    """
    effective_code = auth_code or code
    if not effective_code:
        return HTMLResponse(
            content="""
            <!DOCTYPE html>
            <html>
            <head><title>FYERS OAuth Callback</title></head>
            <body style="font-family:system-ui,-apple-system,sans-serif;background:#0f172a;color:#f8fafc;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
                <div style="background:#1e293b;padding:2rem;border-radius:12px;border:1px solid #334155;max-width:480px;text-align:center;">
                    <h2 style="color:#38bdf8;margin-top:0;">FYERS OAuth Callback Ready</h2>
                    <p style="color:#94a3b8;font-size:14px;">This endpoint is active and waiting for Fyers authentication redirects.</p>
                </div>
            </body>
            </html>
            """,
            status_code=200,
        )

    # Get active Fyers credentials
    broker_config = get_config()
    creds = broker_config.credentials if broker_config.provider == "fyers" else {}
    app_id = creds.get("app_id") or cfg.fyers_app_id
    secret_key = creds.get("secret_key") or cfg.fyers_secret_key

    if not app_id or not secret_key:
        error_html = """
        <!DOCTYPE html>
        <html>
        <head><title>FYERS Auth Error</title></head>
        <body style="font-family:system-ui,-apple-system,sans-serif;background:#0f172a;color:#f8fafc;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
            <div style="background:#1e293b;padding:2rem;border-radius:12px;border:1px solid #ef4444;max-width:480px;text-align:center;">
                <h2 style="color:#ef4444;margin-top:0;">Fyers App ID or Secret Missing</h2>
                <p style="color:#94a3b8;font-size:14px;">Received auth code, but App ID and Secret Key are not configured in Droid Settings. Please save your Fyers App ID and Secret first.</p>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=error_html, status_code=400)

    # Compute SHA-256 hash: appIdHash = SHA256(app_id + ":" + secret_key)
    hash_raw = f"{app_id}:{secret_key}"
    app_id_hash = hashlib.sha256(hash_raw.encode("utf-8")).hexdigest()

    # Exchange auth_code for access_token
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api-t1.fyers.in/api/v3/validate-authcode",
                json={
                    "grant_type": "authorization_code",
                    "appIdHash": app_id_hash,
                    "code": effective_code,
                },
                headers={"Content-Type": "application/json"},
            )
            data = resp.json()
            if resp.status_code == 200 and data.get("s") == "ok" and data.get("access_token"):
                access_token = data["access_token"]
                
                # Apply new access token
                new_settings = {
                    "broker": {
                        "provider": "fyers",
                        "fyers": {
                            "appId": app_id,
                            "secret": secret_key,
                            "access_token": access_token,
                        },
                    }
                }
                apply_app_settings(new_settings)
                reset_provider()
                provider = get_provider()
                token_mgr = provider.get_token_manager()
                token_mgr.set_token(TokenInfo(
                    access_token=access_token,
                    token_type="Bearer",
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
                ))
                await provider.start_stream()

                logger.info("fyers_oauth_exchange_success", app_id=app_id)
                success_html = """
                <!DOCTYPE html>
                <html>
                <head>
                    <title>FYERS Authentication Successful</title>
                    <meta http-equiv="refresh" content="3;url=/" />
                </head>
                <body style="font-family:system-ui,-apple-system,sans-serif;background:#0f172a;color:#f8fafc;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
                    <div style="background:#1e293b;padding:2.5rem;border-radius:12px;border:1px solid #10b981;max-width:500px;text-align:center;box-shadow:0 20px 25px -5px rgba(0,0,0,0.5);">
                        <div style="font-size:48px;margin-bottom:12px;">✅</div>
                        <h2 style="color:#10b981;margin-top:0;">FYERS Connected Successfully!</h2>
                        <p style="color:#94a3b8;font-size:14px;line-height:1.5;">Your daily trading access token has been generated and activated in Droid.</p>
                        <p style="color:#64748b;font-size:12px;margin-top:20px;">Redirecting back to Droid in 3 seconds...</p>
                        <a href="/" style="display:inline-block;margin-top:12px;padding:8px 16px;background:#38bdf8;color:#0f172a;text-decoration:none;font-weight:600;border-radius:6px;font-size:13px;">Return to Dashboard</a>
                    </div>
                </body>
                </html>
                """
                return HTMLResponse(content=success_html, status_code=200)
            else:
                err_text = data.get("message") or str(data)
                logger.warning("fyers_oauth_exchange_failed", response=data)
                fail_html = f"""
                <!DOCTYPE html>
                <html>
                <head><title>FYERS Authentication Failed</title></head>
                <body style="font-family:system-ui,-apple-system,sans-serif;background:#0f172a;color:#f8fafc;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
                    <div style="background:#1e293b;padding:2rem;border-radius:12px;border:1px solid #ef4444;max-width:480px;text-align:center;">
                        <h2 style="color:#ef4444;margin-top:0;">Fyers Token Exchange Failed</h2>
                        <p style="color:#94a3b8;font-size:14px;">Fyers returned: <code>{err_text}</code></p>
                        <p style="color:#64748b;font-size:12px;">Please check that your Secret Key matches your Fyers App ID.</p>
                    </div>
                </body>
                </html>
                """
                return HTMLResponse(content=fail_html, status_code=400)
    except Exception as e:
        logger.error("fyers_oauth_exception", error=str(e))
        return HTMLResponse(
            content=f"<h3>Authentication error: {e}</h3>",
            status_code=500,
        )


@router.post("/fyers/callback")
async def fyers_webhook_post_callback():
    """Handle postbacks / webhook pings from Fyers with HTTP 200 OK."""
    return {"s": "ok", "code": 200, "message": "Callback received"}


@router.post("/test-connection")
async def test_connection(payload: dict = Body(...)):
    """Test broker credentials in real time and return roundtrip diagnostics."""
    import time
    start = time.time()
    prov_name = (payload.get("provider") or "fyers").lower()
    raw_creds = payload.get("credentials") or {}
    
    if prov_name == "fyers":
        app_id = raw_creds.get("appId") or raw_creds.get("app_id") or cfg.fyers_app_id or ""
        access_token = raw_creds.get("access_token") or raw_creds.get("accessToken") or raw_creds.get("token") or cfg.fyers_access_token or ""
        
        if not access_token:
            latency = round((time.time() - start) * 1000, 1)
            return {
                "data": {
                    "success": False,
                    "provider": "fyers",
                    "latency_ms": latency,
                    "token_valid": False,
                    "quote": None,
                    "raw_response": None,
                    "error": "No Access Token found. Please log in via Fyers OAuth or provide an active Access Token.",
                },
                "error": "Access token required for Fyers live probe",
                "meta": _make_meta().model_dump(),
            }
        
        auth_header = f"{app_id}:{access_token}" if app_id else access_token
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                r_profile = await client.get(
                    "https://api-t1.fyers.in/api/v3/profile",
                    headers={"Authorization": auth_header},
                )
                user_info = r_profile.json() if r_profile.status_code == 200 else None

                r_quote = await client.get(
                    "https://api-t1.fyers.in/data/quotes?symbols=NSE:SBIN-EQ,NSE:NIFTY50-INDEX",
                    headers={"Authorization": auth_header},
                )
                latency = round((time.time() - start) * 1000, 1)
                quote_data = r_quote.json() if r_quote.status_code == 200 else None
                is_ok = r_quote.status_code == 200 and quote_data and quote_data.get("s") == "ok"
                
                norm_quote = None
                if is_ok and "d" in quote_data and isinstance(quote_data["d"], list) and len(quote_data["d"]) > 0:
                    first_item = quote_data["d"][0].get("v", {})
                    norm_quote = {
                        "symbol": quote_data["d"][0].get("n"),
                        "ltp": first_item.get("lp", 0),
                        "change": first_item.get("ch", 0),
                        "percent_change": first_item.get("chp", 0),
                    }

                err_msg = None
                if not is_ok:
                    err_msg = quote_data.get("message") if quote_data else f"HTTP {r_quote.status_code}"

                return {
                    "data": {
                        "success": is_ok,
                        "provider": "fyers",
                        "latency_ms": latency,
                        "token_valid": is_ok or (user_info and user_info.get("s") == "ok"),
                        "token_prefix": access_token[:10] + "..." if access_token else "",
                        "user_info": user_info.get("data") if user_info else None,
                        "quote": norm_quote,
                        "raw_response": quote_data,
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
                    "provider": "fyers",
                    "latency_ms": latency,
                    "token_valid": False,
                    "quote": None,
                    "raw_response": None,
                    "error": f"Fyers connection failed: {e}",
                },
                "error": str(e),
                "meta": _make_meta().model_dump(),
            }

    elif prov_name == "binance":
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
