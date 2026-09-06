-- Migration 010: Event Engine Phase 2 Tables — Live Opportunity Intelligence
-- Tables for Alert Queue, Post-Event Outcomes, and Shadow Signals Integration

CREATE TABLE IF NOT EXISTS event_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_id TEXT UNIQUE NOT NULL,
    canonical_event_id TEXT NOT NULL REFERENCES market_events(canonical_event_id) ON DELETE CASCADE,
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'MEDIUM',
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    dedup_signature TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING_REVIEW',
    cooldown_until TIMESTAMPTZ NOT NULL,
    acknowledged_by TEXT,
    acknowledged_at TIMESTAMPTZ,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_event_alerts_canonical ON event_alerts(canonical_event_id);
CREATE INDEX IF NOT EXISTS idx_event_alerts_status ON event_alerts(status);
CREATE INDEX IF NOT EXISTS idx_event_alerts_signature ON event_alerts(dedup_signature);

CREATE TABLE IF NOT EXISTS event_outcomes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_event_id TEXT UNIQUE NOT NULL REFERENCES market_events(canonical_event_id) ON DELETE CASCADE,
    measured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    predicted_direction TEXT NOT NULL,
    actual_direction TEXT NOT NULL,
    prediction_correct BOOLEAN NOT NULL DEFAULT FALSE,
    initial_move_pct DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    maximum_move_pct DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    mfe_pct DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    mae_pct DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    time_to_peak_min INT NOT NULL DEFAULT 0,
    time_to_reversal_min INT,
    realized_volatility_change DOUBLE PRECISION,
    iv_change_pct DOUBLE PRECISION,
    oi_change_pct DOUBLE PRECISION,
    primary_instrument TEXT NOT NULL,
    monitoring_snapshots JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_settled BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_event_outcomes_event ON event_outcomes(canonical_event_id);
CREATE INDEX IF NOT EXISTS idx_event_outcomes_correct ON event_outcomes(prediction_correct);

CREATE TABLE IF NOT EXISTS event_shadow_signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shadow_signal_id TEXT UNIQUE NOT NULL,
    canonical_event_id TEXT NOT NULL REFERENCES market_events(canonical_event_id) ON DELETE CASCADE,
    base_signal_id TEXT NOT NULL,
    underlying TEXT NOT NULL,
    strategy TEXT NOT NULL,
    direction TEXT NOT NULL,
    execution_mode TEXT NOT NULL DEFAULT 'SHADOW_MODE',
    event_importance_score DOUBLE PRECISION NOT NULL,
    event_market_impact_score DOUBLE PRECISION,
    event_opportunity_score DOUBLE PRECISION NOT NULL,
    suggested_sizing_factor DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    simulated_entry_price DOUBLE PRECISION,
    simulated_exit_price DOUBLE PRECISION,
    simulated_pnl_pct DOUBLE PRECISION,
    shadow_status TEXT NOT NULL DEFAULT 'TRACKING',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_event_shadow_event ON event_shadow_signals(canonical_event_id);
CREATE INDEX IF NOT EXISTS idx_event_shadow_signal ON event_shadow_signals(base_signal_id);
