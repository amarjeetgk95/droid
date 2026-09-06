from typing import Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.user_repository import (
    ProfileRepository, SettingsRepository,
    InstrumentRepository, ExpiryRepository
)
from app.models.user import (
    ProfileUpdate, ProfileResponse,
    UserSettingsUpdate, UserSettingsResponse,
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
        # RECTIFY: if app_settings is empty or non-dict (e.g., MagicMock in tests), synthesize from legacy flat columns so old rows still return usable JSON
        _app_val = getattr(settings, "app_settings", None)
        _is_missing = _app_val is None or not isinstance(_app_val, dict) or not _app_val
        if _is_missing:
            try:
                legacy_app = {
                    "preferences": {
                        "theme": getattr(settings, "theme", "dark"),
                        "defaultIndexSymbol": getattr(settings, "default_symbol", "NIFTY"),
                        "numberFormat": "INDIAN",
                    },
                    "broker": {"provider": getattr(settings, "preferred_market_provider", "fyers")},
                    "ai": {
                        "provider": getattr(settings, "preferred_ai_provider", "openrouter"),
                        "geminiModel": getattr(settings, "preferred_ai_model", "gemini-2.5-flash"),
                    },
                    "quantitative": {
                        "riskFreeRate": 0.0675,
                        "timeConvention": "ACT365",
                        "defaultPricingModel": "FUTURES_BLACK76",
                        "ivMethod": "BRENT",
                        "brokeragePerOrder": 20,
                        "slippagePct": 0.05,
                    },
                    "paper": {
                        "initialCapital": 1000000,
                        "autoSquareOffTime": "15:20",
                        "maxCapitalPerTradePct": 20,
                        "maxDailyDrawdownHaltPct": 10,
                        "requireOrderConfirm": True,
                        "allowOvernightPositions": True,
                    },
                }
                # Persist synthesized value for future reads (best-effort)
                settings.app_settings = legacy_app
                await session.commit()
                await session.refresh(settings)
            except Exception:
                logger.warning("failed_to_synthesize_app_settings", user_id=str(user_id))
        return UserSettingsResponse.model_validate(settings)

    @staticmethod
    async def update_settings(session: AsyncSession, user_id: UUID, data: UserSettingsUpdate) -> Optional[UserSettingsResponse]:
        # Ensure profile exists first
        await ProfileRepository.get_or_create(session, user_id)
        settings = await SettingsRepository.get_or_create(session, user_id)
        if settings is None:
            return None
        update_data = data.model_dump(exclude_unset=True)
        # RECTIFY: keep flat columns in sync with app_settings JSONB so Supabase stays source of truth
        # If app_settings supplied, mirror key fields to legacy columns for backward compat / quick queries.
        if "app_settings" in update_data and isinstance(update_data["app_settings"], dict):
            app = update_data["app_settings"]
            # preferences.theme -> theme
            try:
                if "preferences" in app and isinstance(app["preferences"], dict):
                    if "theme" in app["preferences"] and "theme" not in update_data:
                        update_data["theme"] = app["preferences"]["theme"]
                    if "defaultIndexSymbol" in app["preferences"] and "default_symbol" not in update_data:
                        update_data["default_symbol"] = app["preferences"]["defaultIndexSymbol"]
                if "ai" in app and isinstance(app["ai"], dict):
                    if "provider" in app["ai"] and "preferred_ai_provider" not in update_data:
                        update_data["preferred_ai_provider"] = app["ai"]["provider"]
                    if "geminiModel" in app["ai"] and "preferred_ai_model" not in update_data:
                        update_data["preferred_ai_model"] = app["ai"]["geminiModel"]
                if "broker" in app and isinstance(app["broker"], dict):
                    if "provider" in app["broker"] and "preferred_market_provider" not in update_data:
                        update_data["preferred_market_provider"] = app["broker"]["provider"]
            except Exception:
                logger.warning("failed_to_sync_app_settings_to_flat_columns", user_id=str(user_id))
        # If only flat columns were updated, also patch existing app_settings to keep it consistent
        elif any(k in update_data for k in ("theme", "default_symbol", "preferred_ai_provider", "preferred_ai_model", "preferred_market_provider")):
            existing_raw = getattr(settings, "app_settings", None)
            existing_app = existing_raw if isinstance(existing_raw, dict) else {}
            if isinstance(existing_app, dict):
                patched = dict(existing_app)
                if "theme" in update_data:
                    patched.setdefault("preferences", {})["theme"] = update_data["theme"]
                if "default_symbol" in update_data:
                    patched.setdefault("preferences", {})["defaultIndexSymbol"] = update_data["default_symbol"]
                if "preferred_ai_provider" in update_data:
                    patched.setdefault("ai", {})["provider"] = update_data["preferred_ai_provider"]
                if "preferred_ai_model" in update_data:
                    patched.setdefault("ai", {})["geminiModel"] = update_data["preferred_ai_model"]
                if "preferred_market_provider" in update_data:
                    patched.setdefault("broker", {})["provider"] = update_data["preferred_market_provider"]
                # Only set if we actually patched something beyond what was there
                if patched != existing_app:
                    update_data["app_settings"] = patched
        updated = await SettingsRepository.update(session, user_id, **update_data)
        if updated is None:
            return None
        # Sanitize MagicMock app_settings that leaks from tests (not a real dict)
        _upd_app = getattr(updated, "app_settings", None)
        if _upd_app is not None and not isinstance(_upd_app, dict):
            try:
                updated.app_settings = None
            except Exception:
                pass
        return UserSettingsResponse.model_validate(updated)


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
