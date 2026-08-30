from fastapi import APIRouter, Depends, HTTPException, status
from app.core.security import require_auth, AuthUser
from app.core.database import get_db_session
from app.models.user import UserSettingsResponse, UserSettingsUpdate
from app.services.user_service import SettingsService
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


@router.get("", response_model=UserSettingsResponse)
async def get_settings(
    user: AuthUser = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Get the authenticated user's settings."""
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not configured. Settings require a database connection."
        )
    settings = await SettingsService.get_settings(session, user.user_id)
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
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not configured. Settings require a database connection."
        )
    settings = await SettingsService.update_settings(session, user.user_id, data)
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
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not configured. Settings require a database connection."
        )
    settings = await SettingsService.update_settings(session, user.user_id, data)
    if settings is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Settings not found"
        )
    return settings
