from fastapi import APIRouter, Depends, HTTPException, status
from app.core.security import require_auth, AuthUser
from app.core.database import get_db_session
from app.models.user import ProfileResponse, ProfileUpdate
from app.services.user_service import ProfileService
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class ProfileResponseSimple(BaseModel):
    user_id: str
    email: str | None
    role: str


@router.get("/profile", response_model=ProfileResponseSimple)
async def get_profile_simple(user: AuthUser = Depends(require_auth)):
    """Get the current user's basic profile from JWT."""
    return ProfileResponseSimple(
        user_id=user.user_id,
        email=user.email,
        role=user.role,
    )


@router.get("/profile/full", response_model=ProfileResponse)
async def get_profile(
    user: AuthUser = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Get the current user's full profile from database."""
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not configured"
        )
    profile = await ProfileService.get_profile(session, user.user_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found"
        )
    return profile


@router.patch("/profile", response_model=ProfileResponse)
async def update_profile(
    data: ProfileUpdate,
    user: AuthUser = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Update the current user's profile."""
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not configured"
        )
    profile = await ProfileService.update_profile(session, user.user_id, data)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found"
        )
    return profile
