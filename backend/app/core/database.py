import os
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
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


def normalize_database_url(url: str, for_async: bool = True) -> str:
    """Normalize database URL for asyncpg / psycopg and resolve IPv6-only Supabase direct hosts.

    Supabase direct DB hosts (db.<ref>.supabase.co) only provide IPv6 (AAAA) records.
    Cloud platforms without IPv6 egress (such as Render) fail with [Errno 101] Network is unreachable.
    This function automatically routes db.<ref>.supabase.co to the Supabase IPv4 connection pooler.
    """
    if not url:
        return url

    parsed = urlsplit(url)
    hostname = parsed.hostname or ""
    port = parsed.port
    username = parsed.username or ""
    password = parsed.password
    path = parsed.path
    query = parsed.query

    # Translate Supabase direct host (IPv6 only) to IPv4 connection pooler
    if hostname.startswith("db.") and hostname.endswith(".supabase.co"):
        parts = hostname.split(".")
        ref = parts[1] if len(parts) >= 3 else ""
        pooler_host = os.getenv("SUPABASE_POOLER_HOST", "aws-0-ap-south-1.pooler.supabase.com")
        hostname = pooler_host
        port = 5432  # Session pooler port
        if ref and username and "." not in username:
            username = f"{username}.{ref}"

    scheme = "postgresql+asyncpg" if for_async else "postgresql"

    # asyncpg does not accept sslmode in query string; strip it if present
    if for_async and query:
        q_params = [(k, v) for k, v in parse_qsl(query) if k.lower() != "sslmode"]
        query = urlencode(q_params)

    # Reconstruct netloc
    if username and password is not None:
        netloc = f"{username}:{password}@{hostname}"
    elif username:
        netloc = f"{username}@{hostname}"
    else:
        netloc = hostname

    if port:
        netloc = f"{netloc}:{port}"

    return urlunsplit((scheme, netloc, path, query, ""))


def get_async_engine():
    global _async_engine
    if _async_engine is None:
        raw_url = settings.database_url
        if not raw_url:
            return None
        db_url = normalize_database_url(raw_url, for_async=True)
        try:
            connect_args = {"statement_cache_size": 0}
            _async_engine = create_async_engine(
                db_url,
                connect_args=connect_args,
                pool_pre_ping=True,
                pool_size=10,
                max_overflow=20,
                echo=False,
            )
            logger.info("async_db_engine_created", host=urlsplit(db_url).hostname)
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
        raw_url = settings.database_url
        if not raw_url:
            return None
        sync_url = normalize_database_url(raw_url, for_async=False)
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
