-- Migration 017: Historical Data Management Module Schema
-- Relational metadata, version tracking, download jobs, session gaps, and quality gating.

-- 1. Historical Datasets Catalog
CREATE TABLE IF NOT EXISTS historical_datasets (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'fyers',
    status TEXT NOT NULL DEFAULT 'INITIALIZED',
    current_version_id TEXT,
    earliest_available_ts TIMESTAMPTZ,
    latest_available_ts TIMESTAMPTZ,
    total_candles BIGINT NOT NULL DEFAULT 0,
    latest_quality_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    storage_bytes BIGINT NOT NULL DEFAULT 0,
    parquet_relative_path TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hist_datasets_sym_tf ON historical_datasets(symbol, timeframe);
CREATE INDEX IF NOT EXISTS idx_hist_datasets_status ON historical_datasets(status);

-- 2. Historical Dataset Versions (Point-in-Time Reproducibility)
CREATE TABLE IF NOT EXISTS historical_dataset_versions (
    version_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL REFERENCES historical_datasets(id) ON DELETE CASCADE,
    version_tag TEXT NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    row_count BIGINT NOT NULL DEFAULT 0,
    checksum_sha256 TEXT NOT NULL,
    quality_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    quality_status TEXT NOT NULL DEFAULT 'PASSED',
    parquet_path TEXT NOT NULL,
    lineage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    methodology_events_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hist_versions_dataset ON historical_dataset_versions(dataset_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_hist_versions_checksum ON historical_dataset_versions(checksum_sha256);

-- 3. Historical Download Jobs
CREATE TABLE IF NOT EXISTS historical_download_jobs (
    job_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL REFERENCES historical_datasets(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'fyers',
    range_from DATE NOT NULL,
    range_to DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'QUEUED',
    progress_pct DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    total_chunks INT NOT NULL DEFAULT 0,
    completed_chunks INT NOT NULL DEFAULT 0,
    rows_downloaded BIGINT NOT NULL DEFAULT 0,
    rows_valid BIGINT NOT NULL DEFAULT 0,
    rows_rejected BIGINT NOT NULL DEFAULT 0,
    retry_count INT NOT NULL DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hist_jobs_status ON historical_download_jobs(status);
CREATE INDEX IF NOT EXISTS idx_hist_jobs_created ON historical_download_jobs(created_at DESC);

-- 4. Historical Download Chunks (Automated 100-day slices)
CREATE TABLE IF NOT EXISTS historical_download_chunks (
    chunk_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES historical_download_jobs(job_id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    range_from DATE NOT NULL,
    range_to DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    rows_fetched BIGINT NOT NULL DEFAULT 0,
    retries INT NOT NULL DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_hist_chunks_job ON historical_download_chunks(job_id, chunk_index);

-- 5. Historical Data Gaps Ledger
CREATE TABLE IF NOT EXISTS historical_data_gaps (
    gap_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL REFERENCES historical_datasets(id) ON DELETE CASCADE,
    trading_date DATE NOT NULL,
    expected_candles INT NOT NULL,
    actual_candles INT NOT NULL,
    missing_candles INT NOT NULL,
    first_missing_ts TIMESTAMPTZ,
    last_missing_ts TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'OPEN',
    repair_attempts INT NOT NULL DEFAULT 0,
    last_repair_attempt TIMESTAMPTZ,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hist_gaps_dataset_date ON historical_data_gaps(dataset_id, trading_date);
CREATE INDEX IF NOT EXISTS idx_hist_gaps_status ON historical_data_gaps(status);

-- 6. Historical Quality Reports
CREATE TABLE IF NOT EXISTS historical_quality_reports (
    report_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL REFERENCES historical_datasets(id) ON DELETE CASCADE,
    version_id TEXT REFERENCES historical_dataset_versions(version_id) ON DELETE SET NULL,
    quality_score DOUBLE PRECISION NOT NULL,
    status TEXT NOT NULL,
    hard_gates_passed BOOLEAN NOT NULL DEFAULT true,
    completeness_score DOUBLE PRECISION NOT NULL DEFAULT 100.0,
    temporal_continuity_score DOUBLE PRECISION NOT NULL DEFAULT 100.0,
    sanity_score DOUBLE PRECISION NOT NULL DEFAULT 100.0,
    total_rows BIGINT NOT NULL DEFAULT 0,
    valid_rows BIGINT NOT NULL DEFAULT 0,
    invalid_rows BIGINT NOT NULL DEFAULT 0,
    duplicate_rows BIGINT NOT NULL DEFAULT 0,
    missing_candles BIGINT NOT NULL DEFAULT 0,
    ohlc_violations BIGINT NOT NULL DEFAULT 0,
    details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hist_quality_dataset ON historical_quality_reports(dataset_id, created_at DESC);
