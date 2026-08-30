from fastapi import APIRouter, Depends, HTTPException, status
from app.core.security import require_auth, AuthUser
from app.core.config import settings as app_settings
from app.core.database import get_db_session
from app.models.user import UserSettingsResponse, UserSettingsUpdate
from app.services.user_service import SettingsService
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
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
        preferred_market_provider=stored.get("preferred_market_provider", "mock"),
        preferred_ai_provider=stored.get("preferred_ai_provider", "mock_ai"),
        preferred_ai_model=stored.get("preferred_ai_model"),
        notification_enabled=stored.get("notification_enabled", True),
        app_settings=stored.get("app_settings"),
        created_at=now,
        updated_at=now,
    )

def _is_dev_mode() -> bool:
    return not app_settings.auth_required

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
            await session.rollback() if hasattr(session, "rollback") else None
    # In-memory fallback
    if data is not None:
        patch = data.model_dump(exclude_unset=True)
        existing = _dev_settings_store.get(user.user_id, {})
        # merge app_settings shallow
        if "app_settings" in patch and isinstance(patch["app_settings"], dict):
            existing_app = existing.get("app_settings", {}) or {}
            merged = dict(existing_app)
            for k, v in patch["app_settings"].items():
                if isinstance(v, dict) and isinstance(merged.get(k), dict):
                    merged[k] = {**merged[k], **v}
                else:
                    merged[k] = v
            patch["app_settings"] = merged
        _dev_settings_store[user.user_id] = {**existing, **patch}
    return _mock_settings(user.user_id)


@router.get("", response_model=UserSettingsResponse)
async def get_settings(
    user: AuthUser = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Get the authenticated user's settings."""
    if _is_dev_mode():
        return await _get_settings_dev_fallback(user, session, None)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not configured. Settings require a database connection."
        )
    try:
        settings = await SettingsService.get_settings(session, user.user_id)
    except Exception as e:
        logger.error("get_settings_db_error", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)[:200]}")
    if settings is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Settings not found"
        )
    return settings


@router.post("", response_model=UserSettingsResponse)
async def create_settings(
    data: UserSettingsUpdate,
    user: AuthUser = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Create or replace the authenticated user's settings."""
    if _is_dev_mode():
        return await _get_settings_dev_fallback(user, session, data)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not configured. Settings require a database connection."
        )
    try:
        settings = await SettingsService.update_settings(session, user.user_id, data)
    except Exception as e:
        logger.error("create_settings_db_error", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)[:200]}")
    if settings is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create settings"
        )
    return settings


@router.patch("", response_model=UserSettingsResponse)
async def update_settings(
    data: UserSettingsUpdate,
    user: AuthUser = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Partially update the authenticated user's settings."""
    if _is_dev_mode():
        return await _get_settings_dev_fallback(user, session, data)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not configured. Settings require a database connection."
        )
    try:
        settings = await SettingsService.update_settings(session, user.user_id, data)
    except Exception as e:
        logger.error("update_settings_db_error", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)[:200]}")
    if settings is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Settings not found"
        )
    return settings
