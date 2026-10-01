import type { ApiCore } from './client';

export interface TimeframeMetric {
  timeframe: string;
  bars: number;
  macd_line: number;
  signal_line: number;
  histogram: number;
  macd_trend: 'BULLISH' | 'BEARISH';
  fisher_line: number;
  fisher_trigger: number;
  fisher_zone: 'EXTREME_OVERSOLD' | 'OVERSOLD' | 'NEUTRAL' | 'OVERBOUGHT' | 'EXTREME_OVERBOUGHT';
  role: string;
}

export interface MacroTrend15M {
  timeframe: string;
  trend: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  macd_line: number;
  signal_line: number;
  histogram: number;
  histogram_expanding: boolean;
  bars_in_trend: number;
}

export interface PullbackOscillator5M {
  timeframe: string;
  fisher: number;
  trigger: number;
  zone: 'EXTREME_OVERSOLD' | 'OVERSOLD' | 'NEUTRAL' | 'OVERBOUGHT' | 'EXTREME_OVERBOUGHT';
  hook_direction: 'UP' | 'DOWN' | 'FLAT';
  is_bullish_crossover: boolean;
  is_bearish_crossover: boolean;
  prev_fisher: number;
  prev_trigger: number;
}

export interface RecommendedContract {
  symbol: string;
  strike: number;
  option_type: 'CE' | 'PE';
  delta: number;
  lot_size: number;
  estimated_premium: number;
  target_profit_inr: number;
  max_risk_inr: number;
}

export interface ConfluenceSetup {
  readiness: 'TRIGGERED' | 'ARMED' | 'IDLE';
  direction: 'LONG_CALL' | 'LONG_PUT' | 'NONE';
  bias_summary: string;
  entry_price: number;
  atr_14: number;
  target_1_half_atr: number;
  target_2_full_atr: number;
  stop_loss_full_atr: number;
  target_1_points: number;
  target_2_points: number;
  stop_loss_points: number;
  recommended_contract: RecommendedContract;
}

export interface EmpiricalBenchmarks {
  target_1_win_rate: string;
  target_1_rr: string;
  target_1_sample_pf: number;
  target_2_win_rate: string;
  target_2_rr: string;
  target_2_sample_pf: number;
  total_sample_trades: number;
  instrument_evaluated: string;
  pinned_indicators: {
    macd: string;
    fisher: string;
  };
  core_layman_rule: string;
}

export interface DivergenceRadar {
  has_active_divergence: boolean;
  divergence_type: 'REGULAR_BULLISH' | 'REGULAR_BEARISH' | 'HIDDEN_BULLISH' | 'HIDDEN_BEARISH' | 'NONE';
  indicator: string;
  bars_ago: number;
  price_delta: number;
  price_delta_atr: number;
  indicator_delta: number;
  classification: 'MACRO_STRUCTURAL' | 'FAST_MOMENTUM' | 'NONE';
}

export interface FisherMacdStatus {
  symbol: string;
  spot_price: number;
  timestamp_ms: number;
  time_ist: string;
  data_source: {
    type: string;
    source: string;
    bars: number;
    is_live: boolean;
  };
  macro_trend_15m: MacroTrend15M;
  pullback_oscillator_5m: PullbackOscillator5M;
  confluence_setup: ConfluenceSetup;
  divergence_radar?: DivergenceRadar;
  timeframe_matrix: TimeframeMetric[];
  empirical_benchmarks: EmpiricalBenchmarks;
}

export interface BarrierConfiguration {
  label: string;
  target_atr: number;
  stop_atr: number;
  win_rate_pct: number;
  profit_factor: number;
  sample_trades: number;
  net_atr_gain?: number;
  description: string;
}

export interface FisherMacdPerformance {
  strategy: string;
  specification: string;
  total_episodes_analyzed: number;
  instrument: string;
  primary_timeframe: string;
  barrier_configurations: BarrierConfiguration[];
  noise_analysis: {
    '1M_candle': string;
    '5M_candle': string;
    '15M_candle': string;
  };
}

export interface FisherMacdBacktestTrade {
  timestamp: string;
  direction: 'LONG_CALL' | 'LONG_PUT';
  entry_price: number;
  atr: number;
  target_price: number;
  stop_price: number;
  outcome: 'WIN' | 'LOSS';
  pnl_atr: number;
  pnl_points: number;
}

export interface DivergenceAnalysis {
  trades_with_divergence: number;
  trades_without_divergence: number;
  win_rate_with_divergence: number;
  win_rate_without_divergence: number;
  divergence_lift_pct: number;
  stability_flag: string;
}

export interface FrictionSensitivityRow {
  friction_haircut_atr: number;
  total_trades: number;
  net_wins: number;
  net_win_rate_pct: number;
  profit_factor: number;
  total_net_gain_atr: number;
  expected_value_atr: number;
  is_economically_viable: boolean;
}

export interface FisherMacdBacktestResult {
  symbol: string;
  bars_evaluated: number;
  target_atr: number;
  stop_atr: number;
  total_trades: number;
  wins: number;
  losses: number;
  win_rate_pct: number;
  profit_factor: number;
  net_atr_gain: number;
  expected_value_atr: number;
  divergence_analysis?: DivergenceAnalysis;
  friction_sensitivity?: FrictionSensitivityRow[];
  recent_trades: FisherMacdBacktestTrade[];
}

export interface FisherMacdBacktestParams {
  symbol?: string;
  target_atr?: number;
  stop_atr?: number;
  max_bars?: number;
}

export interface FisherMacdDispatchRequest {
  symbol: string;
  direction: string;
  contract_symbol: string;
  quantity: number;
  entry_price: number;
  target_price: number;
  stop_price: number;
  destination?: 'PAPER_PORTFOLIO' | 'ALERT_WEBHOOK';
}

export interface FisherMacdDispatchResult {
  dispatch_id: string;
  timestamp: string;
  status: string;
  symbol: string;
  direction: string;
  contract: string;
  order?: {
    order_id: string;
    status: string;
    fill_price?: number;
    quantity: number;
    rejection_reason?: string;
  };
  alert: {
    channel: string;
    severity: string;
    title: string;
    message: string;
    dispatched_at: string;
  };
}

export function createFisherMacdApi(core: ApiCore) {
  return {
    async getFisherMacdStatus(symbol: string = 'NIFTY'): Promise<FisherMacdStatus> {
      const resp = await core.request<{ data: FisherMacdStatus }>(
        `/api/v1/strategies/fisher-macd/status/${encodeURIComponent(symbol)}`
      );
      return resp.data;
    },

    async getFisherMacdPerformance(): Promise<FisherMacdPerformance> {
      const resp = await core.request<{ data: FisherMacdPerformance }>(
        '/api/v1/strategies/fisher-macd/performance'
      );
      return resp.data;
    },

    async runFisherMacdBacktest(params: FisherMacdBacktestParams = {}): Promise<FisherMacdBacktestResult> {
      const resp = await core.request<{ data: FisherMacdBacktestResult }>(
        '/api/v1/strategies/fisher-macd/backtest',
        {
          method: 'POST',
          body: JSON.stringify({
            symbol: params.symbol || 'NIFTY',
            target_atr: params.target_atr ?? 0.50,
            stop_atr: params.stop_atr ?? 1.00,
            max_bars: params.max_bars ?? 5000,
          }),
        }
      );
      return resp.data;
    },

    async dispatchFisherMacdSignal(req: FisherMacdDispatchRequest): Promise<FisherMacdDispatchResult> {
      const resp = await core.request<{ data: FisherMacdDispatchResult }>(
        '/api/v1/strategies/fisher-macd/dispatch',
        {
          method: 'POST',
          body: JSON.stringify(req),
        }
      );
      return resp.data;
    },
  };
}

export type FisherMacdApi = ReturnType<typeof createFisherMacdApi>;
