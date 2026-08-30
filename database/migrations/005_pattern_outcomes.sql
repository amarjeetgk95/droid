-- ============================================================
-- Migration: 005_pattern_outcomes
-- Description: Pattern outcome tracking for Historical Intelligence
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- Pattern Outcomes Table
-- ============================================================
CREATE TABLE IF NOT EXISTS pattern_outcomes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    symbol TEXT NOT NULL,
    pattern_type TEXT NOT NULL,
    pattern_name TEXT NOT NULL,
    bias TEXT NOT NULL, -- BULLISH, BEARISH, NEUTRAL
    confidence DOUBLE PRECISION NOT NULL,
    timeframe TEXT NOT NULL,
    trigger_price DOUBLE PRECISION NOT NULL,
    invalidation_level DOUBLE PRECISION NOT NULL,
    target_level DOUBLE PRECISION NOT NULL,
    detection_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    regime_state TEXT, -- Market regime at detection time
    -- Outcome fields (populated by background worker)
    outcome_1d DOUBLE PRECISION, -- Price change % after 1 session
    outcome_3d DOUBLE PRECISION, -- Price change % after 3 sessions
    outcome_5d DOUBLE PRECISION, -- Price change % after 5 sessions
    hit_target_before_invalidation BOOLEAN, -- Did price reach target before invalidation?
    outcome_labeled_at TIMESTAMPTZ, -- When outcomes were computed
    outcome_source TEXT DEFAULT 'background_worker', -- 'background_worker' | 'on_demand' | 'manual'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pattern_outcomes_symbol ON pattern_outcomes(symbol);
CREATE INDEX IF NOT EXISTS idx_pattern_outcomes_pattern_type ON pattern_outcomes(pattern_type);
CREATE INDEX IF NOT EXISTS idx_pattern_outcomes_detection_ts ON pattern_outcomes(detection_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_pattern_outcomes_user_id ON pattern_outcomes(user_id);
CREATE INDEX IF NOT EXISTS idx_pattern_outcomes_labeled ON pattern_outcomes(outcome_labeled_at) WHERE outcome_labeled_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_pattern_outcomes_unlabeled ON pattern_outcomes(detection_timestamp) WHERE outcome_labeled_at IS NULL;

-- ============================================================
-- Pattern Hit Rate Aggregates (Materialized View for fast queries)
-- ============================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS pattern_hit_rates AS
SELECT
    symbol,
    pattern_type,
    pattern_name,
    bias,
    timeframe,
    COUNT(*) AS sample_count,
    ROUND(AVG(outcome_1d)::numeric, 4) AS avg_return_1d,
    ROUND(STDDEV(outcome_1d)::numeric, 4) AS stddev_return_1d,
    ROUND(AVG(outcome_3d)::numeric, 4) AS avg_return_3d,
    ROUND(AVG(outcome_5d)::numeric, 4) AS avg_return_5d,
    ROUND(AVG(CASE WHEN hit_target_before_invalidation THEN 1 ELSE 0 END)::numeric, 4) AS hit_target_rate,
    ROUND(AVG(CASE WHEN bias = 'BULLISH' AND outcome_1d > 0 THEN 1 WHEN bias = 'BEARISH' AND outcome_1d < 0 THEN 1 ELSE 0 END)::numeric, 4) AS directional_accuracy,
    MIN(detection_timestamp) AS first_detection,
    MAX(detection_timestamp) AS last_detection
FROM pattern_outcomes
WHERE outcome_labeled_at IS NOT NULL
GROUP BY symbol, pattern_type, pattern_name, bias, timeframe
WITH NO DATA;

CREATE UNIQUE INDEX IF NOT EXISTS idx_pattern_hit_rates_pk
    ON pattern_hit_rates (symbol, pattern_type, pattern_name, bias, timeframe);

-- ============================================================
-- Trigger: Auto updated_at timestamp
-- ============================================================
DROP TRIGGER IF EXISTS update_pattern_outcomes_updated_at ON public.pattern_outcomes;
CREATE TRIGGER update_pattern_outcomes_updated_at
    BEFORE UPDATE ON public.pattern_outcomes
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- ============================================================
-- Row Level Security (RLS)
-- ============================================================
ALTER TABLE pattern_outcomes ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'pattern_outcomes_select_all') THEN
        CREATE POLICY pattern_outcomes_select_all ON pattern_outcomes FOR SELECT USING (TRUE);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'pattern_outcomes_insert_all') THEN
        CREATE POLICY pattern_outcomes_insert_all ON pattern_outcomes FOR INSERT WITH CHECK (TRUE);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'pattern_outcomes_update_all') THEN
        CREATE POLICY pattern_outcomes_update_all ON pattern_outcomes FOR UPDATE USING (TRUE);
    END IF;
END $$;