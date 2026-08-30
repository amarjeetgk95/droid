from fastapi import APIRouter, Depends, HTTPException, status
from app.core.security import require_auth, AuthUser
from app.core.database import get_db_session
from app.models.user import (
    WatchlistCreate, WatchlistUpdate, WatchlistResponse,
    WatchlistItemCreate, WatchlistItemUpdate, WatchlistItemResponse
)
from app.services.user_service import WatchlistService, WatchlistItemService
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
import structlog

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/watchlists", tags=["watchlists"])


# ============================================================
# Watchlist endpoints
# ============================================================

@router.get("", response_model=list[WatchlistResponse])
async def list_watchlists(
    user: AuthUser = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """List all watchlists for the authenticated user."""
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not configured. Watchlists require a database connection."
        )
    return await WatchlistService.get_user_watchlists(session, user.user_id)


@router.post("", response_model=WatchlistResponse, status_code=status.HTTP_201_CREATED)
async def create_watchlist(
    data: WatchlistCreate,
    user: AuthUser = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Create a new watchlist for the authenticated user."""
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not configured. Watchlists require a database connection."
        )
    return await WatchlistService.create_watchlist(session, user.user_id, data)


@router.get("/{watchlist_id}", response_model=WatchlistResponse)
async def get_watchlist(
    watchlist_id: UUID,
    user: AuthUser = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Get a specific watchlist by ID."""
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not configured. Watchlists require a database connection."
        )
    watchlist = await WatchlistService.get_watchlist(session, watchlist_id, user.user_id)
    if watchlist is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watchlist not found"
        )
    return watchlist


@router.patch("/{watchlist_id}", response_model=WatchlistResponse)
async def update_watchlist(
    watchlist_id: UUID,
    data: WatchlistUpdate,
    user: AuthUser = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Update a watchlist's name."""
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not configured. Watchlists require a database connection."
        )
    watchlist = await WatchlistService.update_watchlist(session, watchlist_id, user.user_id, data)
    if watchlist is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watchlist not found"
        )
    return watchlist


@router.delete("/{watchlist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watchlist(
    watchlist_id: UUID,
    user: AuthUser = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Delete a watchlist and all its items."""
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not configured. Watchlists require a database connection."
        )
    deleted = await WatchlistService.delete_watchlist(session, watchlist_id, user.user_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watchlist not found"
        )
    return None


# ============================================================
# Watchlist item endpoints
# ============================================================

@router.get("/{watchlist_id}/items", response_model=list[WatchlistItemResponse])
async def list_items(
    watchlist_id: UUID,
    user: AuthUser = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """List all items in a watchlist."""
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not configured. Watchlists require a database connection."
        )
    items = await WatchlistItemService.get_items(session, watchlist_id, user.user_id)
    if items is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watchlist not found"
        )
    return items


@router.post("/{watchlist_id}/items", response_model=WatchlistItemResponse, status_code=status.HTTP_201_CREATED)
async def add_item(
    watchlist_id: UUID,
    data: WatchlistItemCreate,
    user: AuthUser = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Add an instrument to a watchlist."""
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not configured. Watchlists require a database connection."
        )
    item = await WatchlistItemService.add_item(session, watchlist_id, user.user_id, data)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Item already exists in watchlist or watchlist not found"
        )
    return item


@router.patch("/{watchlist_id}/items/{item_id}", response_model=WatchlistItemResponse)
async def update_item(
    watchlist_id: UUID,
    item_id: UUID,
    data: WatchlistItemUpdate,
    user: AuthUser = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Update a watchlist item (e.g., change display order)."""
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not configured. Watchlists require a database connection."
        )
    item = await WatchlistItemService.update_item(session, watchlist_id, item_id, user.user_id, data)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watchlist item not found"
        )
    return item


@router.delete("/{watchlist_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_item(
    watchlist_id: UUID,
    item_id: UUID,
    user: AuthUser = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Remove an instrument from a watchlist."""
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not configured. Watchlists require a database connection."
        )
    removed = await WatchlistItemService.remove_item(session, watchlist_id, item_id, user.user_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watchlist item not found"
        )
    return None
