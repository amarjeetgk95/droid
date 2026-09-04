"""
HPI Supabase / PostgreSQL Persistence Layer
Persists Historical Intelligence datasets, user selections, retention policies,
and deletion audit logs to Supabase across Render restarts, deployments, and browser refreshes.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
import structlog
from sqlalchemy import text

from app.core.database import get_async_session_factory

logger = structlog.get_logger()


async def ensure_hpi_tables() -> bool:
    """Auto-provision HPI tables in Supabase if not present."""
    factory = get_async_session_factory()
    if factory is None:
        return False
    try:
        async with factory() as session:
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS hpi_state (
                    id TEXT PRIMARY KEY DEFAULT 'global',
                    selection_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                    policies_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                    audit_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                    deleted_ranges_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                    seeded BOOLEAN NOT NULL DEFAULT false,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );

                CREATE TABLE IF NOT EXISTS hpi_datasets (
                    symbol TEXT NOT NULL,
                    category TEXT NOT NULL,
                    record_count INT NOT NULL DEFAULT 0,
                    storage_bytes BIGINT NOT NULL DEFAULT 0,
                    oldest_ts TIMESTAMPTZ,
                    newest_ts TIMESTAMPTZ,
                    records_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    PRIMARY KEY (symbol, category)
                );

                CREATE INDEX IF NOT EXISTS idx_hpi_datasets_symbol ON hpi_datasets (symbol);
            """))
            await session.commit()
            logger.info("hpi_db_tables_ensured")
            return True
    except Exception as e:
        logger.warning("hpi_ensure_tables_failed", error=str(e)[:200])
        return False


async def restore_hpi_from_db() -> dict[str, Any] | None:
    """
    Restore HPI state and dataset records from Supabase PostgreSQL.
    Returns dictionary with records, deleted_ranges, selection, policies, audit, and seeded.
    """
    factory = get_async_session_factory()
    if factory is None:
        return None

    try:
        async with factory() as session:
            # 1. Load state metadata
            state_res = await session.execute(
                text("SELECT selection_json, policies_json, audit_json, deleted_ranges_json, seeded FROM hpi_state WHERE id = 'global'")
            )
            state_row = state_res.first()

            # 2. Load dataset records
            ds_res = await session.execute(
                text("SELECT symbol, category, records_json, record_count FROM hpi_datasets WHERE record_count > 0")
            )
            ds_rows = ds_res.fetchall()

            if not state_row and not ds_rows:
                return None

            records: dict[str, list[list]] = {}
            for row in ds_rows:
                sym = str(row[0]).upper()
                cat = str(row[1])
                rec_data = row[2]
                if isinstance(rec_data, str):
                    try:
                        rec_data = json.loads(rec_data)
                    except Exception:
                        rec_data = []
                if isinstance(rec_data, list) and rec_data:
                    records[f"{sym}|{cat}"] = rec_data

            selection = []
            policies = []
            audit = []
            deleted_ranges = {}
            seeded = False

            if state_row:
                s_json, p_json, a_json, d_json, is_seeded = state_row
                if isinstance(s_json, str):
                    try:
                        s_json = json.loads(s_json)
                    except Exception:
                        s_json = []
                selection = s_json if isinstance(s_json, list) else []

                if isinstance(p_json, str):
                    try:
                        p_json = json.loads(p_json)
                    except Exception:
                        p_json = []
                policies = p_json if isinstance(p_json, list) else []

                if isinstance(a_json, str):
                    try:
                        a_json = json.loads(a_json)
                    except Exception:
                        a_json = []
                audit = a_json if isinstance(a_json, list) else []

                if isinstance(d_json, str):
                    try:
                        d_json = json.loads(d_json)
                    except Exception:
                        d_json = {}
                deleted_ranges = d_json if isinstance(d_json, dict) else {}
                seeded = bool(is_seeded)

            logger.info("hpi_db_state_restored", datasets_loaded=len(records), seeded=seeded)
            return {
                "records": records,
                "deleted_ranges": deleted_ranges,
                "selection": selection,
                "policies": policies,
                "audit": audit,
                "seeded": seeded,
            }
    except Exception as e:
        logger.warning("hpi_db_restore_failed", error=str(e)[:200])
        return None


async def persist_hpi_to_db(
    records_map: dict[tuple[str, str], list[tuple]],
    deleted_ranges: dict[tuple[str, str], list[list[str]]],
    selection: list[dict],
    policies: list[dict],
    audit: list[dict],
    seeded: bool,
) -> bool:
    """
    Persist full HPI state and records to Supabase PostgreSQL.
    """
    factory = get_async_session_factory()
    if factory is None:
        return False

    try:
        # Convert deleted ranges to string keys
        d_ranges_json = {
            f"{s}|{c}": ranges
            for (s, c), ranges in deleted_ranges.items()
            if ranges
        }

        async with factory() as session:
            # 1. Upsert global state
            await session.execute(
                text("""
                    INSERT INTO hpi_state (id, selection_json, policies_json, audit_json, deleted_ranges_json, seeded, updated_at)
                    VALUES ('global', CAST(:sel AS JSONB), CAST(:pol AS JSONB), CAST(:aud AS JSONB), CAST(:del AS JSONB), :sd, now())
                    ON CONFLICT (id) DO UPDATE SET
                        selection_json = EXCLUDED.selection_json,
                        policies_json = EXCLUDED.policies_json,
                        audit_json = EXCLUDED.audit_json,
                        deleted_ranges_json = EXCLUDED.deleted_ranges_json,
                        seeded = EXCLUDED.seeded,
                        updated_at = now()
                """),
                {
                    "sel": json.dumps(selection),
                    "pol": json.dumps(policies),
                    "aud": json.dumps(audit),
                    "del": json.dumps(d_ranges_json),
                    "sd": seeded,
                }
            )

            # 2. Upsert each dataset
            for (sym, cat), recs in records_map.items():
                count = len(recs)
                if count == 0:
                    await session.execute(
                        text("DELETE FROM hpi_datasets WHERE symbol = :sym AND category = :cat"),
                        {"sym": sym, "cat": cat}
                    )
                    continue

                oldest_ts = datetime.fromtimestamp(recs[0][0], tz=timezone.utc) if recs else None
                newest_ts = datetime.fromtimestamp(recs[-1][0], tz=timezone.utc) if recs else None
                bytes_est = count * 32

                # Store records as JSON list
                recs_json = json.dumps(recs)
                await session.execute(
                    text("""
                        INSERT INTO hpi_datasets (symbol, category, record_count, storage_bytes, oldest_ts, newest_ts, records_json, updated_at)
                        VALUES (:sym, :cat, :cnt, :b, :old_ts, :new_ts, CAST(:recs AS JSONB), now())
                        ON CONFLICT (symbol, category) DO UPDATE SET
                            record_count = EXCLUDED.record_count,
                            storage_bytes = EXCLUDED.storage_bytes,
                            oldest_ts = EXCLUDED.oldest_ts,
                            newest_ts = EXCLUDED.newest_ts,
                            records_json = EXCLUDED.records_json,
                            updated_at = now()
                    """),
                    {
                        "sym": sym,
                        "cat": cat,
                        "cnt": count,
                        "b": bytes_est,
                        "old_ts": oldest_ts,
                        "new_ts": newest_ts,
                        "recs": recs_json,
                    }
                )

            await session.commit()
            logger.info("hpi_db_state_saved", datasets_saved=len(records_map))
            return True
    except Exception as e:
        logger.warning("hpi_db_persist_failed", error=str(e)[:200])
        return False
