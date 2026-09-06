export type VerificationStatus =
  | 'UNVERIFIED'
  | 'PARTIALLY_VERIFIED'
  | 'VERIFIED'
  | 'CONFLICTING'
  | 'CANCELLED'
  | 'RESCHEDULED';

export type EventCertainty =
  | 'CONFIRMED'
  | 'LIKELY'
  | 'EXPECTED'
  | 'APPROXIMATE'
  | 'RUMORED'
  | 'UNKNOWN';

export type TimestampPrecision = 'EXACT' | 'DATE_ONLY' | 'APPROXIMATE' | 'UNKNOWN';

export type ExpectedDirection = 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'TWO_SIDED' | 'UNKNOWN';

export type TimeHorizon = 'SCALP' | 'INTRADAY' | 'SWING' | 'MULTI_DAY' | 'LONG_TERM' | 'UNKNOWN';

export type EventType =
  | 'MACRO'
  | 'CENTRAL_BANK'
  | 'COMPANY'
  | 'EARNINGS'
  | 'CORPORATE_ACTION'
  | 'REGULATORY'
  | 'POLICY'
  | 'GLOBAL'
  | 'GEOPOLITICAL'
  | 'SECTOR'
  | 'OTHER';

export type TemporalPhase = 'SCHEDULED' | 'APPROACHING' | 'ACTIVE' | 'POST_EVENT' | 'ARCHIVED';

export type TradingDecision = 'NO_TRADE' | 'WAIT_FOR_CONFIRMATION' | 'EXECUTE_SHADOW' | 'EXECUTE_ACTIVE';

export interface RawSourceEvent {
  source_name: string;
  source_type: string;
  source_url?: string;
  raw_payload?: Record<string, unknown>;
  fetch_timestamp: string;
  is_verified: boolean;
}

export interface EventImpactMapping {
  target_type: 'SECTOR' | 'INDEX' | 'STOCK' | 'DERIVATIVE';
  target_symbol: string;
  impact_strength: 'HIGH' | 'MEDIUM' | 'LOW';
  relationship_confidence: number;
  historical_sensitivity?: number;
  primary_or_secondary: 'PRIMARY' | 'SECONDARY';
  notes?: string;
}

export interface ImportanceScoreBreakdown {
  final_score: number;
  source_authority: number;
  scope: number;
  historical_significance: number;
  policy_impact: number;
  surprise_potential: number;
  weights_applied: Record<string, number>;
  excluded_components: string[];
  formula_version: string;
}

export interface MarketImpactBreakdown {
  status: 'SCORED' | 'INSUFFICIENT_DATA' | 'EXCLUDED';
  final_score?: number | null;
  historical_move_percentile?: number | null;
  liquidity_and_sensitivity?: number | null;
  volatility_regime?: number | null;
  positioning_skew?: number | null;
  event_proximity?: number | null;
  reason?: string;
}

export interface OpportunityScoreBreakdown {
  status: 'SCORED' | 'INSUFFICIENT_DATA' | 'NO_TRADE';
  final_score?: number | null;
  setup_quality?: number | null;
  liquidity_and_spread?: number | null;
  signal_confidence?: number | null;
  risk_reward?: number | null;
  confirmation_state?: number | null;
  passed_gates: string[];
  failed_gates: string[];
  final_decision: TradingDecision;
  reason?: string;
}

export interface EventScoreSnapshot {
  canonical_event_id: string;
  formula_version: string;
  importance: ImportanceScoreBreakdown;
  market_impact: MarketImpactBreakdown;
  opportunity: OpportunityScoreBreakdown;
  final_decision: TradingDecision;
  calculated_at: string;
}

export interface PredictionSnapshot {
  prediction_id: string;
  canonical_event_id: string;
  prediction_timestamp: string;
  data_cutoff_timestamp: string;
  feature_cutoff_timestamp: string;
  formula_version: string;
  configuration_version: string;
  importance_score?: number | null;
  market_impact_score?: number | null;
  opportunity_score?: number | null;
  predicted_direction: ExpectedDirection;
  confidence: number;
  strategy_state: string;
  decision: TradingDecision;
  snapshot_immutable: boolean;
}

export interface EventComparable {
  past_event_id: string;
  past_event_date: string;
  similarity_score: number;
  key_comparison_factor?: string;
  past_market_reaction?: Record<string, unknown>;
}

export interface CanonicalEvent {
  id: string;
  canonical_event_id: string;
  title: string;
  description?: string;
  event_type: EventType;
  sub_type?: string;
  entity_id: string;
  entity_name: string;
  sector: string;
  event_timestamp: string;
  timezone: string;
  timestamp_precision: TimestampPrecision;
  verification_status: VerificationStatus;
  certainty: EventCertainty;
  expected_direction: ExpectedDirection;
  time_horizon: TimeHorizon;
  temporal_phase: TemporalPhase;
  processing_flags: {
    discovered: boolean;
    verified: boolean;
    classified: boolean;
    impact_mapped: boolean;
    scored: boolean;
  };
  source_priority: string;
  metadata?: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  sources: RawSourceEvent[];
  impact_mappings: EventImpactMapping[];
  scores?: EventScoreSnapshot;
  latest_prediction?: PredictionSnapshot;
  comparables: EventComparable[];
}

export interface LiveOptionsContext {
  underlying: string;
  spot_price: number;
  futures_price: number;
  basis_points: number;
  expiry: string;
  days_to_expiry: number;
  atm_strike: number;
  atm_iv?: number | null;
  atm_straddle_price?: number | null;
  pcr_oi: number;
  pcr_volume: number;
  total_call_oi: number;
  total_put_oi: number;
  expected_move_points?: number | null;
  expected_move_pct?: number | null;
  bid_ask_spread_pct: number;
  spread_acceptable: boolean;
  liquidity_acceptable: boolean;
  iv_crush_risk_level: string;
  market_data_valid: boolean;
  diagnostics?: Record<string, unknown>;
  sampled_at: string;
}

export interface LiveOpportunityResponse {
  canonical_event_id: string;
  underlying: string;
  live_options: LiveOptionsContext;
  opportunity_score: OpportunityScoreBreakdown;
  strategy_state: string;
  execution_mode: string;
}

export type AlertType =
  | 'EVENT_DISCOVERED'
  | 'EVENT_VERIFIED'
  | 'EVENT_APPROACHING'
  | 'SETUP_DEVELOPING'
  | 'OPPORTUNITY_CONFIRMED'
  | 'NO_TRADE'
  | 'EVENT_ACTIVE'
  | 'EVENT_COMPLETED'
  | 'OUTCOME_AVAILABLE';

export interface EventAlert {
  alert_id: string;
  canonical_event_id: string;
  alert_type: AlertType;
  severity: 'INFO' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  title: string;
  message: string;
  dedup_signature: string;
  status: 'PENDING_REVIEW' | 'ACKNOWLEDGED' | 'SUPPRESSED';
  cooldown_until: string;
  acknowledged_by?: string | null;
  acknowledged_at?: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface MonitoringSnapshot {
  interval_label: string;
  timestamp: string;
  price: number;
  iv?: number | null;
  oi?: number | null;
  move_from_baseline_pct: number;
}

export interface EventOutcome {
  outcome_id: string;
  canonical_event_id: string;
  measured_at: string;
  predicted_direction: ExpectedDirection;
  actual_direction: ExpectedDirection;
  prediction_correct: boolean;
  initial_move_pct: number;
  maximum_move_pct: number;
  mfe_pct: number;
  mae_pct: number;
  time_to_peak_min: number;
  time_to_reversal_min?: number | null;
  realized_volatility_change?: number | null;
  iv_change_pct?: number | null;
  oi_change_pct?: number | null;
  primary_instrument: string;
  monitoring_snapshots: MonitoringSnapshot[];
  is_settled: boolean;
}

export interface ShadowSignalRecord {
  shadow_signal_id: string;
  canonical_event_id: string;
  base_signal_id: string;
  underlying: string;
  strategy: string;
  direction: string;
  execution_mode: string;
  event_importance_score: number;
  event_market_impact_score?: number | null;
  event_opportunity_score: number;
  suggested_sizing_factor: number;
  simulated_entry_price?: number | null;
  simulated_exit_price?: number | null;
  simulated_pnl_pct?: number | null;
  shadow_status: string;
  created_at: string;
}

export type ProximityState = 'NORMAL' | 'APPROACHING_WINDOW' | 'BLACKOUT_WINDOW' | 'REACTION_WINDOW';

export interface EventRiskParameters {
  underlying: string;
  proximity_state: ProximityState;
  can_enter: boolean;
  sizing_multiplier: number;
  max_loss_dampener: number;
  prohibit_naked_options: boolean;
  rejection_reason?: string | null;
  triggering_event_id?: string | null;
  triggering_event_title?: string | null;
  minutes_to_event?: number | null;
  evaluated_at: string;
}

export type SourceHealthStatus = 'HEALTHY' | 'DEGRADED' | 'OFFLINE';
export type CircuitState = 'CLOSED' | 'HALF_OPEN' | 'OPEN';

export interface SourceHealthRecord {
  source_name: string;
  status: SourceHealthStatus;
  circuit_state: CircuitState;
  last_sync_timestamp?: string | null;
  last_latency_ms: number;
  success_count: number;
  error_count: number;
  consecutive_errors: number;
  circuit_cooldown_until?: string | null;
  last_error_message?: string | null;
}

export interface SourceHealthTelemetry {
  overall_status: SourceHealthStatus;
  sources: Record<string, SourceHealthRecord>;
  active_circuit_breakers: string[];
  evaluated_at: string;
}

export interface EventTrackRecord {
  total_events_evaluated: number;
  settled_events_count: number;
  shadow_trades_count: number;
  directional_accuracy_pct: number;
  shadow_win_rate_pct: number;
  profit_factor: number;
  average_expectancy_r: number;
  average_mfe_pct: number;
  average_mae_pct: number;
  average_realized_iv_crush_pct: number;
  sample_size_gate_passed: boolean;
  minimum_sample_required: number;
  recommendation: 'ACCUMULATE_MORE_EVENTS' | 'CALIBRATION_STABLE' | 'READY_FOR_PAPER_PILOT';
  breakdown_by_event_type: Record<string, { count: number }>;
  calculated_at: string;
}

export interface HistoricalEventDistribution {
  event_category: string;
  sample_size: number;
  median_move_pct: number;
  percentile_75_move_pct: number;
  percentile_90_move_pct: number;
  max_observed_move_pct: number;
  typical_iv_expansion_pct: number;
  typical_iv_crush_pct: number;
}

export interface CalibrationSummary {
  total_calibrated_events: number;
  categories_covered: string[];
  formula_version: string;
  last_calibrated_at: string;
  distributions: Record<string, HistoricalEventDistribution>;
}
