"""
Telegram State Persistence Layer
Provides persistent storage for Telegram user account bindings and notification
preferences across Render deployments, container rebuilds, and process restarts.

Storage strategy:
1. Primary: PostgreSQL / Supabase database (via DATABASE_URL & user_settings table).
2. Fallback / Local cache: telegram_state.json.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID
import structlog

logger = structlog.get_logger()

STATE_FILE = Path("telegram_state.json")


def read_local_file() -> tuple[dict[str, dict], dict[str, dict]]:
    """Read bindings and preferences from local cache file."""
    if not STATE_FILE.exists():
        return {}, {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            bindings = data.get("bindings", {})
            preferences = data.get("preferences", {})
            return bindings, preferences
    except Exception as e:
        logger.warning("telegram_local_state_read_error", error=str(e))
        return {}, {}


def write_local_file(bindings: dict[str, dict], preferences: dict[str, dict] | None = None) -> None:
    """Write bindings and preferences to local cache file."""
    try:
        payload: dict[str, Any] = {"bindings": bindings}
        if preferences is not None:
            payload["preferences"] = preferences
        else:
            _, existing_prefs = read_local_file()
            payload["preferences"] = existing_prefs
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception as e:
        logger.warning("telegram_local_state_write_error", error=str(e))


async def restore_telegram_state_from_db() -> tuple[dict[str, dict], dict[str, dict]]:
    """
    Load all active Telegram bindings and preferences from database.
    Falls back to local file if DB is not configured or fails.
    """
    file_bindings, file_preferences = read_local_file()
    db_bindings: dict[str, dict] = {}
    db_preferences: dict[str, dict] = {}

    try:
        from app.core.database import get_async_session_factory
        factory = get_async_session_factory()
        if factory is None:
            logger.warning("telegram_db_restore_no_factory", hint="DATABASE_URL may not be set")
            return file_bindings, file_preferences
        async with factory() as session:
            from sqlalchemy import text
            # First check if the table exists
            table_check = await session.execute(
                text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'user_settings')")
            )
            table_exists = table_check.scalar()
            if not table_exists:
                logger.warning("telegram_db_restore_no_table", hint="user_settings table does not exist — run migrations")
                return file_bindings, file_preferences

            res = await session.execute(
                text("SELECT user_id, app_settings FROM user_settings WHERE app_settings IS NOT NULL")
            )
            rows = res.fetchall()
            logger.info("telegram_db_restore_query", rows_with_settings=len(rows))
            for row in rows:
                uid = str(row[0])
                settings_blob = row[1]
                if isinstance(settings_blob, str):
                    try:
                        settings_blob = json.loads(settings_blob)
                    except Exception:
                        settings_blob = {}
                if isinstance(settings_blob, dict):
                    if "telegram_binding" in settings_blob and isinstance(settings_blob["telegram_binding"], dict):
                        db_bindings[uid] = settings_blob["telegram_binding"]
                        logger.info("telegram_db_restore_binding_found", user_id=uid, chat_id=settings_blob["telegram_binding"].get("telegram_chat_id"))
                    if "telegram_preferences" in settings_blob and isinstance(settings_blob["telegram_preferences"], dict):
                        db_preferences[uid] = settings_blob["telegram_preferences"]
            logger.info("telegram_db_state_restored", binding_count=len(db_bindings), pref_count=len(db_preferences))
    except Exception as e:
        logger.warning("telegram_db_state_restore_failed", error=str(e), error_type=type(e).__name__)

    # Merge: DB takes priority, file supplies offline/fallback entries
    final_bindings = {**file_bindings, **db_bindings}
    final_preferences = {**file_preferences, **db_preferences}

    if final_bindings or final_preferences:
        write_local_file(final_bindings, final_preferences)

    return final_bindings, final_preferences


async def persist_user_binding_to_db(user_id: str, binding: dict | None) -> None:
    """
    Persist or remove a single user's Telegram binding in DB and local file cache.
    Auto-creates user_settings row if it doesn't exist.
    """
    try:
        from app.core.database import get_async_session_factory
        factory = get_async_session_factory()
        if factory is None:
            logger.warning("persist_telegram_binding_no_db", user_id=user_id)
            return
        async with factory() as session:
            from sqlalchemy import text
            try:
                uid_val = UUID(str(user_id))
            except Exception:
                uid_val = user_id

            # Check if user_settings row exists
            res = await session.execute(
                text("SELECT app_settings FROM user_settings WHERE user_id = :uid"),
                {"uid": uid_val}
            )
            row = res.first()
            if row:
                settings_blob = row[0] or {}
                if isinstance(settings_blob, str):
                    try:
                        settings_blob = json.loads(settings_blob)
                    except Exception:
                        settings_blob = {}
                if binding:
                    settings_blob["telegram_binding"] = binding
                else:
                    settings_blob.pop("telegram_binding", None)
                await session.execute(
                    text("UPDATE user_settings SET app_settings = :settings, updated_at = NOW() WHERE user_id = :uid"),
                    {"settings": json.dumps(settings_blob), "uid": uid_val}
                )
            else:
                # Auto-create user_settings row with telegram_binding
                app_settings = {}
                if binding:
                    app_settings["telegram_binding"] = binding
                await session.execute(
                    text("INSERT INTO user_settings (user_id, app_settings) VALUES (:uid, :settings) ON CONFLICT (user_id) DO UPDATE SET app_settings = :settings, updated_at = NOW()"),
                    {"uid": uid_val, "settings": json.dumps(app_settings)}
                )
                logger.info("persist_telegram_binding_created_settings_row", user_id=user_id)
            await session.commit()
            logger.info("persist_telegram_binding_ok", user_id=user_id, has_binding=binding is not None)
    except Exception as e:
        logger.warning("persist_telegram_binding_db_failed", user_id=user_id, error=str(e), error_type=type(e).__name__)


async def persist_user_preferences_to_db(user_id: str, preferences: dict | None) -> None:
    """
    Persist a user's Telegram notification preferences in DB.
    """
    try:
        from app.core.database import get_async_session_factory
        factory = get_async_session_factory()
        if factory is not None:
            async with factory() as session:
                from sqlalchemy import text
                try:
                    uid_val = UUID(str(user_id))
                except Exception:
                    uid_val = user_id

                res = await session.execute(
                    text("SELECT app_settings FROM user_settings WHERE user_id = :uid"),
                    {"uid": uid_val}
                )
                row = res.first()
                if row:
                    settings_blob = row[0] or {}
                    if isinstance(settings_blob, str):
                        try:
                            settings_blob = json.loads(settings_blob)
                        except Exception:
                            settings_blob = {}
                    if preferences:
                        settings_blob["telegram_preferences"] = preferences
                    else:
                        settings_blob.pop("telegram_preferences", None)
                    await session.execute(
                        text("UPDATE user_settings SET app_settings = :settings, updated_at = NOW() WHERE user_id = :uid"),
                        {"settings": json.dumps(settings_blob), "uid": uid_val}
                    )
                    await session.commit()
    except Exception as e:
        logger.warning("persist_telegram_prefs_db_failed", user_id=user_id, error=str(e))
