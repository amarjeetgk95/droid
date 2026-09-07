import type { ApiCore } from './client';

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
