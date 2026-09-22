import { ApiCore, API_BASE, type RequestOptions } from './client';

const defaultCore = new ApiCore(API_BASE);

async function request<T>(path: string, options?: RequestOptions): Promise<T> {
  return defaultCore.request<T>(path, options);
}

export interface StrategyMatrixRequest {
  symbol?: string;
  timeframe?: string;
  trend_aligned?: boolean;
  session_filter?: boolean;
  k_tp?: number;
  k_sl?: number;
  t_max_bars?: number;
  stress_multiplier?: number;
}

export interface StrategyMatrixRow {
  strategy_key: string;
  strategy_name?: string;
  total_trades: number;
  win_rate: number;
  gross_expectancy_pct: number;
  net_expectancy_pct: number;
  profit_factor: number;
  max_drawdown_pct: number;
  annualized_sharpe?: number;
  deflated_sharpe_ratio?: number;
  gate_g0_verdict: 'PASSED' | 'FAILED' | 'INCONCLUSIVE' | 'NOT RUN';
  verdict_reasons?: string[];
}

export interface StrategyProvenance {
  source_symbol?: string;
  source_timeframe?: string;
  source_bars?: number;
  analysis_timeframe?: string;
  analysis_bars?: number;
  date_start?: string | null;
  date_end?: string | null;
  data_quality_score?: number;
  source_dataset?: string;
  cost_model?: string;
  execution_assumptions?: string;
}

export interface StrategyMatrixData {
  data?: {
    provenance?: StrategyProvenance;
    matrix?: StrategyMatrixRow[];
    rows?: StrategyMatrixRow[];
  };
  provenance?: StrategyProvenance;
  matrix?: StrategyMatrixRow[];
  rows?: StrategyMatrixRow[];
}

export async function runStrategyMatrix(params: StrategyMatrixRequest): Promise<StrategyMatrixData> {
  return request<StrategyMatrixData>('/api/v1/quant/strategy-matrix', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

export interface QuantDataset {
  symbol: string;
  timeframe: string;
  row_count: number;
  start_time: string | null;
  end_time: string | null;
  data_quality_score: number;
  checksum_sha256: string | null;
}

export interface G0Metrics {
  total_candidates: number;
  total_trades: number;
  win_rate: number;
  profit_factor: number;
  net_expectancy_pct: number;
  gross_expectancy_pct: number;
  cost_drag_pct: number;
  max_drawdown_pct: number;
  annualized_sharpe: number;
  deflated_sharpe_ratio: number;
  cost_survival_max_multiplier: number;
  gate_g0_verdict: 'PASSED' | 'FAILED' | 'INCONCLUSIVE';
  verdict_reasons: string[];
}

export interface G0Trade {
  entry_time: string;
  exit_time: string;
  strategy_id: string;
  direction: number;
  gross_pnl_pct: number;
  net_pnl_pct: number;
  total_cost_pct: number;
  exit_reason: string;
  bars_held: number;
}

export interface G0Result {
  metrics: G0Metrics;
  sample_trades: G0Trade[];
}

export interface ArmMetrics {
  arm_name: string;
  total_trades: number;
  win_rate: number;
  net_expectancy_pct: number;
  gross_expectancy_pct: number;
  cost_drag_pct: number;
  profit_factor: number;
  max_drawdown_pct: number;
  deflated_sharpe_ratio: number;
}

export interface G1Report {
  timestamp: string;
  n_folds: number;
  total_candidates: number;
  arms: Record<string, ArmMetrics>;
  model_correlation: number;
  mean_disagreement: number;
  disagreement_rejections: number;
  disagreement_rejection_pct: number;
  gate_g1_verdict: 'PASSED' | 'FAILED' | 'INCONCLUSIVE';
  verdict_reasons: string[];
}

export interface G2StressPoint {
  stress_multiplier: number;
  total_trades: number;
  net_expectancy_pct: number;
  profit_factor: number;
  max_drawdown_pct: number;
  survives: boolean;
}

export interface G2SensitivityPoint {
  k_tp: number;
  k_sl: number;
  total_trades: number;
  net_expectancy_pct: number;
  positive: boolean;
}

export interface G2Report {
  timestamp: string;
  strategy_key: string;
  total_trades: number;
  base_net_expectancy_pct: number;
  base_profit_factor: number;
  base_max_drawdown_pct: number;
  deflated_sharpe_ratio: number;
  cost_survival_max_multiplier: number;
  stress_curve: G2StressPoint[];
  sensitivity: G2SensitivityPoint[];
  sensitivity_pass_count: number;
  sensitivity_total: number;
  gate_g2_verdict: 'PASSED' | 'FAILED' | 'INCONCLUSIVE';
  verdict_reasons: string[];
}

export interface MatrixExportResult {
  provenance: StrategyProvenance;
  csv: string;
  filename: string;
}

export interface G0TradesExportResult {
  metrics: G0Metrics;
  trade_count: number;
  csv: string;
  filename: string;
}

export interface AnalogueNeighbor {
  timestamp: string;
  distance: number;
  similarity: number;
  direction: number;
  gross_return: number;
  net_return: number;
  exit_reason: string;
}

export interface AnalogueQueryResult {
  query_time: string;
  query_direction: number;
  analogue_context: {
    total_matches: number;
    mean_distance: number;
    analogue_win_rate: number;
    analogue_mean_return: number;
    analogue_dispersion: number;
    regime_similarity_score: number;
    has_historical_support: boolean;
    neighbor_count: number;
  };
  top_neighbors: AnalogueNeighbor[];
}

export interface OptionsSimResult {
  symbol: string;
  strike: number;
  option_type: 'CE' | 'PE';
  spot_entry: number;
  spot_exit: number;
  premium_entry: number;
  premium_exit: number;
  options_gross_pnl_pts: number;
  options_gross_roi_pct: number;
  total_statutory_cost_rupees: number;
  net_pnl_rupees: number;
  options_net_roi_pct: number;
  delta_at_entry: number;
  theta_per_day: number;
  bars_held: number;
}

export interface OptionsSpreadSimulationRequest {
  symbol?: string;
  direction?: 'LONG' | 'SHORT';
  spot_entry?: number;
  spot_exit?: number;
  holding_bars?: number;
  bar_minutes?: number;
  iv?: number;
  dte_entry?: number;
  strike_width?: number;
  lot_size?: number;
  contracts?: number;
  stress_multiplier?: number;
}

export interface OptionsSpreadSimulationResult {
  spread_name: string;
  symbol: string;
  direction: 'LONG' | 'SHORT';
  strike_width: number;
  net_entry: number;
  net_exit: number;
  gross_pnl_pts: number;
  gross_roi_pct: number;
  net_pnl_rupees: number;
  net_roi_pct: number;
  theta_decay_reduction_pct: number;
  net_greeks: {
    net_delta: number;
    net_theta_per_day: number;
    net_gamma: number;
    net_vega: number;
  };
  costs: {
    brokerage: number;
    stt: number;
    exchange_fees: number;
    gst: number;
    total_cost: number;
  };
  legs: {
    long_leg: {
      option_type: string;
      strike: number;
      premium_entry: number;
      premium_exit: number;
    };
    short_leg: {
      option_type: string;
      strike: number;
      premium_entry: number;
      premium_exit: number;
    };
  };
}

export interface S6TrackMetrics {
  instrument: string;
  track: string;
  variant: string;
  compression_episodes: number;
  raw_breakouts: number;
  failures: number;
  total_candidates: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  gross_expectancy_R: number;
  net_expectancy_R: number;
  profit_factor: number;
  max_drawdown_R: number;
  average_MFE_R: number;
  average_MAE_R: number;
  cost_drag_R: number;
  slippage_drag_R: number;
  compression_to_breakout_rate: number;
  breakout_to_trade_rate: number;
  breakout_to_failure_rate: number;
  gate_g0_verdict?: 'PASSED' | 'FAILED' | 'INCONCLUSIVE';
  verdict_reasons?: string[];
  run_dir?: string;
  sample_trades?: Array<Record<string, unknown>>;
}

export interface S6BatteryResult {
  provenance: {
    instrument: string;
    source_bars: number;
    start_time?: string | null;
    end_time?: string | null;
    spec_version: string;
    status: string;
    promotion: string;
  };
  matrix: Record<string, S6TrackMetrics>;
}

export interface S6Trial {
  trial_id: string;
  strategy_version: string;
  variant: string;
  instrument: string;
  track: string;
  parameter_hash: string;
  dataset_hash: string;
  registered_at: string;
  metrics?: Record<string, unknown> | null;
}

export interface S6TrialsResponse {
  trial_count: number;
  trials: S6Trial[];
}

export function createQuantApi(core: ApiCore) {
  return {
    async listDatasets(): Promise<{ data: QuantDataset[] }> {
      return core.request<{ data: QuantDataset[] }>('/api/v1/quant/datasets');
    },

    async runG0Baseline(params: {
      symbol?: string;
      timeframe?: string;
      strategy_key?: string;
      trend_aligned?: boolean;
      session_filter?: boolean;
      k_tp?: number;
      k_sl?: number;
      t_max_bars?: number;
      stress_multiplier?: number;
    }): Promise<{ data: G0Result }> {
      return core.request<{ data: G0Result }>('/api/v1/quant/g0-baseline', {
        method: 'POST',
        body: JSON.stringify(params),
      });
    },

    async runG1Ablation(params: {
      symbol?: string;
      timeframe?: string;
      strategy_key?: string;
      n_folds?: number;
      confidence_threshold?: number;
      max_disagreement?: number;
      k_tp?: number;
      k_sl?: number;
    }): Promise<{ data: G1Report }> {
      return core.request<{ data: G1Report }>('/api/v1/quant/g1-ablation', {
        method: 'POST',
        body: JSON.stringify(params),
      });
    },

    async runG2Robustness(params: {
      symbol?: string;
      timeframe?: string;
      strategy_key?: string;
      k_tp?: number;
      k_sl?: number;
      t_max_bars?: number;
      trend_aligned?: boolean;
      session_filter?: boolean;
    }): Promise<{ data: G2Report }> {
      return core.request<{ data: G2Report }>('/api/v1/quant/g2-robustness', {
        method: 'POST',
        body: JSON.stringify(params),
      });
    },

    async exportStrategyMatrix(params: StrategyMatrixRequest): Promise<{ data: MatrixExportResult }> {
      return core.request<{ data: MatrixExportResult }>('/api/v1/quant/strategy-matrix-export', {
        method: 'POST',
        body: JSON.stringify(params),
      });
    },

    async exportG0Trades(params: {
      symbol?: string;
      timeframe?: string;
      strategy_key?: string;
      trend_aligned?: boolean;
      session_filter?: boolean;
      k_tp?: number;
      k_sl?: number;
      t_max_bars?: number;
      stress_multiplier?: number;
    }): Promise<{ data: G0TradesExportResult }> {
      return core.request<{ data: G0TradesExportResult }>('/api/v1/quant/g0-trades-export', {
        method: 'POST',
        body: JSON.stringify(params),
      });
    },

    async queryHistoricalAnalogues(params: {
      symbol?: string;
      timeframe?: string;
      bar_index?: number;
      direction?: number;
      k_neighbors?: number;
    }): Promise<{ data: AnalogueQueryResult }> {
      return core.request<{ data: AnalogueQueryResult }>('/api/v1/quant/analogues', {
        method: 'POST',
        body: JSON.stringify(params),
      });
    },

    async simulateOptionsTrade(params: {
      symbol?: string;
      direction?: number;
      spot_entry?: number;
      spot_exit?: number;
      bars_held?: number;
      days_to_expiry?: number;
      custom_iv?: number;
      stress_multiplier?: number;
    }): Promise<{ data: OptionsSimResult }> {
      return core.request<{ data: OptionsSimResult }>('/api/v1/quant/options-simulate', {
        method: 'POST',
        body: JSON.stringify(params),
      });
    },

    async simulateOptionsSpread(params: OptionsSpreadSimulationRequest): Promise<{ data: OptionsSpreadSimulationResult }> {
      return core.request<{ data: OptionsSpreadSimulationResult }>('/api/v1/quant/options-spread-simulate', {
        method: 'POST',
        body: JSON.stringify(params),
      });
    },

    async runStrategyMatrix(params: StrategyMatrixRequest): Promise<StrategyMatrixData> {
      return core.request<StrategyMatrixData>('/api/v1/quant/strategy-matrix', {
        method: 'POST',
        body: JSON.stringify(params),
      });
    },

    async getS6Trials(): Promise<{ data: S6TrialsResponse }> {
      return core.request<{ data: S6TrialsResponse }>('/api/v1/quant/s6/trials');
    },

    async runS6Battery(params?: {
      instrument?: string;
      track?: string;
      mode?: string;
    }): Promise<{ data: S6BatteryResult }> {
      return core.request<{ data: S6BatteryResult }>('/api/v1/quant/s6/run', {
        method: 'POST',
        body: JSON.stringify(params || {}),
      });
    },
  };
}

export type QuantApi = ReturnType<typeof createQuantApi>;

export const quantApi = {
  ...createQuantApi(defaultCore),
  runStrategyMatrix,
};


