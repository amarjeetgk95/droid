"""SQLite Manager (Deprecated).

All data persistence has been migrated to Supabase PostgreSQL.
This module is retained only for backwards compatibility.
"""
import structlog

logger = structlog.get_logger()


class DummyDatabaseManager:
    def __init__(self):
        logger.debug("sqlite_deprecated_using_supabase")

    def get_connection(self):
        raise NotImplementedError("SQLite has been deprecated in favor of Supabase PostgreSQL.")


db_manager = DummyDatabaseManager()
