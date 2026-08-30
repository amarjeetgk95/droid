from typing import Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.user_repository import (
    ProfileRepository, SettingsRepository, WatchlistRepository, WatchlistItemRepository,
    InstrumentRepository, ExpiryRepository
)
from app.models.user import (
    ProfileUpdate, ProfileResponse,
    UserSettingsUpdate, UserSettingsResponse,
    WatchlistCreate, WatchlistUpdate, WatchlistResponse,
    WatchlistItemCreate, WatchlistItemUpdate, WatchlistItemResponse,
    InstrumentResponse, ExpiryResponse
)
import structlog

logger = structlog.get_logger()


class ProfileService:
    """Service for profile operations."""

    @staticmethod
    async def get_profile(session: AsyncSession, user_id: UUID) -> Optional[ProfileResponse]:
        profile = await ProfileRepository.get_or_create(session, user_id)
        if profile is None:
            return None
        return ProfileResponse.model_validate(profile)

    @staticmethod
    async def update_profile(session: AsyncSession, user_id: UUID, data: ProfileUpdate) -> Optional[ProfileResponse]:
        profile = await ProfileRepository.get_or_create(session, user_id)
        if profile is None:
            return None
        updated = await ProfileRepository.update(session, user_id, display_name=data.display_name)
        if updated is None:
            return None
        return ProfileResponse.model_validate(updated)


class SettingsService:
    """Service for user settings operations."""

    @staticmethod
    async def get_settings(session: AsyncSession, user_id: UUID) -> Optional[UserSettingsResponse]:
        settings = await SettingsRepository.get_or_create(session, user_id)
        if settings is None:
            return None
        return UserSettingsResponse.model_validate(settings)

    @staticmethod
    async def update_settings(session: AsyncSession, user_id: UUID, data: UserSettingsUpdate) -> Optional[UserSettingsResponse]:
        # Ensure profile exists first
        await ProfileRepository.get_or_create(session, user_id)
        settings = await SettingsRepository.get_or_create(session, user_id)
        if settings is None:
            return None
        update_data = data.model_dump(exclude_unset=True)
        updated = await SettingsRepository.update(session, user_id, **update_data)
        if updated is None:
            return None
        return UserSettingsResponse.model_validate(updated)


class WatchlistService:
    """Service for watchlist operations."""

    @staticmethod
    async def get_user_watchlists(session: AsyncSession, user_id: UUID) -> list[WatchlistResponse]:
        watchlists = await WatchlistRepository.get_by_user(session, user_id)
        return [WatchlistResponse.model_validate(w) for w in watchlists]

    @staticmethod
    async def get_watchlist(session: AsyncSession, watchlist_id: UUID, user_id: UUID) -> Optional[WatchlistResponse]:
        if not await WatchlistRepository.belongs_to_user(session, watchlist_id, user_id):
            return None
        watchlist = await WatchlistRepository.get_by_id(session, watchlist_id)
        if watchlist is None:
            return None
        return WatchlistResponse.model_validate(watchlist)

    @staticmethod
    async def create_watchlist(session: AsyncSession, user_id: UUID, data: WatchlistCreate) -> WatchlistResponse:
        # Ensure profile exists
        await ProfileRepository.get_or_create(session, user_id)
        watchlist = await WatchlistRepository.create(session, user_id, data.name)
        return WatchlistResponse.model_validate(watchlist)

    @staticmethod
    async def update_watchlist(session: AsyncSession, watchlist_id: UUID, user_id: UUID, data: WatchlistUpdate) -> Optional[WatchlistResponse]:
        if not await WatchlistRepository.belongs_to_user(session, watchlist_id, user_id):
            return None
        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            return await WatchlistService.get_watchlist(session, watchlist_id, user_id)
        updated = await WatchlistRepository.update(session, watchlist_id, **update_data)
        if updated is None:
            return None
        return WatchlistResponse.model_validate(updated)

    @staticmethod
    async def delete_watchlist(session: AsyncSession, watchlist_id: UUID, user_id: UUID) -> bool:
        if not await WatchlistRepository.belongs_to_user(session, watchlist_id, user_id):
            return False
        return await WatchlistRepository.delete(session, watchlist_id)


class WatchlistItemService:
    """Service for watchlist item operations."""

    @staticmethod
    async def get_items(session: AsyncSession, watchlist_id: UUID, user_id: UUID) -> Optional[list[WatchlistItemResponse]]:
        if not await WatchlistRepository.belongs_to_user(session, watchlist_id, user_id):
            return None
        items = await WatchlistItemRepository.get_by_watchlist(session, watchlist_id)
        return [WatchlistItemResponse.model_validate(item) for item in items]

    @staticmethod
    async def add_item(
        session: AsyncSession, watchlist_id: UUID, user_id: UUID, data: WatchlistItemCreate
    ) -> Optional[WatchlistItemResponse]:
        if not await WatchlistRepository.belongs_to_user(session, watchlist_id, user_id):
            return None
        # Check for duplicates
        if await WatchlistItemRepository.exists_in_watchlist(session, watchlist_id, data.symbol):
            return None
        # Try to find instrument_id from symbol
        instrument = await InstrumentRepository.get_by_symbol(session, data.symbol)
        instrument_id = data.instrument_id or (instrument.id if instrument else None)
        items = await WatchlistItemRepository.get_by_watchlist(session, watchlist_id)
        max_order = max((item.display_order for item in items), default=-1)
        item = await WatchlistItemRepository.create(
            session, watchlist_id, data.symbol, instrument_id, data.display_order or max_order + 1
        )
        return WatchlistItemResponse.model_validate(item)

    @staticmethod
    async def update_item(
        session: AsyncSession, watchlist_id: UUID, item_id: UUID, user_id: UUID, data: WatchlistItemUpdate
    ) -> Optional[WatchlistItemResponse]:
        if not await WatchlistRepository.belongs_to_user(session, watchlist_id, user_id):
            return None
        item = await WatchlistItemRepository.get_by_id(session, item_id)
        if item is None or item.watchlist_id != watchlist_id:
            return None
        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            return WatchlistItemResponse.model_validate(item)
        updated = await WatchlistItemRepository.update(session, item_id, **update_data)
        if updated is None:
            return None
        return WatchlistItemResponse.model_validate(updated)

    @staticmethod
    async def remove_item(session: AsyncSession, watchlist_id: UUID, item_id: UUID, user_id: UUID) -> bool:
        if not await WatchlistRepository.belongs_to_user(session, watchlist_id, user_id):
            return False
        item = await WatchlistItemRepository.get_by_id(session, item_id)
        if item is None or item.watchlist_id != watchlist_id:
            return False
        return await WatchlistItemRepository.delete(session, item_id)


class InstrumentService:
    """Service for instrument metadata operations."""

    @staticmethod
    async def get_all_instruments(session: AsyncSession) -> list[InstrumentResponse]:
        instruments = await InstrumentRepository.get_all_active(session)
        return [InstrumentResponse.model_validate(i) for i in instruments]

    @staticmethod
    async def search_instruments(session: AsyncSession, query: str) -> list[InstrumentResponse]:
        instruments = await InstrumentRepository.search(session, query)
        return [InstrumentResponse.model_validate(i) for i in instruments]

    @staticmethod
    async def get_by_symbol(session: AsyncSession, symbol: str) -> Optional[InstrumentResponse]:
        instrument = await InstrumentRepository.get_by_symbol(session, symbol)
        if instrument is None:
            return None
        return InstrumentResponse.model_validate(instrument)


class ExpiryService:
    """Service for expiry metadata operations."""

    @staticmethod
    async def get_expiries(session: AsyncSession, symbol: str) -> list[ExpiryResponse]:
        expiries = await ExpiryRepository.get_by_symbol(session, symbol)
        return [ExpiryResponse.model_validate(e) for e in expiries]
