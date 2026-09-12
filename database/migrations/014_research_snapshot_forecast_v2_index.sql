-- ============================================================
-- P0-3 (forecast 1h-v2): snapshot lookup index for audit trail.
-- research_snapshots already exists (011); this only adds the
-- (instrument, timestamp) composite used to list/reconstruct the
-- market state behind persisted trend_forecast_* predictions.
-- Additive only — never edits applied migrations.
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_research_snapshots_inst_ts
    ON research_snapshots(instrument, timestamp DESC);
