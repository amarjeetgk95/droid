import type { ApiCore } from './client';

export interface GreeksResult {
  theoretical_price: number;
  delta: number;
  gamma: number;
  theta_day: number;
  theta_hour: number;
  theta_pct_day: number;
  vega: number;
  rho: number;
  iv: number;
  moneyness: number;
  is_itm: boolean;
  is_atm: boolean;
  is_otm: boolean;
  theta_trading_day?: number;
  charm_day?: number;
  charm_hour?: number;
  vanna?: number;
  dte_days?: number;
}

export interface ExpectedMoveProjection {
  underlying: string;
  horizon: string;
  direction: string;
  spot_price: number;
  expected_move_points: number;
  expected_move_pct: number;
  conservative_move_points: number;
  aggressive_move_points: number;
  iv_implied_1sigma_move: number;
  atr_excursion_points: number;
  expected_duration_hours: number;
  expected_velocity_pts_per_hour: number;
  velocity_atr_per_hour?: number;
  live_iv?: number | null;
  iv_source?: string;
  option_delta?: number | null;
  dte_days?: number | null;
  expiry_crush_haircut_applied?: boolean;
  is_fast_enough_for_option: boolean;
  velocity_assessment: string;
  calibration_confidence: number;
  forecast_rationale?: string[];
}

export interface PortfolioGreeksSummary {
  total_delta: number;
  total_gamma: number;
  total_theta_day: number;
  total_vega: number;
  gross_delta: number;
  gross_gamma: number;
  gross_theta_day: number;
  gross_vega: number;
  net_exposure_by_underlying: Record<string, number>;
  gross_exposure_by_underlying: Record<string, number>;
  positions_by_horizon: Record<string, number>;
  expiry_concentrations: Record<string, number>;
  total_open_positions: number;
}

export interface FinancialResearchReport {
  research_id: string;
  underlying: string;
  proposed_direction: 'BULLISH' | 'BEARISH';
  horizon: 'SCALP' | 'INTRADAY' | 'SWING' | 'POSITIONAL';
  created_at: string;
  research_status: 'COMPLETE' | 'PARTIAL' | 'FALLBACK_TIMEOUT';
  market_context: string;
  macro_context: string;
  fundamental_context: string;
  news_context: string;
  sentiment_context: string;
  cross_asset_context: string;
  supporting_evidence: Array<Record<string, unknown>>;
  contradiction_analysis: Record<string, unknown>;
  key_catalysts: string[];
  bull_case_summary: string;
  bear_case_summary: string;
  uncertainty_level: 'LOW' | 'MODERATE' | 'HIGH' | 'EXTREME';
  research_assessment: string;
  ai_impact: 'STRENGTHEN' | 'NO_CHANGE' | 'WEAKEN' | 'BLOCK';
  impact_rationale: string[];
  model_version: string;
}

export function createOptionsIntelApi(core: ApiCore) {
  void core;
  return {};
}

export type OptionsIntelApi = ReturnType<typeof createOptionsIntelApi>;
