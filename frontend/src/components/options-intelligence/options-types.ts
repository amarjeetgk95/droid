export type UnderlyingSymbol = 'NIFTY' | 'BANKNIFTY' | 'SENSEX';
export type TradingHorizon = 'SCALP' | 'INTRADAY' | 'SWING' | 'POSITIONAL';
export type DirectionalBias = 'BULLISH' | 'BEARISH';
export type OptionType = 'CE' | 'PE';
export type StrikeCategory = 'ITM_1' | 'ATM' | 'OTM_1';

export interface SourcedEvidence {
  claim: string;
  source_name: string;
  source_tier: number;
  publication_timestamp: string;
  effect: 'SUPPORTIVE' | 'CONTRADICTORY' | 'NEUTRAL';
  confidence: number;
  url?: string;
}

export interface ContradictionAnalysis {
  strongest_counter_argument: string;
  contradicting_evidence: SourcedEvidence[];
  key_risks: string[];
  invalidation_conditions: string[];
  missing_information: string[];
  counter_weight_score: number;
}

export interface FinancialResearchReport {
  research_id: string;
  underlying: UnderlyingSymbol;
  proposed_direction: DirectionalBias;
  horizon: TradingHorizon;
  created_at: string;
  research_status: 'COMPLETE' | 'FALLBACK_TIMEOUT' | 'INSUFFICIENT_EVIDENCE';
  market_context: 'SUPPORTIVE' | 'CONTRADICTORY' | 'NEUTRAL';
  macro_context: 'SUPPORTIVE' | 'CONTRADICTORY' | 'NEUTRAL';
  fundamental_context: 'SUPPORTIVE' | 'CONTRADICTORY' | 'NEUTRAL';
  news_context: 'SUPPORTIVE' | 'CONTRADICTORY' | 'NEUTRAL';
  sentiment_context: 'SUPPORTIVE' | 'CONTRADICTORY' | 'NEUTRAL';
  cross_asset_context: 'SUPPORTIVE' | 'CONTRADICTORY' | 'NEUTRAL';
  supporting_evidence: SourcedEvidence[];
  contradiction_analysis: ContradictionAnalysis;
  key_catalysts: string[];
  bull_case_summary: string;
  bear_case_summary: string;
  uncertainty_level: 'LOW' | 'MODERATE' | 'HIGH';
  research_assessment:
    | 'STRONGLY_SUPPORTIVE'
    | 'MODERATELY_SUPPORTIVE'
    | 'MIXED'
    | 'MODERATELY_ADVERSE'
    | 'STRONGLY_ADVERSE'
    | 'INSUFFICIENT_EVIDENCE';
  ai_impact: 'STRENGTHEN' | 'NO_CHANGE' | 'WEAKEN' | 'BLOCK';
  impact_rationale: string[];
  model_version: string;
}

export interface ExpectedMoveProjection {
  underlying: UnderlyingSymbol;
  spot: number;
  direction: DirectionalBias;
  horizon: TradingHorizon;
  expected_duration_hours: number;
  expected_move_points: number;
  expected_target_price: number;
  expected_velocity_pts_per_hour: number;
  iv_implied_1sigma_move: number;
  atr_excursion_points: number;
  hourly_theta_decay: number;
  is_fast_enough_for_option: boolean;
  forecast_rationale: string[];
  conservative_target_t1: number;
  structural_target_t2: number;
  extended_target_t3: number;
}

export interface GreeksData {
  delta: number;
  gamma: number;
  theta_day: number;
  theta_hour: number;
  vega: number;
  rho: number;
  theoretical_price: number;
  intrinsic_value: number;
  time_value: number;
}

export interface PathScenarioOutcome {
  scenario_name: string;
  exit_spot: number;
  elapsed_hours: number;
  gross_option_premium: number;
  gross_pnl_total: number;
  theta_drag_total: number;
  vega_drag_total: number;
  statutory_taxes_total: number;
  net_pnl_total: number;
  net_return_pct: number;
  outcome_verdict: string;
}

export interface PathSimulationReport {
  fast_target: PathScenarioOutcome;
  slow_target: PathScenarioOutcome;
  sideways: PathScenarioOutcome;
  adverse_stop: PathScenarioOutcome;
  iv_crush_target: PathScenarioOutcome;
}

export interface ContractCandidate {
  strike: number;
  strike_type: StrikeCategory;
  broker_symbol: string;
  greeks: GreeksData;
  composite_score: number;
}

export interface ContractSelectionReport {
  underlying: UnderlyingSymbol;
  spot_price: number;
  direction: string;
  selected_strike: number;
  selected_strike_type: StrikeCategory;
  selection_score: number;
  selected_contract: {
    broker_symbol: string;
    strike: number;
    option_type: OptionType;
    current_iv: number;
  };
  selected_greeks: GreeksData;
  path_simulation: PathSimulationReport;
  selection_rationale: string[];
  all_candidates_evaluated: ContractCandidate[];
}

export interface PortfolioGreeksSummary {
  total_delta: number;
  total_gamma: number;
  total_theta_day: number;
  total_vega: number;
  total_open_positions: number;
  by_horizon: Record<string, { delta: number; theta: number }>;
  by_underlying: Record<string, { delta: number; theta: number }>;
}
