import type { ApiCore } from './client';
import { DEFAULT_STALE_AFTER_MS } from '@/lib/feedState';

export interface VortexSessionInfo {
  phase: string;
  is_trading_allowed: boolean;
  is_forced_square_off: boolean;
  session_progress_pct: number;
  minutes_to_market_close: number;
}

export interface VortexMLHealth {
  is_model_loaded: boolean;
  model_artifact_path: string | null;
  feature_count: number;
  calibration_enabled: boolean;
  acceptance_threshold: number;
}

export interface VortexStatus {
  strategy: string;
  version: string;
  status: string;
  primary_hypothesis: string;
  primary_timeframe: string;
  instruments_supported: string[];
  session: VortexSessionInfo;
  ml_validator: VortexMLHealth;
  config: Record<string, any>;
}

export interface CompressionState {
  score: number;
  zone: string;
  is_compressed: boolean;
  is_severe_compression: boolean;
  duration_bars: number;
  channel_range_pct: number;
}

export interface DirectionalPressureState {
  score: number;
  persistence: number;
  persistence_abs?: number;
  acceleration: number;
  acceleration_raw?: number;
  is_bullish: boolean;
  is_strong: boolean;
}

export interface TranslationRatioState {
  ratio: number;
  displacement: number;
  displacement_norm?: number;
  displacement_pts?: number;
  translation_state?: string;
  is_directional_acceptance: boolean;
  is_absorption_candidate: boolean;
  is_rejection_conflict: boolean;
}

export interface AbsorptionState {
  is_detected: boolean;
  absorption_score: number;
  side: number;
  exhaustion_volume_ratio: number;
}

export interface LiquidityVacuumState {
  is_detected: boolean;
  vacuum_score: number;
  thin_depth_side: string;
  displacement_velocity: number;
}

export interface SnapEnergyState {
  energy_score: number;
  is_snap_ready: boolean;
  energy_tier: string;
}

export interface MarketRegimeState {
  regime: string;
  confidence: number;
  adx: number;
  atr_14: number;
}

export interface StructuralLevelsState {
  nearest_support: number | null;
  nearest_resistance: number | null;
  support_distance_points: number;
  resistance_distance_points: number;
  relevance_score: number;
}

export interface FSMStateData {
  current_state: string;
  state_enter_bar_count: number;
  transition_history: Array<{
    from_state: string;
    to_state: string;
    timestamp_ms: number;
    reason: string;
  }>;
}

export interface VortexDataSource {
  type: 'parquet' | 'synthetic';
  instrument: string;
  path: string | null;
  is_simulated: boolean;
  note: string;
}

export interface ActiveCandidateSignal {
  strategy: string;
  underlying: string;
  direction: string;
  trigger_price: number;
  stop_loss: number;
  target_1: number;
  target_2: number;
  confidence: number;
  reason_codes: string[];
}

export interface VortexMicrostructureHUD {
  symbol: string;
  timestamp: string;
  latest_close: number;
  compression: CompressionState;
  directional_pressure: DirectionalPressureState;
  translation_ratio: TranslationRatioState;
  absorption: AbsorptionState;
  liquidity_vacuum: LiquidityVacuumState;
  snap_energy: SnapEnergyState;
  market_regime: MarketRegimeState;
  structural_levels: StructuralLevelsState;
  fsm_state: FSMStateData;
  active_candidate: ActiveCandidateSignal | null;
  data_source: VortexDataSource;
  /** Epoch-ms of the last candle in the payload (freshness evidence). */
  last_candle_timestamp_ms?: number | null;
  /** ISO form of `last_candle_timestamp_ms` when the backend supplies it. */
  last_candle_timestamp?: string | null;
  /** Backend clock at generation — lets the UI age data without trusting local time. */
  server_now_ms?: number | null;
}

/** Epoch-ms of the last candle, from either the ms or ISO field. Null = unknown. */
export function vortexLastCandleMs(
  hud: VortexMicrostructureHUD | null | undefined,
): number | null {
  if (!hud) return null;
  const ms = hud.last_candle_timestamp_ms;
  if (typeof ms === 'number' && Number.isFinite(ms) && ms > 0) {
    return ms < 1e12 ? Math.round(ms * 1000) : Math.round(ms);
  }
  const iso = hud.last_candle_timestamp;
  if (typeof iso === 'string' && iso.trim()) {
    const t = Date.parse(iso);
    if (Number.isFinite(t)) return t;
  }
  return null;
}

/** Backend server clock (epoch ms), or null when the payload omits it. */
export function vortexServerNowMs(
  hud: VortexMicrostructureHUD | null | undefined,
): number | null {
  const ms = hud?.server_now_ms;
  return typeof ms === 'number' && Number.isFinite(ms) && ms > 0 ? Math.round(ms) : null;
}

/**
 * Age of the HUD in ms. Uses the backend's server clock when present so local
 * clock skew cannot make stale candles look fresh; otherwise falls back to the
 * client clock. Null when the payload carries no candle timestamp.
 */
export function vortexDataAgeMs(
  hud: VortexMicrostructureHUD | null | undefined,
  clientNowMs: number = Date.now(),
): number | null {
  const last = vortexLastCandleMs(hud);
  if (last === null) return null;
  const serverNow = vortexServerNowMs(hud);
  const reference =
    serverNow ?? (Number.isFinite(clientNowMs) && clientNowMs > 0 ? clientNowMs : Date.now());
  return Math.max(0, reference - last);
}

/** Missing candle time is stale — unknown freshness is never "live". */
export function isVortexStale(
  hud: VortexMicrostructureHUD | null | undefined,
  clientNowMs: number = Date.now(),
  staleAfterMs: number = DEFAULT_STALE_AFTER_MS,
): boolean {
  const ageMs = vortexDataAgeMs(hud, clientNowMs);
  return ageMs === null || ageMs > staleAfterMs;
}

export interface VortexBacktestParams {
  symbol?: string;
  slippage_stress?: number;
  execution_lag?: number;
  initial_capital?: number;
  max_bars?: number;
}

export interface VortexTradeRecord {
  trade_id: number;
  entry_time_ms: number;
  exit_time_ms: number;
  direction: string;
  entry_price: number;
  exit_price: number;
  gross_pnl_rupees: number;
  net_pnl_rupees: number;
  friction_rupees: number;
  exit_reason: string;
  holding_bars: number;
  holding_minutes: number;
  confidence: number;
  reason_codes: string[];
}

export interface VortexBacktestResult {
  symbol: string;
  total_bars: number;
  metrics: {
    total_trades: number;
    winning_trades: number;
    losing_trades: number;
    scratch_trades: number;
    win_rate_pct: number;
    loss_rate_pct: number;
    gross_pnl_rupees: number;
    net_pnl_rupees: number;
    total_friction_rupees: number;
    cost_drag_pct: number;
    profit_factor: number;
    annualized_sharpe: number;
    annualized_sortino: number;
    calmar_ratio: number;
    max_drawdown_rupees: number;
    max_drawdown_pct: number;
    avg_holding_minutes: number;
    [key: string]: any;
  };
  exit_breakdown: Record<string, number>;
  equity_curve: number[];
  recent_trades: VortexTradeRecord[];
  data_source: VortexDataSource;
}

export interface AblationStageData {
  stage: string;
  config_name: string;
  description: string;
  trades: number;
  win_rate_pct: number;
  profit_factor: number;
  annualized_sharpe: number;
  max_dd_pct: number;
  delta_sharpe: number;
  delta_win_rate: number;
  marginal_sharpe: number;
}

export interface VortexAblationReport {
  symbol: string;
  bars_tested: number;
  primary_hypothesis_supported: boolean;
  primary_hypothesis_delta_sharpe: number;
  primary_hypothesis_delta_win_rate: number;
  stages: AblationStageData[];
  data_source: VortexDataSource;
}

export interface VortexExperimentSummary {
  id: string;
  filename: string;
  strategy: string;
  instrument: string;
  total_bars: number;
  generated_at: string;
  metrics: {
    total_trades: number;
    win_rate_pct: number;
    annualized_sharpe: number;
    profit_factor: number;
    net_pnl_rupees: number;
    max_drawdown_pct: number;
  };
}

export interface VortexExperimentDetail {
  id: string;
  structured: Record<string, any>;
  markdown: string;
}

export function createVortexApi(core: ApiCore) {
  return {
    async getVortexStatus(): Promise<VortexStatus> {
      const resp = await core.request<{ data: VortexStatus }>('/api/v1/strategies/vortex-snap/status');
      return resp.data;
    },

    async getVortexMicrostructure(symbol: string = 'SENSEX', bars: number = 120): Promise<VortexMicrostructureHUD> {
      const resp = await core.request<{ data: VortexMicrostructureHUD }>(
        `/api/v1/strategies/vortex-snap/microstructure/${encodeURIComponent(symbol)}?bars=${bars}`
      );
      return resp.data;
    },

    async runVortexBacktest(params: VortexBacktestParams = {}): Promise<VortexBacktestResult> {
      const resp = await core.request<{ data: VortexBacktestResult }>(
        '/api/v1/strategies/vortex-snap/backtest',
        {
          method: 'POST',
          body: JSON.stringify({
            symbol: params.symbol || 'SENSEX',
            slippage_stress: params.slippage_stress ?? 1.0,
            execution_lag: params.execution_lag ?? 1,
            initial_capital: params.initial_capital ?? 500000.0,
            max_bars: params.max_bars ?? 1500,
          }),
        }
      );
      return resp.data;
    },

    async getVortexAblation(symbol: string = 'SENSEX', sampleBars: number = 750): Promise<VortexAblationReport> {
      const resp = await core.request<{ data: VortexAblationReport }>(
        `/api/v1/strategies/vortex-snap/ablation?symbol=${encodeURIComponent(symbol)}&sample_bars=${sampleBars}`
      );
      return resp.data;
    },

    async getVortexExperiments(): Promise<VortexExperimentSummary[]> {
      const resp = await core.request<{ data: VortexExperimentSummary[] }>(
        '/api/v1/strategies/vortex-snap/experiments'
      );
      return resp.data;
    },

    async getVortexExperiment(id: string): Promise<VortexExperimentDetail> {
      const resp = await core.request<{ data: VortexExperimentDetail }>(
        `/api/v1/strategies/vortex-snap/experiments/${encodeURIComponent(id)}`
      );
      return resp.data;
    },
  };
}

export type VortexApi = ReturnType<typeof createVortexApi>;
