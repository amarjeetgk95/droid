-- Migration 007: Historical Pattern Intelligence (HPI) & Historical Intelligence Persistence
-- Tables to persist HPI datasets, selections, retention policies, and audit logs to Supabase PostgreSQL.

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
