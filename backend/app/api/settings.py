from fastapi import APIRouter, Depends, HTTPException, status
from app.core.security import require_auth, AuthUser
from app.core.config import settings as app_settings
from app.core.database import get_db_session
from app.models.user import UserSettingsResponse, UserSettingsUpdate
from app.services.user_service import SettingsService
from app.providers.registry import reset_provider, get_provider, stop_previous_provider_stream
from app.core.broker_runtime import apply_app_settings, get_config as get_broker_config
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
import json
from datetime import datetime, timezone
from uuid import UUID

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

# In-memory fallback for dev mode (auth not required) when DB FK fails
_dev_settings_store: dict[str, dict] = {}

def _mock_settings(user_id: str) -> UserSettingsResponse:
    stored = _dev_settings_store.get(user_id, {})
    now = datetime.now(timezone.utc)
    try:
        uid = UUID(user_id)
    except Exception:
        uid = UUID("00000000-0000-0000-0000-000000000001")
    return UserSettingsResponse(
        id=uid,
        user_id=uid,
        theme=stored.get("theme", "dark"),
        default_symbol=stored.get("default_symbol", "NIFTY"),
        default_timeframe=stored.get("default_timeframe", "5m"),
        default_expiry=stored.get("default_expiry"),
        preferred_market_provider=stored.get("preferred_market_provider", "fyers"),
        preferred_ai_provider=stored.get("preferred_ai_provider", "openrouter"),
        preferred_ai_model=stored.get("preferred_ai_model"),
        notification_enabled=stored.get("notification_enabled", True),
        app_settings=stored.get("app_settings"),
        created_at=now,
        updated_at=now,
    )

def _is_dev_mode() -> bool:
    return not app_settings.auth_required

def _deep_merge(base: dict, patch: dict, depth: int = 4) -> dict:
    out = dict(base)
    for k, v in patch.items():
        prev = out.get(k)
        if isinstance(v, dict) and isinstance(prev, dict) and depth > 0:
            out[k] = _deep_merge(prev, v, depth - 1)
        else:
            out[k] = v
    return out

def _is_broker_changed(old: dict | None, new: dict | None) -> bool:
    if not old and new:
        return True
    if not new:
        return False
    old_b = (old or {}).get("broker") if isinstance(old, dict) else None
    new_b = (new or {}).get("broker") if isinstance(new, dict) else None
    return old_b != new_b


async def _reconfigure_provider(res: UserSettingsResponse | None, previous_app_settings: dict | None = None) -> None:
    """After persisting settings, refresh the runtime broker config so saved
    credentials / provider selection take effect without a backend restart.

    Only restarts the provider stream if broker section actually changed to avoid
    storm on unrelated PATCHes (quant/paper/prefs).
    """
    if res is None:
        return
    new_app = res.app_settings if isinstance(res.app_settings, dict) else None
    # If caller provided previous snapshot, use it for cheap diff; otherwise apply anyway
    if previous_app_settings is not None and not _is_broker_changed(previous_app_settings, new_app):
        logger.info("broker_config_unchanged_skip_restart", provider=(new_app or {}).get("broker", {}).get("provider") if isinstance(new_app, dict) else None)
        return
    try:
        changed = apply_app_settings(new_app)
    except Exception as e:
        logger.warning("broker_config_reconfigure_failed", error=str(e)[:200])
        return
    if not changed:
        logger.info("broker_config_no_change", provider=get_broker_config().provider)
        return
    # Stop previous provider's stream BEFORE swapping
    await stop_previous_provider_stream()
    reset_provider()
    try:
        provider = get_provider()
        await provider.start_stream()
        logger.info("settings_provider_stream_restarted", provider=provider.provider_name)
    except Exception as e:
        logger.warning("settings_provider_stream_start_failed", error=str(e)[:200])

async def _get_settings_dev_fallback(user: AuthUser, session: AsyncSession | None, data: UserSettingsUpdate | None = None):
    # Try DB first, fall back to in-memory on any DB error (FK, UUID, connection)
    if session is not None:
        try:
            if data is None:
                res = await SettingsService.get_settings(session, user.user_id)
            else:
                res = await SettingsService.update_settings(session, user.user_id, data)
            if res is not None:
                return res
        except Exception as e:
            logger.warning("settings_db_fallback_to_memory", error=str(e)[:200], user_id=user.user_id)
            try:
                await session.rollback()
            except Exception:
                pass
    # In-memory fallback — deep merge so nested PATCH doesn't drop sibling keys
    if data is not None:
        patch = data.model_dump(exclude_unset=True)
        existing = _dev_settings_store.get(user.user_id, {})
        if "app_settings" in patch and isinstance(patch["app_settings"], dict):
            existing_app = existing.get("app_settings", {}) or {}
            patch["app_settings"] = _deep_merge(existing_app if isinstance(existing_app, dict) else {}, patch["app_settings"])
        _dev_settings_store[user.user_id] = _deep_merge(existing, patch)
    return _mock_settings(user.user_id)


@router.get("/schema")
async def get_settings_schema(user: AuthUser = Depends(require_auth)):
    """Return JSON schema for AppSettings — frontend codegen / drift detection."""
    # Minimal schema mirroring frontend zod shape; keeps backend and frontend in sync
    return {
        "schemaVersion": 2,
        "sections": ["broker", "quantitative", "ai", "paper", "preferences"],
        "broker": {
            "apiType": ["indian", "crypto"],
            "providers": ["fyers", "flattrade", "binance"],
            "fields": {"fyers": ["appId", "secret", "redirectUri"], "flattrade": ["userId", "apiKey", "apiSecret"], "binance": ["apiKey", "apiSecret"]},
        },
        "ai": {
            "connectionModes": ["OpenRouter", "Direct Provider", "Local Ollama"],
            "directProviders": ["OpenAI", "Novita AI", "NVIDIA", "Google Gemini", "Custom OpenAI-Compatible"],
            "routingModes": ["Manual", "Task Optimized", "Best Available", "Cost Optimized"],
        },
        "quantitative": {"fields": ["riskFreeRate", "timeConvention", "defaultPricingModel", "ivMethod", "brokeragePerOrder", "slippagePct"]},
        "paper": {"fields": ["initialCapital", "autoSquareOffTime", "maxCapitalPerTradePct", "maxDailyDrawdownHaltPct"]},
        "preferences": {"fields": ["theme", "numberFormat", "defaultIndexSymbol"]},
        "max_bytes": 16 * 1024,
    }


@router.get("", response_model=UserSettingsResponse)
async def get_settings(
    user: AuthUser = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Get the authenticated user's settings."""
    if _is_dev_mode():
        return await _get_settings_dev_fallback(user, session, None)
    if session is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database not configured. Settings require a database connection.")
    try:
        settings = await SettingsService.get_settings(session, user.user_id)
    except Exception as e:
        logger.error("get_settings_db_error", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)[:200]}")
    if settings is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Settings not found")
    return settings


@router.post("", response_model=UserSettingsResponse)
async def create_settings(
    data: UserSettingsUpdate,
    user: AuthUser = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Create or replace the authenticated user's settings."""
    # Size guard
    try:
        if data.app_settings and len(json.dumps(data.app_settings)) > 16 * 1024:
            raise HTTPException(status_code=413, detail="Settings payload too large (>16KB)")
    except HTTPException:
        raise
    except Exception:
        pass
    if _is_dev_mode():
        settings = await _get_settings_dev_fallback(user, session, data)
        await _reconfigure_provider(settings)
        return settings
    if session is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database not configured. Settings require a database connection.")
    # Capture previous for diff
    previous = None
    try:
        prev_res = await SettingsService.get_settings(session, user.user_id)
        previous = prev_res.app_settings if prev_res and isinstance(prev_res.app_settings, dict) else None
    except Exception:
        pass
    try:
        settings = await SettingsService.update_settings(session, user.user_id, data)
    except Exception as e:
        logger.error("create_settings_db_error", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)[:200]}")
    if settings is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create settings")
    logger.info("settings_saved", user_id=str(user.user_id), has_app_settings=bool(settings.app_settings))
    await _reconfigure_provider(settings, previous)
    return settings


@router.patch("", response_model=UserSettingsResponse)
async def update_settings(
    data: UserSettingsUpdate,
    user: AuthUser = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Partially update the authenticated user's settings."""
    try:
        if data.app_settings and len(json.dumps(data.app_settings)) > 16 * 1024:
            raise HTTPException(status_code=413, detail="Settings payload too large (>16KB)")
    except HTTPException:
        raise
    except Exception:
        pass
    if _is_dev_mode():
        # Capture previous for broker-diff in dev mode
        prev_app = _dev_settings_store.get(user.user_id, {}).get("app_settings") if isinstance(_dev_settings_store.get(user.user_id, {}).get("app_settings"), dict) else None
        settings = await _get_settings_dev_fallback(user, session, data)
        await _reconfigure_provider(settings, prev_app if isinstance(prev_app, dict) else None)
        return settings
    if session is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database not configured. Settings require a database connection.")
    previous = None
    try:
        prev_res = await SettingsService.get_settings(session, user.user_id)
        previous = prev_res.app_settings if prev_res and isinstance(prev_res.app_settings, dict) else None
    except Exception:
        pass
    try:
        settings = await SettingsService.update_settings(session, user.user_id, data)
    except Exception as e:
        logger.error("update_settings_db_error", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)[:200]}")
    if settings is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Settings not found")
    logger.info("settings_patched", user_id=str(user.user_id), fields=list(data.model_dump(exclude_unset=True).keys()))
    await _reconfigure_provider(settings, previous)
    return settings
