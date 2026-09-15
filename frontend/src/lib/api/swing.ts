import type { ApiCore } from './client';

export type SwingSetupDTO = {
  setup_id: string;
  underlying: string; // "NIFTY", "BANKNIFTY", "SENSEX"
  direction: 'LONG_CALL' | 'LONG_PUT';
  option_type: 'CE' | 'PE';
  strategy:
    | 'TREND_BREAKOUT_CE'
    | 'TREND_BREAKOUT_PE'
    | 'PULLBACK_CE'
    | 'PULLBACK_PE'
    | 'STAGE2_CE'
    | 'STAGE2_PE'
    | 'IV_DIRECTIONAL'
    | string;

  // Option Contract Details
  horizon?: 'POSITIONAL' | 'INTRADAY';
  timeframe?: string;
  hard_exit_time?: string;
  strike: number;
  expiry_date: string;
  contract_symbol: string;
  lot_size: number;
  expected_holding_days: number;
  dte: number;
  vwap?: number;

  // Underlying Technical Context
  spot_price: number;
  spot_trigger: number;
  spot_stop: number;
  daily_atr: number;

  // Option Premium Execution Levels (₹ per unit)
  entry_premium: number;
  stop_premium: number;
  target_premium_1: number;
  target_premium_2: number;
  premium_risk_per_lot: number;

  // Greeks & Volatility Telemetry
  iv: number;
  iv_percentile: number;
  iv_regime: string;
  greeks: {
    delta?: number;
    gamma?: number;
    theta_day?: number;
    theta_hour?: number;
    vega?: number;
    [key: string]: any;
  };
  theta_drag_ratio: number;

  // Scoring & Validity (§6)
  score: {
    trend: number;
    structure: number;
    volume: number;
    expected_move: number;
    iv_favorability: number;
    greeks_quality: number;
    theta_efficiency: number;
    liquidity: number;
    regime: number;
    risk_reward: number;
    portfolio_fit: number;
    dte_adequacy: number;
    total: number;
    score_is_probability: boolean;
  };
  trade_validity: {
    underlying_valid: boolean;
    option_valid: boolean;
    portfolio_valid: boolean;
    execution_valid: boolean;
    overall_valid: boolean;
    rejection_reasons: string[];
  };
  strike_selection_rationale?: string[];
  strike_selection_score?: number;
  liquidity_score?: number;
  execution_score?: number;

  // Macro & Rationale
  market_regime: string;
  technical_reasons: string[];
  options_reasons: string[];
  risk_reasons: string[];
  invalidation_rules: string[];

  // Lifecycle
  signal_state:
    | 'WATCH'
    | 'READY'
    | 'TRIGGERED'
    | 'ENTERED'
    | 'PARTIAL_EXIT'
    | 'TRAILING'
    | 'EXITED'
    | 'INVALIDATED'
    | 'EXPIRED'
    | 'ABSTAINED'
    | 'BLOCKED'
    | 'THETA_WARNING'
    | 'EXPIRY_WARNING'
    | string;
  created_at_utc: number;
  valid_until_utc?: number;
};

export type SwingPositionDTO = {
  position_id: string;
  setup_id: string;
  underlying: string;
  option_type: 'CE' | 'PE';
  strike: number;
  expiry_date: string;
  contract_symbol: string;
  direction: 'LONG_CALL' | 'LONG_PUT';
  strategy: string;
  horizon?: 'POSITIONAL' | 'INTRADAY';
  timeframe?: string;
  hard_exit_time?: string;

  // Sizing & Premiums
  entry_premium: number;
  current_premium: number;
  num_lots: number;
  lot_size: number;

  // Dual-layer stops & targets
  initial_stop_premium: number;
  current_stop_premium: number;
  spot_stop: number;
  stop_method: 'INITIAL' | 'BREAK_EVEN' | 'TRAILING_PREMIUM' | 'TIME_DECAY' | string;
  target_1: number;
  target_2: number;

  // Spot & Greeks tracking
  spot_at_entry: number;
  current_spot: number;
  greeks_at_entry: Record<string, any>;
  iv_at_entry: number;
  days_held: number;
  dte_remaining: number;
  highest_premium: number;
  theta_cost_accumulated: number;

  // Performance
  unrealized_pnl: number;
  pnl_pct: number;
  r_multiple: number;
  status: 'OPEN' | 'PARTIALLY_CLOSED' | 'CLOSED';
  close_premium?: number;
  closed_at_utc?: number;
  exit_reason?: string;
};

export type PortfolioRiskDTO = {
  total_equity: number;
  total_premium_deployed: number;
  premium_at_risk: number;
  portfolio_heat_pct: number;
  max_heat_pct: number;
  net_delta: number;
  net_theta_day: number;
  net_vega: number;
  open_positions_count: number;
  max_positions_count: number;
  positions_by_underlying: Record<string, number>;
  max_positions_per_underlying: number;
  // Backward compat optional fields
  open_capital?: number;
  open_risk_capital?: number;
};

export type Envelope<T> = {
  data: T;
  error: string | null;
  meta: any;
};

export function createSwingApi(core: ApiCore) {
  return {
    async getSwingUniverse() {
      return core.request<
        Envelope<{
          total_count: number;
          sectors: string[];
          instruments: Array<{
            symbol: string;
            display_name: string;
            exchange: string;
            lot_size: number;
            strike_interval: number;
            tick_size: number;
          }>;
        }>
      >('/api/v1/swing/universe');
    },

    async getSwingRegime() {
      return core.request<
        Envelope<{
          regime: {
            regime: string;
            confidence: number;
            persistence_bars: number;
            benchmark_symbol: string;
            benchmark_price: number;
            benchmark_change_pct: number;
            ma_alignment_score: number;
            recent_drawdown_pct: number;
            iv_percentile: number;
            iv_regime: string;
            reasons: string[];
          } | null;
          sectors: Array<{
            sector: string;
            trend: string;
            relative_strength: number;
            return_20d_pct: number;
            leading_stocks: string[];
          }>;
          scan_timestamp_utc?: number;
        }>
      >('/api/v1/swing/regime');
    },

    async getSwingSetups(params?: {
      strategy?: string;
      underlying?: string;
      sector?: string;
      min_score?: number;
      state?: string;
      direction?: string;
      horizon?: string;
    }) {
      const q = new URLSearchParams();
      if (params?.strategy) q.set('strategy', params.strategy);
      if (params?.underlying) q.set('underlying', params.underlying);
      if (params?.sector) q.set('sector', params.sector);
      if (params?.min_score !== undefined) q.set('min_score', String(params.min_score));
      if (params?.state) q.set('state', params.state);
      if (params?.direction) q.set('direction', params.direction);
      if (params?.horizon && params.horizon !== 'ALL') q.set('horizon', params.horizon);
      const queryStr = q.toString() ? `?${q.toString()}` : '';
      return core.request<
        Envelope<{
          count: number;
          total_unfiltered: number;
          setups: SwingSetupDTO[];
        }>
      >(`/api/v1/swing/setups${queryStr}`);
    },

    async triggerSwingScan(payload?: {
      portfolio_equity?: number;
      force_refresh?: boolean;
      limit_symbols?: string[];
      horizon?: string;
    }) {
      return core.request<
        Envelope<{
          scan_timestamp_utc: number;
          duration_seconds: number;
          indices_scanned: number;
          regime: any;
          sectors: any[];
          setups: SwingSetupDTO[];
          open_positions: SwingPositionDTO[];
          closed_positions_count: number;
          portfolio_risk: PortfolioRiskDTO;
        }>
      >('/api/v1/swing/scan', {
        method: 'POST',
        body: JSON.stringify(payload || {}),
      });
    },

    async getSwingPositions() {
      return core.request<
        Envelope<{
          open_positions: SwingPositionDTO[];
          closed_positions: SwingPositionDTO[];
          portfolio_risk: PortfolioRiskDTO;
        }>
      >('/api/v1/swing/positions');
    },

    async enterSwingPosition(payload: {
      setup_id: string;
      fill_premium?: number;
      fill_price?: number;
      num_lots?: number;
      quantity?: number;
    }) {
      return core.request<Envelope<SwingPositionDTO>>('/api/v1/swing/positions/enter', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },

    async exitSwingPosition(payload: {
      position_id: string;
      exit_premium?: number;
      exit_price?: number;
      exit_reason?: string;
    }) {
      return core.request<Envelope<SwingPositionDTO>>('/api/v1/swing/positions/exit', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },

    async getSwingThesis(setupId: string) {
      return core.request<
        Envelope<{
          setup_id: string;
          contract: string;
          context: Record<string, any>;
          structured_prompt: string;
        }>
      >('/api/v1/swing/thesis', {
        method: 'POST',
        body: JSON.stringify({ setup_id: setupId }),
      });
    },
  };
}

export type SwingApi = ReturnType<typeof createSwingApi>;
