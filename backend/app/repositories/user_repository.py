from typing import Optional
from uuid import UUID
from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from app.models.database import Profile, UserSettings, Watchlist, WatchlistItem, Instrument, Expiry
import structlog

logger = structlog.get_logger()


class ProfileRepository:
    """Repository for profile operations."""

    @staticmethod
    async def get_by_id(session: AsyncSession, user_id: UUID) -> Optional[Profile]:
        result = await session.execute(select(Profile).where(Profile.id == user_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def create(session: AsyncSession, user_id: UUID, display_name: Optional[str] = None) -> Profile:
        profile = Profile(id=user_id, display_name=display_name)
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
        return profile

    @staticmethod
    async def update(session: AsyncSession, user_id: UUID, display_name: Optional[str] = None) -> Optional[Profile]:
        profile = await ProfileRepository.get_by_id(session, user_id)
        if profile is None:
            return None
        if display_name is not None:
            profile.display_name = display_name
        await session.commit()
        await session.refresh(profile)
        return profile

    @staticmethod
    async def get_or_create(session: AsyncSession, user_id: UUID, display_name: Optional[str] = None) -> Profile:
        profile = await ProfileRepository.get_by_id(session, user_id)
        if profile is None:
            profile = await ProfileRepository.create(session, user_id, display_name)
        return profile


class SettingsRepository:
    """Repository for user settings operations."""

    @staticmethod
    async def get_by_user(session: AsyncSession, user_id: UUID) -> Optional[UserSettings]:
        result = await session.execute(select(UserSettings).where(UserSettings.user_id == user_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def create(session: AsyncSession, user_id: UUID, **kwargs) -> UserSettings:
        settings = UserSettings(user_id=user_id, **kwargs)
        session.add(settings)
        await session.commit()
        await session.refresh(settings)
        return settings

    @staticmethod
    async def update(session: AsyncSession, user_id: UUID, **kwargs) -> Optional[UserSettings]:
        settings = await SettingsRepository.get_by_user(session, user_id)
        if settings is None:
            return None
        for key, value in kwargs.items():
            if hasattr(settings, key):
                # For app_settings JSONB: deep-merge instead of blind replace so PATCH is safe
                if key == "app_settings" and isinstance(value, dict):
                    existing = getattr(settings, "app_settings", None) or {}
                    if isinstance(existing, dict) and existing:
                        # shallow merge top-level keys; nested dicts merged one level deep
                        merged = dict(existing)
                        for k, v in value.items():
                            if isinstance(v, dict) and isinstance(merged.get(k), dict):
                                merged[k] = {**merged[k], **v}
                            else:
                                merged[k] = v
                        setattr(settings, key, merged)
                    else:
                        setattr(settings, key, value)
                elif value is not None:
                    setattr(settings, key, value)
        await session.commit()
        await session.refresh(settings)
        return settings

    @staticmethod
    async def get_or_create(session: AsyncSession, user_id: UUID) -> UserSettings:
        settings = await SettingsRepository.get_by_user(session, user_id)
        if settings is None:
            settings = await SettingsRepository.create(session, user_id)
        return settings


class WatchlistRepository:
    """Repository for watchlist operations."""

    @staticmethod
    async def get_by_user(session: AsyncSession, user_id: UUID) -> list[Watchlist]:
        result = await session.execute(
            select(Watchlist).where(Watchlist.user_id == user_id).order_by(Watchlist.created_at)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_id(session: AsyncSession, watchlist_id: UUID) -> Optional[Watchlist]:
        result = await session.execute(select(Watchlist).where(Watchlist.id == watchlist_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def create(session: AsyncSession, user_id: UUID, name: str) -> Watchlist:
        watchlist = Watchlist(user_id=user_id, name=name)
        session.add(watchlist)
        await session.commit()
        await session.refresh(watchlist)
        return watchlist

    @staticmethod
    async def update(session: AsyncSession, watchlist_id: UUID, name: str) -> Optional[Watchlist]:
        watchlist = await WatchlistRepository.get_by_id(session, watchlist_id)
        if watchlist is None:
            return None
        watchlist.name = name
        await session.commit()
        await session.refresh(watchlist)
        return watchlist

    @staticmethod
    async def delete(session: AsyncSession, watchlist_id: UUID) -> bool:
        watchlist = await WatchlistRepository.get_by_id(session, watchlist_id)
        if watchlist is None:
            return False
        await session.delete(watchlist)
        await session.commit()
        return True

    @staticmethod
    async def belongs_to_user(session: AsyncSession, watchlist_id: UUID, user_id: UUID) -> bool:
        watchlist = await WatchlistRepository.get_by_id(session, watchlist_id)
        return watchlist is not None and watchlist.user_id == user_id


class WatchlistItemRepository:
    """Repository for watchlist item operations."""

    @staticmethod
    async def get_by_watchlist(session: AsyncSession, watchlist_id: UUID) -> list[WatchlistItem]:
        result = await session.execute(
            select(WatchlistItem)
            .where(WatchlistItem.watchlist_id == watchlist_id)
            .order_by(WatchlistItem.display_order)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_id(session: AsyncSession, item_id: UUID) -> Optional[WatchlistItem]:
        result = await session.execute(select(WatchlistItem).where(WatchlistItem.id == item_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        watchlist_id: UUID,
        symbol: str,
        instrument_id: Optional[int] = None,
        display_order: int = 0
    ) -> WatchlistItem:
        item = WatchlistItem(
            watchlist_id=watchlist_id,
            symbol=symbol.upper(),
            instrument_id=instrument_id,
            display_order=display_order
        )
        session.add(item)
        await session.commit()
        await session.refresh(item)
        return item

    @staticmethod
    async def update(session: AsyncSession, item_id: UUID, **kwargs) -> Optional[WatchlistItem]:
        item = await WatchlistItemRepository.get_by_id(session, item_id)
        if item is None:
            return None
        for key, value in kwargs.items():
            if value is not None and hasattr(item, key):
                setattr(item, key, value)
        await session.commit()
        await session.refresh(item)
        return item

    @staticmethod
    async def delete(session: AsyncSession, item_id: UUID) -> bool:
        item = await WatchlistItemRepository.get_by_id(session, item_id)
        if item is None:
            return False
        await session.delete(item)
        await session.commit()
        return True

    @staticmethod
    async def exists_in_watchlist(session: AsyncSession, watchlist_id: UUID, symbol: str) -> bool:
        result = await session.execute(
            select(WatchlistItem).where(
                WatchlistItem.watchlist_id == watchlist_id,
                WatchlistItem.symbol == symbol.upper()
            )
        )
        return result.scalar_one_or_none() is not None


class InstrumentRepository:
    """Repository for instrument metadata operations."""

    @staticmethod
    async def get_all_active(session: AsyncSession) -> list[Instrument]:
        result = await session.execute(
            select(Instrument).where(Instrument.is_active == True).order_by(Instrument.symbol)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_symbol(session: AsyncSession, symbol: str) -> Optional[Instrument]:
        result = await session.execute(
            select(Instrument).where(Instrument.symbol == symbol.upper())
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(session: AsyncSession, instrument_id: int) -> Optional[Instrument]:
        result = await session.execute(select(Instrument).where(Instrument.id == instrument_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def search(session: AsyncSession, query: str, limit: int = 20) -> list[Instrument]:
        result = await session.execute(
            select(Instrument)
            .where(
                Instrument.is_active == True,
                (Instrument.symbol.ilike(f"%{query}%") | Instrument.display_name.ilike(f"%{query}%"))
            )
            .order_by(Instrument.symbol)
            .limit(limit)
        )
        return list(result.scalars().all())


class ExpiryRepository:
    """Repository for expiry metadata operations."""

    @staticmethod
    async def get_by_instrument(session: AsyncSession, instrument_id: int, active_only: bool = True) -> list[Expiry]:
        query = select(Expiry).where(Expiry.instrument_id == instrument_id)
        if active_only:
            query = query.where(Expiry.is_active == True)
        query = query.order_by(Expiry.expiry_date)
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_by_symbol(session: AsyncSession, symbol: str, active_only: bool = True) -> list[Expiry]:
        instrument = await InstrumentRepository.get_by_symbol(session, symbol)
        if instrument is None:
            return []
        return await ExpiryRepository.get_by_instrument(session, instrument.id, active_only)
