import type { ApiCore } from './client';

export function createSystemApi(core: ApiCore) {
  return {
    async calculatePricing(payload: any) {
    return core.request<any>('/api/v1/pipeline/pricing/calculate', { method: 'POST', body: JSON.stringify(payload) });
  },

    async captureMarketState(symbol: string, currentPrice: number, atr: number, regime: string = 'UNKNOWN') {
      const params = new URLSearchParams({
        symbol,
        current_price: String(currentPrice),
        atr: String(atr),
        regime,
      });
      return core.request<any>(`/api/v1/pipeline/state/capture?${params.toString()}`, { method: 'POST' });
    },

    async evaluateTrigger(symbol: string, triggerType: string, currentPrice: number, significance?: number) {
      const params = new URLSearchParams({
        symbol,
        trigger_type: triggerType,
        current_price: String(currentPrice),
      });
      if (significance !== undefined && significance !== null && Number.isFinite(significance)) {
        params.set('significance', String(significance));
      }
      return core.request<any>(`/api/v1/pipeline/trigger/evaluate?${params.toString()}`, { method: 'POST' });
    },

    async getDashboardSymbol(symbol: string) {
      return core.request<{ data: Record<string, unknown>; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/dashboard/${encodeURIComponent(symbol)}`);
    },

    async getDbHealth() {
      return core.request<{ status: string; connected: boolean; database?: string | null; user?: string | null; server?: string | null; counts?: Record<string, unknown>; error?: string; configured?: boolean }>('/api/v1/health/database');
    },

    async health() {
      return core.request<{ status: string; timestamp?: string }>('/health');
    },

    async checkStaleness(payload: any) {
    return core.request<any>('/api/v1/pipeline/staleness/check', { method: 'POST', body: JSON.stringify(payload) });
  },

    async clearCache() {
    return core.request<{ data: { cleared: boolean }; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/cache/clear', { method: 'POST' });
  },

    async createExecutionSignal(symbol: string, side: string, quantity: number) {
    return core.request<any>(`/api/v1/pipeline/execution/signal?symbol=${encodeURIComponent(symbol)}&side=${side}&quantity=${quantity}`, { method: 'POST' });
  },

    async getCacheStats() {
    return core.request<{ data: Record<string, unknown>; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/cache/stats');
  },

    async getCircuitBreakerStatus() {
    return core.request<{ data: Record<string, unknown>; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/circuit-breaker/status');
  },

    async getDashboardSummary() {
    return core.request<{
      data: {
        cards: any[];
        breadth: any;
        health: any;
        market_status: any;
        ml_prediction: any;
        fii_dii: any;
        regime_overview: any;
        options_analytics: any;
        errors: Record<string, string>;
        degraded: boolean;
        generated_at: string;
      };
      error: string | null;
      meta: import('../types').ApiMeta;
    }>('/api/v1/dashboard/summary');
  },

    async getPipelineStats() {
    return core.request<{ data: { timeseries_store: Record<string, unknown>; write_pipeline: Record<string, unknown> }; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/timeseries/pipeline-stats');
  },

    async healthLive() {
    return core.request<{ status: string }>('/health/live');
  },

    async healthReady() {
    return core.request<{ status: string }>('/health/ready');
  },

    async listExecutionOrders() {
    return core.request<any>('/api/v1/pipeline/execution/orders');
  },

    async resetCircuitBreaker() {
    return core.request<{ data: Record<string, unknown>; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/circuit-breaker/reset', { method: 'POST' });
  },

    async searchInstruments(q: string, asset_class?: string, fno_only?: boolean) {
    const params = new URLSearchParams({ q });
    if (asset_class) params.set('asset_class', asset_class);
    if (fno_only) params.set('fno_only', 'true');
    return core.request<{ data: { query: string; results: any[]; total: number }; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/instruments/search?${params.toString()}`);
  },

    async testDirectProvider(provider: string, payload: any) {
    return core.request<any>('/api/v1/ai/test', { method: 'POST', body: JSON.stringify({ provider, ...payload }) });
  },

    async transitionExecution(orderId: string, toState: string) {
    return core.request<any>(`/api/v1/pipeline/execution/${encodeURIComponent(orderId)}/transition?to_state=${toState}`, { method: 'POST' });
  },

    async tripCircuitBreaker() {
    return core.request<{ data: Record<string, unknown>; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/circuit-breaker/trip', { method: 'POST' });
  },

    async getSignalsSubsystemsHealth() {
    return core.request<{
      timestamp?: string;
      elements?: Record<string, boolean | string>;
      [key: string]: unknown;
    }>('/health/subsystems');
  },

    async getForecastHealth(limit: number = 30) {
    return core.request<{
      status: 'healthy' | 'degraded' | 'unknown';
      degraded: boolean;
      reasons: string[];
      notes?: string[];
      metrics: Record<string, any>;
      runtime: Record<string, any>;
      thresholds: Record<string, any>;
      window: number;
      timestamp: string;
    }>(`/api/v1/monitoring/forecast-health?limit=${limit}`);
  },

    async getForecastConfig() {
    return core.request<{
      status: string;
      bundle: Record<string, any>;
      error?: string;
      timestamp: string;
    }>('/api/v1/monitoring/forecast-config');
  },
  };
}

export type SystemApi = ReturnType<typeof createSystemApi>;
