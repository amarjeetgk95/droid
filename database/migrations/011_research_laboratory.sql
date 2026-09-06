-- Migration 011: Chart Intelligence & Indicator Research Laboratory (Phases 0-7)
-- Standalone, non-production research tables for:
-- 1. Indicator Definitions and Versions
-- 2. Market State Snapshots
-- 3. Immutable Predictions and Separate Append-Only Outcomes
-- 4. Offline Validation Experiments and Runs
-- 5. Comparative Evaluation Runs
-- 6. Chart Annotations & Research Notes

-- 1. Indicator Registry Tables (§13, §14)
CREATE TABLE IF NOT EXISTS research_indicator_definitions (
    indicator_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL, -- STANDARD, STRUCTURAL, DERIVATIVE, PROPRIETARY, EXPERIMENTAL
    description TEXT,
    author TEXT DEFAULT 'system',
    lifecycle TEXT NOT NULL DEFAULT 'EXPERIMENTAL', -- EXPERIMENTAL, VALIDATING, CANDIDATE, COMPARISON, INCUBATION, SHADOW, PRODUCTION, RETIRED
    current_version TEXT NOT NULL DEFAULT '0.1.0',
    supported_timeframes JSONB NOT NULL DEFAULT '["1m", "5m", "15m", "1h", "1D"]'::jsonb,
    supported_instruments JSONB NOT NULL DEFAULT '["NIFTY 50", "BANKNIFTY", "SENSEX"]'::jsonb,
    formula_summary TEXT,
    parameters_schema JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_indicators_category ON research_indicator_definitions(category);
CREATE INDEX IF NOT EXISTS idx_research_indicators_lifecycle ON research_indicator_definitions(lifecycle);

CREATE TABLE IF NOT EXISTS research_indicator_versions (
    version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    indicator_id TEXT NOT NULL REFERENCES research_indicator_definitions(indicator_id) ON DELETE CASCADE,
    version TEXT NOT NULL,
    changelog TEXT,
    parameters_schema JSONB NOT NULL DEFAULT '{}'::jsonb,
    code_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_research_indicator_version UNIQUE (indicator_id, version)
);

CREATE INDEX IF NOT EXISTS idx_research_versions_indicator ON research_indicator_versions(indicator_id);

-- 2. Research Snapshots (§25)
CREATE TABLE IF NOT EXISTS research_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    instrument TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    price DOUBLE PRECISION NOT NULL,
    regime TEXT,
    session TEXT,
    features JSONB NOT NULL DEFAULT '{}'::jsonb,
    options_context JSONB,
    data_quality TEXT NOT NULL DEFAULT 'LIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_snapshots_inst_tf ON research_snapshots(instrument, timeframe);
CREATE INDEX IF NOT EXISTS idx_research_snapshots_ts ON research_snapshots(timestamp DESC);

-- 3. Immutable Predictions (§26, N5)
CREATE TABLE IF NOT EXISTS research_predictions (
    prediction_id TEXT PRIMARY KEY,
    indicator_id TEXT NOT NULL REFERENCES research_indicator_definitions(indicator_id) ON DELETE RESTRICT,
    indicator_version TEXT NOT NULL,
    instrument TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    current_price DOUBLE PRECISION NOT NULL,
    direction TEXT NOT NULL, -- BULLISH, BEARISH, NEUTRAL, UNKNOWN
    score DOUBLE PRECISION NOT NULL, -- normalized [-100, 100]
    confidence DOUBLE PRECISION NOT NULL, -- [0.0, 1.0]
    raw_value JSONB,
    normalized_value DOUBLE PRECISION,
    component_values JSONB NOT NULL DEFAULT '{}'::jsonb,
    forecast_horizon TEXT NOT NULL, -- 5m, 15m, 30m, 1h, 4h, NEXT_DAY
    horizon_candles INT NOT NULL DEFAULT 5,
    target_price DOUBLE PRECISION,
    invalidation_price DOUBLE PRECISION,
    snapshot_id TEXT REFERENCES research_snapshots(snapshot_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_preds_indicator ON research_predictions(indicator_id, indicator_version);
CREATE INDEX IF NOT EXISTS idx_research_preds_inst_tf ON research_predictions(instrument, timeframe);
CREATE INDEX IF NOT EXISTS idx_research_preds_ts ON research_predictions(timestamp DESC);

-- 4. Separate Append-Only Outcomes (§26, N5)
CREATE TABLE IF NOT EXISTS research_prediction_outcomes (
    outcome_id TEXT PRIMARY KEY,
    prediction_id TEXT NOT NULL UNIQUE REFERENCES research_predictions(prediction_id) ON DELETE CASCADE,
    actual_direction TEXT NOT NULL,
    actual_price_move DOUBLE PRECISION NOT NULL,
    actual_pct_move DOUBLE PRECISION NOT NULL,
    entry_price DOUBLE PRECISION NOT NULL,
    exit_price DOUBLE PRECISION NOT NULL,
    mfe DOUBLE PRECISION NOT NULL, -- Maximum Favorable Excursion
    mae DOUBLE PRECISION NOT NULL, -- Maximum Adverse Excursion
    target_hit BOOLEAN NOT NULL DEFAULT FALSE,
    stop_hit BOOLEAN NOT NULL DEFAULT FALSE,
    time_to_target_sec DOUBLE PRECISION,
    is_correct BOOLEAN NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_outcomes_pred ON research_prediction_outcomes(prediction_id);
CREATE INDEX IF NOT EXISTS idx_research_outcomes_eval ON research_prediction_outcomes(evaluated_at DESC);

-- 5. Offline Experiments & Runs (§19, §20, §39)
CREATE TABLE IF NOT EXISTS research_experiment_definitions (
    experiment_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    indicator_id TEXT NOT NULL REFERENCES research_indicator_definitions(indicator_id) ON DELETE CASCADE,
    indicator_version TEXT NOT NULL,
    instrument TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    forecast_horizon TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS research_experiment_runs (
    run_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES research_experiment_definitions(experiment_id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'PENDING', -- PENDING, RUNNING, COMPLETED, FAILED
    sample_count INT NOT NULL DEFAULT 0,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_runs_exp ON research_experiment_runs(experiment_id);
CREATE INDEX IF NOT EXISTS idx_research_runs_status ON research_experiment_runs(status);

-- 6. Indicator Comparison Runs (§30, §31)
CREATE TABLE IF NOT EXISTS research_comparison_runs (
    comparison_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    indicators JSONB NOT NULL, -- array of indicator IDs
    instrument TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    results JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 7. Chart Annotations & Research Log (§47)
CREATE TABLE IF NOT EXISTS research_annotations (
    annotation_id TEXT PRIMARY KEY,
    instrument TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    title TEXT NOT NULL,
    notes TEXT NOT NULL,
    author TEXT DEFAULT 'researcher',
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_ann_inst_ts ON research_annotations(instrument, timestamp DESC);
