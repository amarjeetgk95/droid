import type { ApiCore } from './client';

export function createOptionsApi(core: ApiCore) {
  return {
    async getInstitutionalFlow(symbol: string, expiry?: string) {
    const query = expiry ? `?expiry=${expiry}` : '';
    return core.request<{ data: import('../types').InstitutionalFlowResponse; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/options/${encodeURIComponent(symbol)}/institutional-flow${query}`);
  },

    async getMaxPain(symbol: string, expiry?: string) {
    const query = expiry ? `?expiry=${expiry}` : '';
    return core.request<{ data: import('../types').MaxPainResult; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/options/${encodeURIComponent(symbol)}/max-pain${query}`);
  },

    async getOptionChain(symbol: string, expiry?: string) {
    const query = expiry ? `?expiry=${expiry}` : '';
    return core.request<{ data: import('../types').OptionChainResponse; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/options/${encodeURIComponent(symbol)}/chain${query}`);
  },

    async getOptionsAnalytics(symbol: string, expiry?: string) {
    const query = expiry ? `?expiry=${expiry}` : '';
    return core.request<{ data: import('../types').OptionsAnalytics; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/options/${encodeURIComponent(symbol)}/analytics${query}`);
  },

    async getRegimeKeyLevels(symbol: string) {
    return core.request<{ data: import('../types').KeyLevelsModel; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/regime/${encodeURIComponent(symbol)}/pivots`);
  },

    async getRegimeOverview(symbol: string) {
    return core.request<{ data: import('../types').MarketRegimeOverview; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/regime/${encodeURIComponent(symbol)}/overview`);
  },

    async getRegimeTechnicalIndicators(symbol: string) {
    return core.request<{ data: import('../types').TechnicalIndicators; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/regime/${encodeURIComponent(symbol)}/indicators`);
  },

    async getVixRegime() {
    return core.request<{ data: import('../types').VixRegimeInfo; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/regime/vix-status');
  },
  };
}

export type OptionsApi = ReturnType<typeof createOptionsApi>;
