from fastapi import APIRouter, Body, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from app.providers.registry import get_provider
from app.core.broker_runtime import apply_app_settings, get_config
from app.core.token_manager import ConnectionState, TokenInfo
from app.models.market import ApiMeta, DataStatus
from app.core.config import settings as cfg
from datetime import datetime, timezone, timedelta
import base64
import hashlib
import json
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
                # Backend-owned restart (stops previous BEFORE reset — no
                # leaked second upstream).Same as settings save path.
                from app.core.service_lifecycle import restart_provider_stream
                await restart_provider_stream(reason="token_diagnostics")
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
                from app.core.service_lifecycle import restart_provider_stream
                await restart_provider_stream(reason="token_refresh")
                logger.info("token_refresh_hot_sync", provider=incoming_app.get("broker", {}).get("provider"))
            except Exception as e:
                logger.warning("token_refresh_hot_sync_failed", error=str(e)[:200])

    # Backend-owned idempotent ensure (no-op when already running) — never
    # tied to the calling browser session.
    try:
        from app.core.service_lifecycle import ensure_provider_stream
        provider = await ensure_provider_stream()
    except Exception as e:
        logger.warning("token_refresh_start_stream_failed", error=str(e)[:200])
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


@router.get("/fyers/login")
async def fyers_oauth_login(
    request: Request,
    app_id: str | None = Query(default=None),
    secret_key: str | None = Query(default=None),
):
    """Redirect user to Fyers OAuth authorization using Render server credentials or custom query overrides."""
    broker_config = get_config()
    creds = broker_config.credentials if broker_config.provider == "fyers" else {}
    
    clean_app_id = (app_id or creds.get("app_id") or cfg.fyers_app_id or "").strip().strip("\"'")
    clean_secret = (secret_key or creds.get("secret_key") or cfg.fyers_secret_key or "").strip().strip("\"'")
    redirect_uri = (creds.get("redirect_uri") or cfg.fyers_redirect_uri or "https://droid-backend-emeq.onrender.com/api/v1/tokens/fyers/callback").strip()
    
    if not clean_app_id:
        return HTMLResponse(
            content="""
            <html><body style="font-family:system-ui;background:#0f172a;color:#f8fafc;display:flex;align-items:center;justify-content:center;height:100vh;">
            <div style="background:#1e293b;padding:2rem;border-radius:12px;border:1px solid #ef4444;text-align:center;max-width:480px;">
                <h3 style="color:#ef4444;margin-top:0;">FYERS_APP_ID Not Found</h3>
                <p style="color:#94a3b8;font-size:14px;">Please configure <code>FYERS_APP_ID</code> and <code>FYERS_SECRET_KEY</code> in Render Environment Variables or enter them in Droid Settings.</p>
            </div>
            </body></html>
            """,
            status_code=400,
        )

    # If custom app_id or secret_key provided via query, pack them in state so callback has access
    if app_id or secret_key:
        state_payload = {"a": clean_app_id, "s": clean_secret}
        state_val = "c_" + base64.urlsafe_b64encode(json.dumps(state_payload).encode("utf-8")).decode("utf-8")
    else:
        state_val = "droid_fyers"

    url = f"https://api-t1.fyers.in/api/v3/generate-authcode?client_id={clean_app_id}&redirect_uri={redirect_uri}&response_type=code&state={state_val}"
    return RedirectResponse(url=url)


@router.get("/flattrade/login")
async def flattrade_oauth_login(request: Request):
    """Redirect user to Flattrade OAuth authorization using Render server credentials."""
    broker_config = get_config()
    creds = broker_config.credentials if broker_config.provider == "flattrade" else {}
    api_key = creds.get("api_key") or cfg.flattrade_api_key
    
    if not api_key:
        return HTMLResponse(
            content="""
            <html><body style="font-family:system-ui;background:#0f172a;color:#f8fafc;display:flex;align-items:center;justify-content:center;height:100vh;">
            <div style="background:#1e293b;padding:2rem;border-radius:12px;border:1px solid #ef4444;text-align:center;max-width:480px;">
                <h3 style="color:#ef4444;margin-top:0;">FLATTRADE_API_KEY Not Found in Render</h3>
                <p style="color:#94a3b8;font-size:14px;">Please configure <code>FLATTRADE_API_KEY</code> and <code>FLATTRADE_API_SECRET</code> in Render Environment Variables.</p>
            </div>
            </body></html>
            """,
            status_code=400,
        )
    
    url = f"https://auth.flattrade.in/?app_key={api_key}"
    return RedirectResponse(url=url)


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
    # 1. Handle case where Fyers redirected with an error
    if s == "error" or (message and not auth_code and not code):
        fail_reason = message or "Fyers authentication was cancelled or rejected by Fyers server."
        return HTMLResponse(
            content=f"""
            <!DOCTYPE html>
            <html>
            <head><title>FYERS Authentication Failed</title></head>
            <body style="font-family:system-ui,-apple-system,sans-serif;background:#0f172a;color:#f8fafc;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:1rem;">
                <div style="background:#1e293b;padding:2rem;border-radius:12px;border:1px solid #ef4444;max-width:520px;text-align:center;">
                    <div style="font-size:36px;margin-bottom:8px;">⚠️</div>
                    <h2 style="color:#ef4444;margin-top:0;">Fyers Auth Redirect Error</h2>
                    <div style="background:#0f172a;padding:12px;border-radius:8px;border:1px solid #334155;margin-bottom:16px;text-align:left;">
                        <p style="color:#94a3b8;font-size:13px;margin:0;"><strong>Fyers Message:</strong> <code style="color:#f87171;">{fail_reason}</code></p>
                    </div>
                    <a href="/api/v1/tokens/fyers/login" style="display:inline-block;padding:8px 16px;background:#38bdf8;color:#0f172a;text-decoration:none;font-weight:600;border-radius:6px;font-size:12px;">Retry Login</a>
                </div>
            </body>
            </html>
            """,
            status_code=400,
        )

    # 2. Extract authorization code
    effective_code = auth_code or (code if s != "error" else None)
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

    # 3. Decode custom credentials if packed into state
    custom_app_id = ""
    custom_secret = ""
    if state and state.startswith("c_"):
        try:
            raw_json = base64.urlsafe_b64decode(state[2:].encode("utf-8")).decode("utf-8")
            parsed = json.loads(raw_json)
            custom_app_id = (parsed.get("a") or "").strip().strip("\"'")
            custom_secret = (parsed.get("s") or "").strip().strip("\"'")
        except Exception as ex:
            logger.warning("failed_to_decode_custom_state", error=str(ex))

    # 4. Resolve credentials with fallback hierarchy
    broker_config = get_config()
    creds = broker_config.credentials if broker_config.provider == "fyers" else {}
    app_id = custom_app_id or (creds.get("app_id") or cfg.fyers_app_id or "").strip().strip("\"'")
    secret_key = custom_secret or (creds.get("secret_key") or cfg.fyers_secret_key or "").strip().strip("\"'")
    cred_source = "Custom Browser Session" if custom_app_id else "Render Server Environment Variables"

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
                    "code": effective_code.strip(),
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
                # Backend-owned restart: stop previous BEFORE reset (no leaked
                # second upstream), then activate the new token on the fresh
                # singleton under the process-wide lock.
                from app.core.service_lifecycle import restart_provider_stream
                provider = await restart_provider_stream(reason="fyers_oauth")
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
                logger.warning("fyers_oauth_exchange_failed", status_code=resp.status_code, response=data, app_id=app_id)
                
                # Secret fingerprint (length + preview) so user can immediately verify if Render has the right secret
                if len(secret_key) >= 8:
                    secret_preview = f"{secret_key[:3]}••••{secret_key[-3:]} ({len(secret_key)} chars)"
                elif secret_key:
                    secret_preview = f"•••• ({len(secret_key)} chars)"
                else:
                    secret_preview = "Not configured (empty)"
                
                redirect_uri = (creds.get("redirect_uri") or cfg.fyers_redirect_uri or "https://droid-backend-emeq.onrender.com/api/v1/tokens/fyers/callback").strip()

                fail_html = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>FYERS Authentication Failed</title>
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                </head>
                <body style="font-family:system-ui,-apple-system,sans-serif;background:#0f172a;color:#f8fafc;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:1.5rem;">
                    <div style="background:#1e293b;padding:2rem;border-radius:14px;border:1px solid #ef4444;max-width:580px;width:100%;text-align:center;box-shadow:0 25px 50px -12px rgba(0,0,0,0.6);">
                        <div style="font-size:36px;margin-bottom:8px;">⚠️</div>
                        <h2 style="color:#ef4444;margin:0 0 16px 0;font-size:22px;">Fyers Token Exchange Failed</h2>
                        
                        <div style="background:#0f172a;padding:14px;border-radius:10px;border:1px solid #334155;margin-bottom:20px;text-align:left;font-size:12px;line-height:1.7;">
                            <div style="display:flex;justify-content:space-between;border-bottom:1px solid #1e293b;padding-bottom:6px;margin-bottom:6px;">
                                <span style="color:#94a3b8;">Fyers Error:</span>
                                <code style="color:#f87171;font-weight:600;">{err_text} (HTTP {resp.status_code})</code>
                            </div>
                            <div style="display:flex;justify-content:space-between;border-bottom:1px solid #1e293b;padding-bottom:6px;margin-bottom:6px;">
                                <span style="color:#94a3b8;">App ID Used:</span>
                                <code style="color:#38bdf8;font-weight:600;">{app_id}</code>
                            </div>
                            <div style="display:flex;justify-content:space-between;border-bottom:1px solid #1e293b;padding-bottom:6px;margin-bottom:6px;">
                                <span style="color:#94a3b8;">Secret Key Fingerprint:</span>
                                <code style="color:#e2e8f0;font-weight:600;">{secret_preview}</code>
                            </div>
                            <div style="display:flex;justify-content:space-between;">
                                <span style="color:#94a3b8;">Credential Source:</span>
                                <span style="color:#94a3b8;">{cred_source}</span>
                            </div>
                        </div>

                        <!-- Direct Override & Retry Form -->
                        <div style="background:#111827;border:1px solid #374151;border-radius:10px;padding:16px;margin-bottom:20px;text-align:left;">
                            <p style="color:#f3f4f6;font-weight:600;font-size:13px;margin:0 0 6px 0;">⚡ Re-authorize with Custom Credentials</p>
                            <p style="color:#9ca3af;font-size:11px;margin:0 0 12px 0;">If your App ID or Secret in Render is outdated, enter your actual Fyers MyAPI credentials below to authenticate immediately:</p>
                            <form action="/api/v1/tokens/fyers/login" method="GET" style="display:flex;flex-direction:column;gap:10px;">
                                <div>
                                    <label style="color:#9ca3af;font-size:11px;display:block;margin-bottom:4px;">Fyers App ID (e.g. from MyAPI Dashboard):</label>
                                    <input type="text" name="app_id" value="{app_id}" placeholder="e.g. YOUR_APP_ID-100" required style="width:100%;box-sizing:border-box;background:#1f2937;border:1px solid #4b5563;color:#f9fafb;padding:8px 10px;border-radius:6px;font-size:12px;font-family:monospace;" />
                                </div>
                                <div>
                                    <label style="color:#9ca3af;font-size:11px;display:block;margin-bottom:4px;">Secret ID (from MyAPI Dashboard):</label>
                                    <input type="password" name="secret_key" placeholder="Enter Fyers Secret ID" required style="width:100%;box-sizing:border-box;background:#1f2937;border:1px solid #4b5563;color:#f9fafb;padding:8px 10px;border-radius:6px;font-size:12px;font-family:monospace;" />
                                </div>
                                <button type="submit" style="margin-top:4px;padding:9px 16px;background:#38bdf8;color:#0f172a;border:none;border-radius:6px;font-size:12px;font-weight:bold;cursor:pointer;">Authorize With These Credentials</button>
                            </form>
                        </div>

                        <div style="text-align:left;color:#94a3b8;font-size:12px;line-height:1.6;border-top:1px solid #334155;padding-top:14px;">
                            <p style="color:#e2e8f0;font-weight:600;margin:0 0 6px 0;">Why Fyers returns "internal server error":</p>
                            <ol style="margin:0;padding-left:18px;">
                                <li><strong>App ID Mismatch:</strong> In Fyers MyAPI, verify your App ID matches <code>{app_id}</code> character-by-character.</li>
                                <li><strong>Secret ID Mismatch:</strong> In Fyers MyAPI, copy the <strong>Secret ID</strong> (not trading PIN). If you recently regenerated it, the old secret is invalid.</li>
                                <li><strong>Redirect URL:</strong> In Fyers MyAPI Dashboard, ensure Redirect URL is exactly: <code style="color:#38bdf8;word-break:break-all;">{redirect_uri}</code></li>
                                <li><strong>App Status:</strong> In <a href="https://myapi.fyers.in/dashboard" target="_blank" style="color:#38bdf8;">Fyers MyAPI Dashboard</a>, ensure app toggle is <strong>Active</strong>.</li>
                            </ol>
                        </div>
                        
                        <div style="margin-top:20px;display:flex;gap:10px;justify-content:center;">
                            <a href="/api/v1/tokens/fyers/login" style="display:inline-block;padding:8px 16px;background:#1e293b;border:1px solid #475569;color:#f8fafc;text-decoration:none;font-weight:600;border-radius:6px;font-size:12px;">Retry Server Login</a>
                            <a href="/" style="display:inline-block;padding:8px 16px;background:#334155;color:#f8fafc;text-decoration:none;font-weight:600;border-radius:6px;font-size:12px;">Return to Dashboard</a>
                        </div>
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


@router.get("/flattrade/callback")
async def flattrade_oauth_callback(
    request: Request,
    code: str | None = Query(default=None),
    auth_code: str | None = Query(default=None),
    request_code: str | None = Query(default=None),
):
    """Handle Flattrade OAuth redirect after user authentication.
    
    Exchanges code with API Secret Hash via POST https://authapi.flattrade.in/trade/token.
    Hash formula: SHA-256(api_key + code + api_secret)
    """
    effective_code = code or auth_code or request_code
    if not effective_code:
        return HTMLResponse(
            content="""
            <!DOCTYPE html>
            <html>
            <head><title>Flattrade OAuth Callback</title></head>
            <body style="font-family:system-ui,-apple-system,sans-serif;background:#0f172a;color:#f8fafc;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
                <div style="background:#1e293b;padding:2rem;border-radius:12px;border:1px solid #334155;max-width:480px;text-align:center;">
                    <h2 style="color:#38bdf8;margin-top:0;">Flattrade OAuth Callback Ready</h2>
                    <p style="color:#94a3b8;font-size:14px;">This endpoint is active and waiting for Flattrade authentication redirects.</p>
                </div>
            </body>
            </html>
            """,
            status_code=200,
        )

    # Get active Flattrade credentials
    broker_config = get_config()
    creds = broker_config.credentials if broker_config.provider == "flattrade" else {}
    api_key = creds.get("api_key") or cfg.flattrade_api_key
    api_secret = creds.get("api_secret") or cfg.flattrade_api_secret
    user_id = creds.get("user_id") or cfg.flattrade_user_id

    if not api_key or not api_secret:
        error_html = """
        <!DOCTYPE html>
        <html>
        <head><title>Flattrade Auth Error</title></head>
        <body style="font-family:system-ui,-apple-system,sans-serif;background:#0f172a;color:#f8fafc;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
            <div style="background:#1e293b;padding:2rem;border-radius:12px;border:1px solid #ef4444;max-width:480px;text-align:center;">
                <h2 style="color:#ef4444;margin-top:0;">Flattrade API Key or Secret Missing</h2>
                <p style="color:#94a3b8;font-size:14px;">Received auth code, but API Key and Secret are not configured in Droid Settings. Please save your Flattrade credentials first.</p>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=error_html, status_code=400)

    # Compute SHA-256 hash: SHA256(api_key + code + api_secret)
    hash_raw = f"{api_key}{effective_code}{api_secret}"
    api_secret_hash = hashlib.sha256(hash_raw.encode("utf-8")).hexdigest()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://authapi.flattrade.in/trade/token",
                json={
                    "api_key": api_key,
                    "request_code": effective_code,
                    "api_secret": api_secret_hash,
                },
                headers={"Content-Type": "application/json"},
            )
            data = resp.json()
            if resp.status_code == 200 and data.get("stat") == "Ok" and data.get("token"):
                session_token = data["token"]

                # Apply new token
                new_settings = {
                    "broker": {
                        "provider": "flattrade",
                        "flattrade": {
                            "userId": user_id,
                            "apiKey": api_key,
                            "apiSecret": api_secret,
                            "token": session_token,
                        },
                    }
                }
                apply_app_settings(new_settings)
                # Backend-owned restart: stop previous BEFORE reset (no leaked
                # second upstream), then activate the new token on the fresh
                # singleton under the process-wide lock.
                from app.core.service_lifecycle import restart_provider_stream
                provider = await restart_provider_stream(reason="flattrade_oauth")
                token_mgr = provider.get_token_manager()
                token_mgr.set_token(TokenInfo(
                    access_token=session_token,
                    token_type="Bearer",
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
                ))
                await provider.start_stream()

                logger.info("flattrade_oauth_exchange_success", user_id=user_id)
                success_html = """
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Flattrade Authentication Successful</title>
                    <meta http-equiv="refresh" content="3;url=/" />
                </head>
                <body style="font-family:system-ui,-apple-system,sans-serif;background:#0f172a;color:#f8fafc;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
                    <div style="background:#1e293b;padding:2.5rem;border-radius:12px;border:1px solid #10b981;max-width:500px;text-align:center;box-shadow:0 20px 25px -5px rgba(0,0,0,0.5);">
                        <div style="font-size:48px;margin-bottom:12px;">✅</div>
                        <h2 style="color:#10b981;margin-top:0;">Flattrade Connected Successfully!</h2>
                        <p style="color:#94a3b8;font-size:14px;line-height:1.5;">Your trading session token has been generated and activated in Droid.</p>
                        <p style="color:#64748b;font-size:12px;margin-top:20px;">Redirecting back to Droid in 3 seconds...</p>
                        <a href="/" style="display:inline-block;margin-top:12px;padding:8px 16px;background:#38bdf8;color:#0f172a;text-decoration:none;font-weight:600;border-radius:6px;font-size:13px;">Return to Dashboard</a>
                    </div>
                </body>
                </html>
                """
                return HTMLResponse(content=success_html, status_code=200)
            else:
                err_text = data.get("emsg") or data.get("message") or str(data)
                logger.warning("flattrade_oauth_exchange_failed", response=data)
                fail_html = f"""
                <!DOCTYPE html>
                <html>
                <head><title>Flattrade Authentication Failed</title></head>
                <body style="font-family:system-ui,-apple-system,sans-serif;background:#0f172a;color:#f8fafc;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
                    <div style="background:#1e293b;padding:2rem;border-radius:12px;border:1px solid #ef4444;max-width:480px;text-align:center;">
                        <h2 style="color:#ef4444;margin-top:0;">Flattrade Token Exchange Failed</h2>
                        <p style="color:#94a3b8;font-size:14px;">Flattrade returned: <code>{err_text}</code></p>
                        <p style="color:#64748b;font-size:12px;">Please check that your API Key and Secret match your WallConnect app.</p>
                    </div>
                </body>
                </html>
                """
                return HTMLResponse(content=fail_html, status_code=400)
    except Exception as e:
        logger.error("flattrade_oauth_exception", error=str(e))
        return HTMLResponse(
            content=f"<h3>Authentication error: {e}</h3>",
            status_code=500,
        )


@router.post("/flattrade/callback")
async def flattrade_webhook_post_callback():
    """Handle postbacks / webhook pings from Flattrade with HTTP 200 OK."""
    return {"s": "ok", "code": 200, "message": "Flattrade callback received"}


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
        
        # Fallback to active runtime token if not explicitly provided in test payload
        if not access_token:
            broker_config = get_config()
            if broker_config.provider == "fyers":
                access_token = broker_config.credentials.get("access_token") or ""
            if not access_token:
                try:
                    provider = get_provider()
                    token_mgr = provider.get_token_manager()
                    if token_mgr.token_info and token_mgr.token_info.access_token:
                        access_token = token_mgr.token_info.access_token
                except Exception:
                    pass

        if not app_id:
            broker_config = get_config()
            if broker_config.provider == "fyers":
                app_id = broker_config.credentials.get("app_id") or ""

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

    elif prov_name == "flattrade":
        user_id = raw_creds.get("userId") or raw_creds.get("user_id") or cfg.flattrade_user_id or ""
        token = raw_creds.get("token") or raw_creds.get("access_token") or cfg.flattrade_token or ""
        api_key = raw_creds.get("apiKey") or raw_creds.get("api_key") or cfg.flattrade_api_key or ""

        if not token:
            broker_config = get_config()
            if broker_config.provider == "flattrade":
                token = broker_config.credentials.get("token") or broker_config.credentials.get("access_token") or ""

        if not token:
            latency = round((time.time() - start) * 1000, 1)
            return {
                "data": {
                    "success": False,
                    "provider": "flattrade",
                    "latency_ms": latency,
                    "token_valid": False,
                    "quote": None,
                    "raw_response": None,
                    "error": "No Flattrade Session Token found. Please log in via Flattrade OAuth or provide an active Token.",
                },
                "error": "Session token required for Flattrade live probe",
                "meta": _make_meta().model_dump(),
            }

        try:
            payload_data = {"uid": user_id, "actid": user_id, "exch": "NSE", "token": "26000"}
            jData_str = f"jData={json.dumps(payload_data)}&jKey={token}"
            async with httpx.AsyncClient(timeout=6.0) as client:
                r = await client.post(
                    "https://piconnect.flattrade.in/PiConnectTP/GetQuotes",
                    data=jData_str,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                latency = round((time.time() - start) * 1000, 1)
                data = r.json() if r.status_code == 200 else None
                is_ok = r.status_code == 200 and data and data.get("stat") == "Ok"
                
                norm_quote = None
                if is_ok and data:
                    norm_quote = {
                        "symbol": data.get("tsym", "NIFTY 50"),
                        "ltp": float(data.get("lp", 0.0)),
                        "change": float(data.get("c", 0.0)),
                        "percent_change": float(data.get("pc", 0.0)),
                    }

                err_msg = None if is_ok else (data.get("emsg") if data else f"HTTP {r.status_code}")
                return {
                    "data": {
                        "success": is_ok,
                        "provider": "flattrade",
                        "latency_ms": latency,
                        "token_valid": is_ok,
                        "token_prefix": token[:10] + "..." if token else "",
                        "quote": norm_quote,
                        "raw_response": data,
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
                    "provider": "flattrade",
                    "latency_ms": latency,
                    "token_valid": False,
                    "quote": None,
                    "raw_response": None,
                    "error": f"Flattrade connection failed: {e}",
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
