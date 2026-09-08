-- ============================================================
-- Phase 1: ATR at prediction time (needed for outcome labeling)
-- Nullable so existing rows stay valid; rows without ATR are unsettleable.
-- ============================================================
ALTER TABLE ml_predictions
    ADD COLUMN IF NOT EXISTS atr_at_t DOUBLE PRECISION;
