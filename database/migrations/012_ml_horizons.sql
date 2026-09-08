-- ============================================================
-- Phase 0: multi-horizon predictions + calibration
-- Nullable columns so pre-existing ml_predictions rows stay valid.
-- ============================================================
ALTER TABLE ml_predictions
    ADD COLUMN IF NOT EXISTS horizon_minutes INTEGER,
    ADD COLUMN IF NOT EXISTS target_spec_version TEXT,
    ADD COLUMN IF NOT EXISTS model_source TEXT,
    ADD COLUMN IF NOT EXISTS outcome_label INTEGER,
    ADD COLUMN IF NOT EXISTS outcome_spot DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS settled_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_ml_predictions_horizon
    ON ml_predictions(symbol, horizon_minutes, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_ml_predictions_settled
    ON ml_predictions(symbol, horizon_minutes) WHERE outcome_label IS NOT NULL;
