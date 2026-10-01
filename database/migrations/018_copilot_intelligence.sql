-- 018 — Copilot Intelligence persistence (spec §35).
-- Reuses the Supabase PostgreSQL schema. Prediction rows are append-only:
-- outcomes live in a separate table; a second outcome for the same prediction
-- is refused by the UNIQUE constraint on copilot_prediction_outcome.
-- Idempotent: safe to run multiple times.

CREATE TABLE IF NOT EXISTS copilot_prediction (
    prediction_id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    symbol TEXT NOT NULL,
    horizon TEXT NOT NULL,
    intent TEXT NOT NULL,
    market_context JSONB NOT NULL DEFAULT '{}'::JSONB,
    feature_snapshot JSONB NOT NULL DEFAULT '{}'::JSONB,
    prediction JSONB NOT NULL DEFAULT '{}'::JSONB,
    scenarios JSONB NOT NULL DEFAULT '[]'::JSONB,
    probabilities JSONB NOT NULL DEFAULT '{}'::JSONB,
    levels JSONB NOT NULL DEFAULT '{}'::JSONB,
    confidence JSONB NOT NULL DEFAULT '{}'::JSONB,
    model_version TEXT NOT NULL DEFAULT '',
    prompt_version TEXT NOT NULL DEFAULT '',
    copilot_version TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS copilot_prediction_outcome (
    prediction_id TEXT PRIMARY KEY REFERENCES copilot_prediction(prediction_id),
    outcome TEXT NOT NULL,
    realized_return_pct DOUBLE PRECISION NULL,
    realized_direction TEXT NULL,
    level_result TEXT NULL,
    notes TEXT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_copilot_prediction_symbol_time
    ON copilot_prediction (symbol, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_copilot_prediction_horizon_time
    ON copilot_prediction (horizon, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_copilot_prediction_model_version
    ON copilot_prediction (model_version);
