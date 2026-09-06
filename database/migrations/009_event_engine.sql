-- Migration 009: Event Intelligence & Opportunity Engine v3 Tables
-- Covers canonical events, source attribution, lifecycle transitions, impact mapping, scores, and anti-lookahead prediction snapshots.

CREATE TABLE IF NOT EXISTS market_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_event_id TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    event_type TEXT NOT NULL,
    sub_type TEXT,
    entity_id TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    sector TEXT DEFAULT 'BANKING',
    event_timestamp TIMESTAMPTZ NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata',
    timestamp_precision TEXT NOT NULL DEFAULT 'EXACT',
    verification_status TEXT NOT NULL DEFAULT 'UNVERIFIED',
    certainty TEXT NOT NULL DEFAULT 'CONFIRMED',
    expected_direction TEXT NOT NULL DEFAULT 'UNKNOWN',
    time_horizon TEXT NOT NULL DEFAULT 'INTRADAY',
    temporal_phase TEXT NOT NULL DEFAULT 'SCHEDULED',
    processing_flags JSONB NOT NULL DEFAULT '{"discovered": true, "verified": false, "classified": false, "impact_mapped": false, "scored": false}'::jsonb,
    source_priority TEXT NOT NULL DEFAULT 'PRIMARY',
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_market_events_timestamp ON market_events(event_timestamp);
CREATE INDEX IF NOT EXISTS idx_market_events_type ON market_events(event_type);
CREATE INDEX IF NOT EXISTS idx_market_events_entity ON market_events(entity_id);
CREATE INDEX IF NOT EXISTS idx_market_events_phase ON market_events(temporal_phase);

-- Ingested Source Records and Lineage
CREATE TABLE IF NOT EXISTS event_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_event_id TEXT NOT NULL REFERENCES market_events(canonical_event_id) ON DELETE CASCADE,
    source_name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_url TEXT,
    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    fetch_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_verified BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_event_sources_event ON event_sources(canonical_event_id);

-- Immutable Lifecycle Transition Audit Log
CREATE TABLE IF NOT EXISTS event_lifecycle_transitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_event_id TEXT NOT NULL REFERENCES market_events(canonical_event_id) ON DELETE CASCADE,
    from_phase TEXT NOT NULL,
    to_phase TEXT NOT NULL,
    reason TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT 'EVENT_ENGINE',
    event_version INT NOT NULL DEFAULT 1,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    transition_metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_event_transitions_event ON event_lifecycle_transitions(canonical_event_id);
CREATE INDEX IF NOT EXISTS idx_event_transitions_ts ON event_lifecycle_transitions(timestamp DESC);

-- Impact Mapping Matrix
CREATE TABLE IF NOT EXISTS event_impact_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_event_id TEXT NOT NULL REFERENCES market_events(canonical_event_id) ON DELETE CASCADE,
    target_type TEXT NOT NULL,
    target_symbol TEXT NOT NULL,
    impact_strength TEXT NOT NULL,
    relationship_confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    historical_sensitivity DOUBLE PRECISION,
    primary_or_secondary TEXT NOT NULL DEFAULT 'PRIMARY',
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_event_impact_symbol ON event_impact_mappings(target_symbol);
CREATE INDEX IF NOT EXISTS idx_event_impact_event ON event_impact_mappings(canonical_event_id);

-- Versioned Event Scores Snapshot
CREATE TABLE IF NOT EXISTS event_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_event_id TEXT NOT NULL REFERENCES market_events(canonical_event_id) ON DELETE CASCADE,
    formula_version TEXT NOT NULL DEFAULT 'v3.0.0',
    importance_score DOUBLE PRECISION,
    importance_breakdown JSONB NOT NULL DEFAULT '{}'::jsonb,
    market_impact_score DOUBLE PRECISION,
    market_impact_status TEXT NOT NULL DEFAULT 'INSUFFICIENT_DATA',
    market_impact_breakdown JSONB NOT NULL DEFAULT '{}'::jsonb,
    opportunity_score DOUBLE PRECISION,
    opportunity_status TEXT NOT NULL DEFAULT 'INSUFFICIENT_DATA',
    opportunity_breakdown JSONB NOT NULL DEFAULT '{}'::jsonb,
    final_decision TEXT NOT NULL DEFAULT 'NO_TRADE',
    gate_evaluation JSONB NOT NULL DEFAULT '{}'::jsonb,
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_event_scores_event ON event_scores(canonical_event_id);

-- Immutable Prediction Snapshots with Anti-Lookahead Cutoffs
CREATE TABLE IF NOT EXISTS event_prediction_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_event_id TEXT NOT NULL REFERENCES market_events(canonical_event_id) ON DELETE CASCADE,
    prediction_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    data_cutoff_timestamp TIMESTAMPTZ NOT NULL,
    feature_cutoff_timestamp TIMESTAMPTZ NOT NULL,
    formula_version TEXT NOT NULL,
    configuration_version TEXT NOT NULL,
    importance_score DOUBLE PRECISION,
    market_impact_score DOUBLE PRECISION,
    opportunity_score DOUBLE PRECISION,
    predicted_direction TEXT NOT NULL DEFAULT 'UNKNOWN',
    confidence DOUBLE PRECISION DEFAULT 0.0,
    strategy_state TEXT NOT NULL DEFAULT 'NO_SETUP',
    decision TEXT NOT NULL DEFAULT 'NO_TRADE',
    snapshot_immutable BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_event_predictions_event ON event_prediction_snapshots(canonical_event_id);
CREATE INDEX IF NOT EXISTS idx_event_predictions_cutoff ON event_prediction_snapshots(data_cutoff_timestamp);

-- Historical Comparables Match
CREATE TABLE IF NOT EXISTS event_comparables (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_event_id TEXT NOT NULL REFERENCES market_events(canonical_event_id) ON DELETE CASCADE,
    past_event_id TEXT NOT NULL,
    past_event_date DATE NOT NULL,
    similarity_score DOUBLE PRECISION NOT NULL,
    key_comparison_factor TEXT,
    past_market_reaction JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_event_comparables_event ON event_comparables(canonical_event_id);
