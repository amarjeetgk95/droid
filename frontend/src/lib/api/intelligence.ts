import { isApiErrorStatus, type ApiCore } from './client';
import type { HourForecast, PortfolioGreeksSummary } from '@/lib/types';

/**
 * 1H forecast v2 contract (P0): v1 keys plus optional v2 honesty fields
 * (status, probabilities, settleable, versions, limitations, ...).
 * All v2 keys are optional so v1 responses without new keys still render.
 */
export type HourForecastV2 = HourForecast;
export type TacticalHorizonBias = HourForecast;

export function createIntelligenceApi(core: ApiCore) {
  return {
    async calculateGreeks(params: { spot: number; strike: number; dte_days: number; volatility: number; option_type: 'CE' | 'PE' }) {
    return core.request<any>('/api/v1/options-intelligence/greeks', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },

    async calculateResearchIndicator(id: string, params: { instrument: string; timeframe: string; parameters?: any; candles?: any[] }) {
    return core.request<any>(`/api/v1/research/indicators/${id}/calculate`, {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },

    async getTacticalBias(instrument: string, horizon: string = '1h', record = true, includeExplain = true): Promise<HourForecastV2> {
    try {
      return await core.request<HourForecastV2>(
        `/api/v1/research/tactical-bias/${encodeURIComponent(horizon)}?instrument=${encodeURIComponent(instrument)}&record=${record ? 'true' : 'false'}&include_explain=${includeExplain ? 'true' : 'false'}`,
      );
    } catch (err) {
      // Fall back to the sibling route ONLY when the route itself is missing on
      // this backend build (404/405). Any other failure is real: re-issuing the
      // same computation through /forecast would double the provider work
      // exactly when the broker (or the model) is already struggling, and it
      // turns a fast error into a second full forecast round-trip.
      if (!isApiErrorStatus(err, 404, 405)) throw err;
      return this.getForecast(instrument, horizon, record, includeExplain);
    }
  },

    async getForecast(instrument: string, horizon: string = '1h', record = true, includeExplain = true): Promise<HourForecastV2> {
    return core.request<HourForecastV2>(
      `/api/v1/research/forecast/${encodeURIComponent(horizon)}?instrument=${encodeURIComponent(instrument)}&record=${record ? 'true' : 'false'}&include_explain=${includeExplain ? 'true' : 'false'}`,
    );
  },

    /**
     * Consolidated portfolio Greeks ledger across horizons. The endpoint
     * returns `PortfolioGreeksSummary` directly (no envelope); the optional
     * `data?: never` field is declared only so the drawer's defensive
     * `res.data ?? res` unwrap keeps typechecking against the real contract.
     */
    async getPortfolioGreeksSummary() {
    return core.request<PortfolioGreeksSummary & { data?: never }>(
      '/api/v1/options-intelligence/portfolio-greeks/summary',
    );
  },

    async getResearchIndicators(category?: string, lifecycle?: string) {
    const params = new URLSearchParams();
    if (category) params.set('category', category);
    if (lifecycle) params.set('lifecycle', lifecycle);
    const qs = params.toString() ? `?${params.toString()}` : '';
    return core.request<any[]>(`/api/v1/research/indicators${qs}`);
    },

    async getResearchIndicator(id: string) {
    return core.request<any>(`/api/v1/research/indicators/${encodeURIComponent(id)}`);
    },

    async getResearchChartState(instrument: string = 'NIFTY 50', timeframe: string = '5m') {
    return core.request<any>(
      `/api/v1/research/chart/state?instrument=${encodeURIComponent(instrument)}&timeframe=${encodeURIComponent(timeframe)}`,
    );
    },

    async getResearchChartFeatures(instrument: string = 'NIFTY 50', timeframe: string = '5m') {
    return core.request<any>(
      `/api/v1/research/chart/features?instrument=${encodeURIComponent(instrument)}&timeframe=${encodeURIComponent(timeframe)}`,
    );
    },

    async getResearchOptionsContext(instrument: string = 'NIFTY 50') {
    return core.request<any>(`/api/v1/research/options-context?instrument=${encodeURIComponent(instrument)}`);
  },

    async getResearchPredictionOutcome(predictionId: string) {
    return core.request<any>(`/api/v1/research/predictions/${encodeURIComponent(predictionId)}/outcome`);
    },

    async getResearchPrediction(predictionId: string) {
    return core.request<any>(`/api/v1/research/predictions/${encodeURIComponent(predictionId)}`);
    },

    async createResearchPrediction(params: Record<string, unknown>) {
    return core.request<any>('/api/v1/research/predictions', {
      method: 'POST',
      body: JSON.stringify(params),
    });
    },

    async listResearchPredictions(params?: { indicator_id?: string; instrument?: string; limit?: number }) {
    const q = new URLSearchParams();
    if (params?.indicator_id) q.set('indicator_id', params.indicator_id);
    if (params?.instrument) q.set('instrument', params.instrument);
    if (params?.limit) q.set('limit', String(params.limit));
    const qs = q.toString() ? `?${q.toString()}` : '';
    return core.request<any[]>(`/api/v1/research/predictions${qs}`);
  },

    async measureResearchPrediction(predictionId: string, forwardCandles?: any[]) {
    return core.request<any>(`/api/v1/research/predictions/${encodeURIComponent(predictionId)}/measure`, {
      method: 'POST',
      body: JSON.stringify({ forward_candles: forwardCandles }),
    });
  },

    async projectExpectedMove(params: any) {
    return core.request<any>('/api/v1/options-intelligence/expected-move', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },

    async runResearchExperiment(params: { indicator_id: string; instrument: string; timeframe: string; horizon_candles?: number; stride?: number; parameters?: any; candles?: any[] }) {
    return core.request<any>('/api/v1/research/experiments/run', {
      method: 'POST',
      body: JSON.stringify(params),
    });
    },

    async listResearchSnapshots(instrument?: string, limit: number = 50) {
    const q = new URLSearchParams();
    if (instrument) q.set('instrument', instrument);
    q.set('limit', String(limit));
    return core.request<any[]>(`/api/v1/research/snapshots?${q.toString()}`);
    },

    async createResearchSnapshot(params: Record<string, unknown>) {
    return core.request<any>('/api/v1/research/snapshots', {
      method: 'POST',
      body: JSON.stringify(params),
    });
    },

    async listResearchAnnotations(instrument?: string) {
    const q = new URLSearchParams();
    if (instrument) q.set('instrument', instrument);
    const qs = q.toString() ? `?${q.toString()}` : '';
    return core.request<any[]>(`/api/v1/research/annotations${qs}`);
    },

    async createResearchAnnotation(params: Record<string, unknown>) {
    return core.request<any>('/api/v1/research/annotations', {
      method: 'POST',
      body: JSON.stringify(params),
    });
    },

    async selectOptimalContract(params: any) {
    return core.request<any>('/api/v1/options-intelligence/select-contract', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },

    async simulateOptionPath(params: any) {
    return core.request<any>('/api/v1/options-intelligence/simulate-path', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },

    async solveIV(params: { market_price: number; spot: number; strike: number; dte_days: number; option_type: 'CE' | 'PE' }) {
    return core.request<any>('/api/v1/options-intelligence/solve-iv', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },

    /**
     * AI financial research context (backend returns the report directly, no
     * envelope). Fail-open read: callers render an honest empty state when the
     * engine has nothing stored for this underlying/horizon/direction.
     */
    async getFinancialResearch(
      underlying: string,
      horizon: string = 'INTRADAY',
      direction: 'BULLISH' | 'BEARISH' = 'BULLISH',
    ) {
      const qs = new URLSearchParams({ horizon, direction }).toString();
      return core.request<any>(
        `/api/v1/options-intelligence/financial-research/${encodeURIComponent(underlying)}?${qs}`,
      );
    },

    /**
     * Synthesize fresh AI research. Heavy (model inference): callers gate it
     * behind a ConfirmDialog and surface the outcome via toast.
     */
    async synthesizeFinancialResearch(params: {
      underlying: string;
      horizon?: string;
      direction?: 'BULLISH' | 'BEARISH';
    }) {
      return core.request<any>('/api/v1/options-intelligence/financial-research/synthesize', {
        method: 'POST',
        body: JSON.stringify({
          underlying: params.underlying,
          horizon: params.horizon ?? 'INTRADAY',
          direction: params.direction ?? 'BULLISH',
        }),
      });
    },
  };
}

export type IntelligenceApi = ReturnType<typeof createIntelligenceApi>;
