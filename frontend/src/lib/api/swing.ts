import type { ApiCore } from './client';

export type SwingSetupDTO = {
  setup_id: string;
  symbol: string;
  sector: string;
  strategy: 'VCP_BREAKOUT' | 'TREND_PULLBACK_20EMA' | 'STAGE2_BREAKOUT';
  direction: 'LONG';
  score: {
    trend: number;
    structure: number;
    volume: number;
    relative_strength: number;
    sector: number;
    regime: number;
    risk_reward: number;
    liquidity: number;
    total: number;
    score_is_probability: boolean;
  };
  entry_zone_min: number;
  entry_zone_max: number;
  trigger_price: number;
  max_chase_price: number;
  stop_price: number;
  structural_stop: number;
  atr_floor: number;
  target_1: number;
  target_2: number;
  risk_per_share: number;
  risk_pct: number;
  risk_reward_t1: number;
  risk_reward_t2: number;
  expected_holding_days: number;
  daily_atr: number;
  market_regime: string;
  sector_state: string;
  technical_reasons: string[];
  risk_reasons: string[];
  invalidation_rules: string[];
  signal_state: 'WATCH' | 'READY' | 'TRIGGERED' | 'ENTERED' | 'BLOCKED';
  created_at_utc: number;
};

export type SwingPositionDTO = {
  position_id: string;
  setup_id: string;
  symbol: string;
  sector: string;
  strategy: string;
  entry_price: number;
  current_price: number;
  quantity: number;
  initial_stop: number;
  current_stop: number;
  trailing_method: string;
  target_1: number;
  target_2: number;
  days_held: number;
  unrealized_pnl: number;
  pnl_pct: number;
  r_multiple: number;
  status: 'OPEN' | 'PARTIALLY_CLOSED' | 'CLOSED';
  close_price?: number;
  closed_at_utc?: number;
  exit_reason?: string;
};

export type PortfolioRiskDTO = {
  total_equity: number;
  open_capital: number;
  open_risk_capital: number;
  portfolio_heat_pct: number;
  max_heat_pct: number;
  sector_allocations: Record<string, number>;
  open_positions_count: number;
  max_positions_count: number;
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
            sector: string;
            industry?: string;
            lot_size: number;
            beta: number;
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
      sector?: string;
      min_score?: number;
      state?: string;
    }) {
      const q = new URLSearchParams();
      if (params?.strategy) q.set('strategy', params.strategy);
      if (params?.sector) q.set('sector', params.sector);
      if (params?.min_score !== undefined) q.set('min_score', String(params.min_score));
      if (params?.state) q.set('state', params.state);
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
    }) {
      return core.request<
        Envelope<{
          scan_timestamp_utc: number;
          duration_seconds: number;
          stocks_scanned: number;
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
      fill_price: number;
      quantity?: number;
    }) {
      return core.request<Envelope<SwingPositionDTO>>('/api/v1/swing/positions/enter', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },

    async exitSwingPosition(payload: {
      position_id: string;
      exit_price: number;
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
          symbol: string;
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
