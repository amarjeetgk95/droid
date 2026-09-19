import type { ApiCore } from './client';

/**
 * Futures analytics DTOs (`GET /api/v1/futures/{symbol}/*`).
 * Truth-of-Wall: the broker feed is currently unwired server-side, so these
 * payloads carry `UNAVAILABLE` markers and null prices — consumers must render
 * honest empty states, never synthetic contracts or a fake basis.
 */
export interface FuturesTermContract {
  expiry?: string | null;
  price?: number | null;
  open_interest?: number | null;
  volume?: number | null;
  [key: string]: unknown;
}

export interface FuturesTermStructure {
  underlying: string;
  curve_state: string;
  contracts: FuturesTermContract[];
}

export interface FuturesBuildup {
  underlying: string;
  buildup_type: string;
  price_change_pct: number;
  oi_change_pct: number;
  interpretation: string;
}

export interface FuturesRollover {
  underlying: string;
  rollover_percent: number | null;
  rollover_pace: string;
  previous_month_rollover: number | null;
}

export interface FuturesOverviewData {
  underlying: string;
  spot_price: number | null;
  near_future_price: number | null;
  basis_pts: number | null;
  term_structure: FuturesTermStructure;
  buildup: FuturesBuildup;
  rollover: FuturesRollover;
}

type FuturesEnvelope<T> = {
  data: T;
  error: string | null;
  meta: import('../types').ApiMeta;
};

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

    async getFuturesOverview(symbol: string) {
    return core.request<FuturesEnvelope<FuturesOverviewData>>(`/api/v1/futures/${encodeURIComponent(symbol)}/overview`);
  },

    async getFuturesTermStructure(symbol: string) {
    return core.request<FuturesEnvelope<FuturesTermStructure>>(`/api/v1/futures/${encodeURIComponent(symbol)}/term-structure`);
  },

    async getFuturesBuildup(symbol: string) {
    return core.request<FuturesEnvelope<FuturesBuildup>>(`/api/v1/futures/${encodeURIComponent(symbol)}/buildup`);
  },

    async getFuturesRollover(symbol: string) {
    return core.request<FuturesEnvelope<FuturesRollover>>(`/api/v1/futures/${encodeURIComponent(symbol)}/rollover`);
  },
  };
}

export type OptionsApi = ReturnType<typeof createOptionsApi>;
