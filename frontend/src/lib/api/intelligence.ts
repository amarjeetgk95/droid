import { isApiErrorStatus, type ApiCore } from './client';
import type { HourForecast } from '@/components/research/ForecastCard';

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

    async createResearchAnnotation(annotation: any) {
    return core.request<any>('/api/v1/research/annotations', {
      method: 'POST',
      body: JSON.stringify(annotation),
    });
  },

    async createResearchSnapshot(snapshot: any) {
    return core.request<any>('/api/v1/research/snapshots', {
      method: 'POST',
      body: JSON.stringify(snapshot),
    });
  },

    async getFinancialResearch(underlying: string, horizon = 'INTRADAY', direction = 'BULLISH') {
    return core.request<any>(`/api/v1/options-intelligence/financial-research/${encodeURIComponent(underlying)}?horizon=${encodeURIComponent(horizon)}&direction=${encodeURIComponent(direction)}`);
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

    /** Explain bundle only (no prediction recorded). The bundle is what WhyPanel
     *  renders, so the polling call keeps `include_explain=true` (the default);
     *  pass `includeExplain=false` to `getForecast`/`getTacticalBias` for lighter
     *  polls and use this to fetch it on demand. */
    async getForecastExplain(instrument: string, horizon: string = '1h'): Promise<HourForecastV2> {
    return core.request<HourForecastV2>(
      `/api/v1/research/forecast/${encodeURIComponent(horizon)}?instrument=${encodeURIComponent(instrument)}&record=false&include_explain=true`,
    );
  },

    async getHourForecast(instrument: string, record = true): Promise<HourForecastV2> {
    return core.request<HourForecastV2>(`/api/v1/research/forecast/1h?instrument=${encodeURIComponent(instrument)}&record=${record ? 'true' : 'false'}`);
  },

    async getPortfolioGreeksSummary() {
    return core.request<any>('/api/v1/options-intelligence/portfolio-greeks/summary');
  },

    async getResearchChartState(instrument: string = 'NIFTY 50', timeframe: string = '5m') {
    return core.request<any>(`/api/v1/research/chart/state?instrument=${encodeURIComponent(instrument)}&timeframe=${encodeURIComponent(timeframe)}`);
  },

    async getResearchFeatures(instrument: string = 'NIFTY 50', timeframe: string = '5m') {
    return core.request<any>(`/api/v1/research/chart/features?instrument=${encodeURIComponent(instrument)}&timeframe=${encodeURIComponent(timeframe)}`);
  },

    async getResearchIndicator(id: string) {
    return core.request<any>(`/api/v1/research/indicators/${id}`);
  },

    async getResearchIndicators(category?: string, lifecycle?: string) {
    const params = new URLSearchParams();
    if (category) params.set('category', category);
    if (lifecycle) params.set('lifecycle', lifecycle);
    const qs = params.toString() ? `?${params.toString()}` : '';
    return core.request<any[]>(`/api/v1/research/indicators${qs}`);
  },

    async getResearchOptionsContext(instrument: string = 'NIFTY 50') {
    return core.request<any>(`/api/v1/research/options-context?instrument=${encodeURIComponent(instrument)}`);
  },

    async getResearchPredictionOutcome(predictionId: string) {
    return core.request<any>(`/api/v1/research/predictions/${encodeURIComponent(predictionId)}/outcome`);
  },

    async listResearchAnnotations(instrument?: string) {
    const qs = instrument ? `?instrument=${encodeURIComponent(instrument)}` : '';
    return core.request<any[]>(`/api/v1/research/annotations${qs}`);
  },

    async listResearchPredictions(params?: { indicator_id?: string; instrument?: string; limit?: number }) {
    const q = new URLSearchParams();
    if (params?.indicator_id) q.set('indicator_id', params.indicator_id);
    if (params?.instrument) q.set('instrument', params.instrument);
    if (params?.limit) q.set('limit', String(params.limit));
    const qs = q.toString() ? `?${q.toString()}` : '';
    return core.request<any[]>(`/api/v1/research/predictions${qs}`);
  },

    async listResearchSnapshots(instrument?: string) {
    const qs = instrument ? `?instrument=${encodeURIComponent(instrument)}` : '';
    return core.request<any[]>(`/api/v1/research/snapshots${qs}`);
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

    async recordResearchPrediction(prediction: any) {
    return core.request<any>('/api/v1/research/predictions', {
      method: 'POST',
      body: JSON.stringify(prediction),
    });
  },

    async runResearchExperiment(params: { indicator_id: string; instrument: string; timeframe: string; horizon_candles?: number; stride?: number; parameters?: any; candles?: any[] }) {
    return core.request<any>('/api/v1/research/experiments/run', {
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

    async synthesizeFinancialResearch(params: { underlying: string; horizon?: string; direction?: string }) {
    return core.request<any>('/api/v1/options-intelligence/financial-research/synthesize', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },
  };
}

export type IntelligenceApi = ReturnType<typeof createIntelligenceApi>;
