from __future__ import annotations

from fastapi import APIRouter, Body, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from typing import Any
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
    redirect_to: str | None = Query(default=None),
):
    """Redirect user to Fyers OAuth authorization — localhost hardcoded-only.

    app_id/secret/redirect_uri come ONLY from backend/.env
    (FYERS_APP_ID / FYERS_SECRET_KEY / FYERS_REDIRECT_URI).
    Settings UI values and query overrides are ignored.
    """
    def _clean(v: object) -> str:
        return str(v or "").strip().strip("\"'")

    # Localhost hardcoded-only: env is the sole source.
    clean_app_id = _clean(cfg.fyers_app_id)
    clean_secret = _clean(cfg.fyers_secret_key)
    redirect_uri = (_clean(cfg.fyers_redirect_uri) or "http://127.0.0.1:8000/api/v1/tokens/fyers/callback")
    
    if not clean_app_id:
        return HTMLResponse(
            content="""
            <html><body style="font-family:system-ui;background:#0f172a;color:#f8fafc;display:flex;align-items:center;justify-content:center;height:100vh;">
            <div style="background:#1e293b;padding:2rem;border-radius:12px;border:1px solid #ef4444;text-align:center;max-width:480px;">
                <h3 style="color:#ef4444;margin-top:0;">FYERS_APP_ID Not Found</h3>
                <p style="color:#94a3b8;font-size:14px;">Set <code>FYERS_APP_ID</code> and <code>FYERS_SECRET_KEY</code> in <code>backend/.env</code> and restart the local backend (port 8000).</p>
            </div>
            </body></html>
            """,
            status_code=400,
        )

    target_origin = (redirect_to or "").strip()
    if not target_origin and request.headers.get("referer"):
        ref = request.headers.get("referer", "")
        if "://" in ref:
            parts = ref.split("/")
            if len(parts) >= 3:
                target_origin = f"{parts[0]}//{parts[2]}"

    # Pack only return URL into state (no credentials — localhost env is sole source)
    state_payload = {}
    if target_origin:
        state_payload["r"] = target_origin

    if state_payload:
        state_val = "c_" + base64.urlsafe_b64encode(json.dumps(state_payload).encode("utf-8")).decode("utf-8")
    else:
        state_val = "droid_fyers"

    url = f"https://api-t1.fyers.in/api/v3/generate-authcode?client_id={clean_app_id}&redirect_uri={redirect_uri}&response_type=code&state={state_val}"
    return RedirectResponse(url=url)




async def _handle_post_oauth_sync(provider_name: str, provider: Any) -> None:
    """Synchronize system caches, warmup quote pipeline, and broadcast live status upon successful OAuth."""
    # 1. Warm up quotes so token_manager immediately transitions to CONNECTED and resets failure counter
    try:
        from app.core.token_manager import ConnectionState
        token_mgr = provider.get_token_manager() if hasattr(provider, "get_token_manager") else None
        symbols = list(provider.symbol_map.keys()) if hasattr(provider, "symbol_map") else []
        if symbols:
            if hasattr(provider, "_fetch_fyers_quotes"):
                quotes = await provider._fetch_fyers_quotes(symbols)
                if quotes and token_mgr:
                    token_mgr.set_state(ConnectionState.CONNECTED)
                    token_mgr.record_message()
                    setattr(provider, "_consecutive_failures", 0)
    except Exception as e:
        logger.warning("post_oauth_warmup_failed", provider=provider_name, error=str(e)[:150])

    # 2. Invalidate / clear coordinator cache and dashboard summary cache
    try:
        from app.services.market_data_coordinator import market_data_coordinator
        from app.api.dashboard import _summary_cache
        await market_data_coordinator.clear()
        _summary_cache.clear()
    except Exception as e:
        logger.warning("post_oauth_cache_clear_failed", error=str(e)[:150])

    # 3. Broadcast real-time event to all connected WebSocket clients
    try:
        from app.services.central_feed import central_feed
        await central_feed.broadcast_message({
            "type": "BROKER_AUTHENTICATED",
            "provider": provider_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        snapshot = await central_feed.get_snapshot()
        initial_ticks = snapshot.get("ticks", [])
        if initial_ticks:
            await central_feed.broadcast_message({
                "type": "MARKET_TICKS",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "ticks": initial_ticks,
                "snapshot": True,
            })
    except Exception as e:
        logger.warning("post_oauth_ws_broadcast_failed", error=str(e)[:150])


def _generate_oauth_success_html(broker_name: str, return_url: str) -> str:
    escaped_return_url = (return_url or cfg.frontend_url or "https://fo-droid.web.app").strip()
    display_broker = broker_name.upper()
    return f"""<!DOCTYPE html>
<html>
<head>
    <title>{display_broker} Authentication Successful</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family:system-ui,-apple-system,sans-serif;background:#0f172a;color:#f8fafc;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:1rem;">
    <div style="background:#1e293b;padding:2.5rem;border-radius:14px;border:1px solid #10b981;max-width:500px;width:100%;text-align:center;box-shadow:0 20px 25px -5px rgba(0,0,0,0.5);">
        <div style="font-size:48px;margin-bottom:12px;">✅</div>
        <h2 style="color:#10b981;margin-top:0;">{display_broker} Connected Successfully!</h2>
        <p style="color:#94a3b8;font-size:14px;line-height:1.5;">Your daily trading access token has been generated and activated in Droid.</p>
        <p id="countdown" style="color:#64748b;font-size:12px;margin-top:20px;">Synchronizing dashboard and returning in 2 seconds...</p>
        <div style="display:flex;gap:10px;justify-content:center;margin-top:16px;">
            <button id="closeBtn" onclick="tryClose()" style="padding:8px 16px;background:#10b981;color:#0f172a;border:none;font-weight:700;border-radius:6px;font-size:13px;cursor:pointer;">Return to App</button>
            <a id="returnLink" href="{escaped_return_url}" style="padding:8px 16px;background:#38bdf8;color:#0f172a;text-decoration:none;font-weight:700;border-radius:6px;font-size:13px;">Open Dashboard</a>
        </div>
    </div>

    <script>
        const returnUrl = {json.dumps(escaped_return_url)};
        const payload = {{ type: 'DROID_AUTH_SUCCESS', provider: {json.dumps(broker_name.lower())}, timestamp: Date.now() }};

        // 1. Notify opener tab if opened as popup
        if (window.opener && !window.opener.closed) {{
            try {{
                window.opener.postMessage(payload, '*');
            }} catch (e) {{
                console.warn('Failed to postMessage to opener:', e);
            }}
        }}

        // 2. BroadcastChannel for cross-tab sync
        try {{
            const bc = new BroadcastChannel('droid_auth_channel');
            bc.postMessage(payload);
            bc.close();
        }} catch (e) {{}}

        // 3. Fallback: localStorage marker
        try {{
            localStorage.setItem('droid_last_auth_provider', {json.dumps(broker_name.lower())});
            localStorage.setItem('droid_last_auth_time', String(Date.now()));
        }} catch (e) {{}}

        function tryClose() {{
            if (window.opener && !window.opener.closed) {{
                window.close();
            }} else {{
                window.location.href = returnUrl;
            }}
        }}

        setTimeout(tryClose, 1800);
    </script>
</body>
</html>"""


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

    # 3. Decode return_url if packed into state (no credentials in state anymore)
    return_url = ""
    if state and state.startswith("c_"):
        try:
            raw_json = base64.urlsafe_b64decode(state[2:].encode("utf-8")).decode("utf-8")
            parsed = json.loads(raw_json)
            return_url = (parsed.get("r") or "").strip()
        except Exception as ex:
            logger.warning("failed_to_decode_custom_state", error=str(ex))

    if not return_url:
        return_url = cfg.frontend_url or "https://fo-droid.web.app"

    # 4. Localhost hardcoded-only: credentials come ONLY from backend/.env.
    def _clean2(v: object) -> str:
        return str(v or "").strip().strip("\"'")
    app_id = _clean2(cfg.fyers_app_id)
    secret_key = _clean2(cfg.fyers_secret_key)
    cred_source = "Local backend/.env"

    if not app_id or not secret_key:
        error_html = """
        <!DOCTYPE html>
        <html>
        <head><title>FYERS Auth Error</title></head>
        <body style="font-family:system-ui,-apple-system,sans-serif;background:#0f172a;color:#f8fafc;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
            <div style="background:#1e293b;padding:2rem;border-radius:12px;border:1px solid #ef4444;max-width:480px;text-align:center;">
                <h2 style="color:#ef4444;margin-top:0;">Fyers App ID or Secret Missing</h2>
                <p style="color:#94a3b8;font-size:14px;">Set FYERS_APP_ID and FYERS_SECRET_KEY in backend/.env and restart the local backend.</p>
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

                # Localhost: token is runtime-only. app_id/secret stay in .env.
                new_settings = {
                    "broker": {
                        "provider": "fyers",
                        "apiType": "indian",
                        "fyers": {
                            "access_token": access_token,
                            "accessToken": access_token,
                            "token": access_token,
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
                # Persist to local .fyers_token so restarts and auto-reloads retain active authentication
                try:
                    from pathlib import Path
                    Path(".fyers_token").write_text(access_token.strip(), encoding="utf-8")
                except Exception as _ex:
                    logger.warning("failed_to_persist_fyers_token_file", error=str(_ex))

                await provider.start_stream()

                # Synchronize caches, warmup quotes, and broadcast to all connected clients
                await _handle_post_oauth_sync("fyers", provider)

                logger.info("fyers_oauth_exchange_success", app_id=app_id)
                success_html = _generate_oauth_success_html("fyers", return_url)
                return HTMLResponse(content=success_html, status_code=200)
            else:
                err_text = data.get("message") or str(data)
                logger.warning("fyers_oauth_exchange_failed", status_code=resp.status_code, response=data, app_id=app_id)
                
                # Secret fingerprint (length + preview) so user can verify backend/.env
                if len(secret_key) >= 8:
                    secret_preview = f"{secret_key[:3]}••••{secret_key[-3:]} ({len(secret_key)} chars)"
                elif secret_key:
                    secret_preview = f"•••• ({len(secret_key)} chars)"
                else:
                    secret_preview = "Not configured (empty)"

                redirect_uri = (_clean2(cfg.fyers_redirect_uri) or "http://127.0.0.1:8000/api/v1/tokens/fyers/callback").strip()

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

                        <!-- Local hardcoded-only: fix in backend/.env, then retry -->
                        <div style="background:#111827;border:1px solid #374151;border-radius:10px;padding:16px;margin-bottom:20px;text-align:left;">
                            <p style="color:#f3f4f6;font-weight:600;font-size:13px;margin:0 0 6px 0;">Local backend only — no browser override</p>
                            <p style="color:#9ca3af;font-size:11px;margin:0;">App ID / Secret come from <code>backend/.env</code> (<code>FYERS_APP_ID</code> / <code>FYERS_SECRET_KEY</code>). Fix them there, restart the backend on port 8000, then retry.</p>
                        </div>

                        <div style="text-align:left;color:#94a3b8;font-size:12px;line-height:1.6;border-top:1px solid #334155;padding-top:14px;">
                            <p style="color:#e2e8f0;font-weight:600;margin:0 0 6px 0;">Common causes for "{err_text}":</p>
                            <ol style="margin:0;padding-left:18px;">
                                <li><strong>Secret ID Mismatch (Most Common):</strong> Fyers creates a SHA-256 hash of <code>App_ID:Secret_ID</code>. If the Secret ID is wrong, outdated, or regenerated, Fyers returns <code>invalid app id hash</code>. Note that <strong>Secret ID</strong> is from the API dashboard, NOT your User/Client ID, login password, or trading PIN.</li>
                                <li><strong>Secret ID Was Regenerated:</strong> In Fyers MyAPI Dashboard, regenerating the secret key revokes the previous one immediately. Copy the newest Secret ID.</li>
                                <li><strong>App ID Mismatch:</strong> In Fyers MyAPI, verify your App ID matches <code>{app_id}</code> character-by-character (including <code>-100</code>).</li>
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




@router.post("/test-connection")
async def test_connection(payload: dict = Body(...)):
    """Test broker credentials in real time and return roundtrip diagnostics."""
    import time
    start = time.time()
    prov_name = (payload.get("provider") or "fyers").lower()
    raw_creds = payload.get("credentials") or {}
    
    if prov_name == "fyers":
        # Localhost hardcoded-only: app_id from backend/.env, never from browser.
        app_id = (cfg.fyers_app_id or "").strip()
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
            app_id = (cfg.fyers_app_id or "").strip()

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
