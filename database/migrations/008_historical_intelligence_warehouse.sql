-- Migration 008: Historical Intelligence Engine (HIE) Warehouse Tables — §§3.1, 4, 11
-- Stores Point-in-Time Historical State Snapshots and Supervised Multi-Horizon Outcomes (15m, 30m, 60m).

CREATE TABLE IF NOT EXISTS hie_state_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    instrument TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    trading_date DATE NOT NULL,
    session TEXT NOT NULL,
    minute_of_session INT NOT NULL DEFAULT 0,
    market_regime TEXT NOT NULL,
    volatility_regime TEXT NOT NULL,
    vix_bucket TEXT NOT NULL,
    data_quality_score DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    feature_version TEXT NOT NULL,
    embedding_version TEXT NOT NULL,
    raw_features_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    normalized_features_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding_vector FLOAT[] NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hie_snapshots_inst_tf ON hie_state_snapshots(instrument, timeframe);
CREATE INDEX IF NOT EXISTS idx_hie_snapshots_ts ON hie_state_snapshots(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_hie_snapshots_regime ON hie_state_snapshots(market_regime);
CREATE INDEX IF NOT EXISTS idx_hie_snapshots_date ON hie_state_snapshots(trading_date);

-- Multi-Horizon Forward Outcomes Table (§11)
CREATE TABLE IF NOT EXISTS hie_forward_outcomes (
    snapshot_id TEXT PRIMARY KEY REFERENCES hie_state_snapshots(snapshot_id) ON DELETE CASCADE,
    entry_price DOUBLE PRECISION NOT NULL,
    return_15m DOUBLE PRECISION,
    direction_15m TEXT,
    mfe_15m DOUBLE PRECISION,
    mae_15m DOUBLE PRECISION,
    target_hit_15m BOOLEAN,
    stop_hit_15m BOOLEAN,
    return_30m DOUBLE PRECISION,
    direction_30m TEXT,
    mfe_30m DOUBLE PRECISION,
    mae_30m DOUBLE PRECISION,
    target_hit_30m BOOLEAN,
    stop_hit_30m BOOLEAN,
    return_60m DOUBLE PRECISION,
    direction_60m TEXT,
    mfe_60m DOUBLE PRECISION,
    mae_60m DOUBLE PRECISION,
    target_hit_60m BOOLEAN,
    stop_hit_60m BOOLEAN,
    outcome_version TEXT NOT NULL,
    labeled_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hie_outcomes_labeled ON hie_forward_outcomes(labeled_at);

-- Query Audit Table (§36)
CREATE TABLE IF NOT EXISTS hie_query_audit (
    query_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instrument TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    query_mode TEXT NOT NULL,
    sample_count INT NOT NULL,
    effective_sample_size DOUBLE PRECISION NOT NULL,
    bullish_prob DOUBLE PRECISION NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    latency_ms DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hie_audit_inst ON hie_query_audit(instrument, created_at DESC);
