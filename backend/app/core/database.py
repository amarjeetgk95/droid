from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from app.core.config import settings
import structlog

logger = structlog.get_logger()

_async_engine = None
_async_session_factory = None
_sync_engine = None
_sync_session_factory = None


def get_async_engine():
    global _async_engine
    if _async_engine is None:
        db_url = settings.database_url
        if not db_url:
            return None
        # Normalize database URL for asyncpg
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif db_url.startswith("postgresql://") and not db_url.startswith("postgresql+asyncpg://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        try:
            _async_engine = create_async_engine(
                db_url,
                pool_pre_ping=True,
                pool_size=10,
                max_overflow=20,
                echo=False,
            )
            logger.info("async_db_engine_created")
        except Exception as e:
            logger.warning("async_db_engine_create_failed", error=str(e))
            return None
    return _async_engine


def get_async_session_factory():
    global _async_session_factory
    if _async_session_factory is None:
        engine = get_async_engine()
        if engine is None:
            return None
        _async_session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
    return _async_session_factory


async def get_db_session() -> AsyncSession:
    """Get an async database session. Yields None if database is not configured."""
    factory = get_async_session_factory()
    if factory is None:
        yield None
        return
    async with factory() as session:
        yield session


def get_sync_engine():
    global _sync_engine
    if _sync_engine is None:
        db_url = settings.database_url
        if not db_url:
            return None
        # Convert async URL to sync for sync operations
        sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        if sync_url.startswith("postgres://"):
            sync_url = sync_url.replace("postgres://", "postgresql://", 1)
        try:
            _sync_engine = create_engine(
                sync_url,
                pool_pre_ping=True,
                pool_size=5,
                echo=False,
            )
            logger.info("sync_db_engine_created")
        except Exception as e:
            logger.warning("sync_db_engine_create_failed", error=str(e))
            return None
    return _sync_engine


def get_sync_session_factory():
    global _sync_session_factory
    if _sync_session_factory is None:
        engine = get_sync_engine()
        if engine is None:
            return None
        _sync_session_factory = sessionmaker(engine) if engine else None
    return _sync_session_factory


def is_database_configured() -> bool:
    """Check if database URL is configured."""
    return bool(settings.database_url)


from sqlalchemy.orm import sessionmaker
