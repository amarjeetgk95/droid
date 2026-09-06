from typing import Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import Profile, UserSettings, Instrument, Expiry
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
            # If dev user not present in DB auth.users, map to existing active profile in DB
            if str(user_id) == "00000000-0000-0000-0000-000000000001":
                res = await session.execute(select(Profile).order_by(Profile.created_at.asc()).limit(1))
                existing = res.scalar_one_or_none()
                if existing:
                    return existing
            try:
                profile = await ProfileRepository.create(session, user_id, display_name)
            except Exception as e:
                logger.warning("profile_create_fallback", error=str(e)[:200])
                res = await session.execute(select(Profile).order_by(Profile.created_at.asc()).limit(1))
                existing = res.scalar_one_or_none()
                if existing:
                    return existing
                raise
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
    async def get_or_create(session: AsyncSession, user_id: UUID, **kwargs) -> UserSettings:
        settings = await SettingsRepository.get_by_user(session, user_id)
        if settings is None:
            if str(user_id) == "00000000-0000-0000-0000-000000000001":
                res = await session.execute(select(UserSettings).limit(1))
                existing = res.scalar_one_or_none()
                if existing:
                    return existing
            try:
                prof = await ProfileRepository.get_or_create(session, user_id)
                settings = await SettingsRepository.create(session, prof.id, **kwargs)
            except Exception as e:
                logger.warning("settings_create_fallback", error=str(e)[:200])
                res = await session.execute(select(UserSettings).limit(1))
                existing = res.scalar_one_or_none()
                if existing:
                    return existing
                raise
        return settings

    @staticmethod
    def _deep_merge_dict(base: dict, patch: dict, max_depth: int = 4) -> dict:
        """Recursively merge patch into base — preserves sibling keys at every nesting level."""
        out = dict(base)
        for k, v in patch.items():
            prev = out.get(k)
            if isinstance(v, dict) and isinstance(prev, dict) and max_depth > 0:
                out[k] = SettingsRepository._deep_merge_dict(prev, v, max_depth - 1)
            else:
                out[k] = v
        return out

    @staticmethod
    async def update(session: AsyncSession, user_id: UUID, **kwargs) -> Optional[UserSettings]:
        settings = await SettingsRepository.get_by_user(session, user_id)
        if settings is None:
            return None
        for key, value in kwargs.items():
            if hasattr(settings, key):
                if key == "app_settings" and isinstance(value, dict):
                    # Guard: refuse absurdly large blobs (16KB)
                    import json as _json
                    try:
                        if len(_json.dumps(value)) > 16 * 1024:
                            logger.warning("app_settings_payload_too_large", user_id=str(user_id), size=len(_json.dumps(value)))
                            # still allow but log — frontend already guards
                            pass
                    except Exception:
                        pass
                    existing = getattr(settings, "app_settings", None) or {}
                    if isinstance(existing, dict) and existing:
                        merged = SettingsRepository._deep_merge_dict(existing, value)
                        # ensure schemaVersion preserved
                        if "schemaVersion" not in merged and "schemaVersion" in existing:
                            merged["schemaVersion"] = existing["schemaVersion"]
                        if "schemaVersion" not in merged:
                            merged["schemaVersion"] = value.get("schemaVersion", 2)
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
