import type { ApiCore } from './client';

export function createMarketsApi(core: ApiCore) {
  return {
    async getIndexCards() {
    return core.request<{ data: import('../types').IndexCard[]; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/markets/cards');
  },

    async getMarketBreadth() {
    return core.request<{ data: import('../types').MarketBreadthData; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/markets/breadth');
  },

    async getMarketHealth() {
    return core.request<import('../types').MarketHealthStatus>('/api/v1/health/market-data');
  },

    async getMarketStatus() {
    return core.request<{ data: import('../types').MarketStatusResponse; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/markets/status');
  },

    async getQuote(symbol: string) {
    return core.request<{ data: import('../types').NormalizedQuote; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/markets/${encodeURIComponent(symbol)}/quote`);
  },

    async getSessionInfo(date?: string) {
    const query = date ? `?target_date=${date}` : '';
    return core.request<{ data: { is_trading_day: boolean; is_holiday: boolean; is_weekend: boolean; holiday_name: string | null; is_special_session: boolean; market_open: string | null; market_close: string | null }; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/calendar/session${query}`);
  },

    async testBrokerConnection(payload: { provider: string; credentials: Record<string, unknown> }) {
    return core.request<{
      data: {
        success: boolean;
        provider: string;
        latency_ms: number;
        token_valid: boolean;
        token_prefix?: string;
        quote?: { symbol: string; ltp: number; high?: number; low?: number; status?: string };
        raw_response?: unknown;
        error?: string | null;
      };
      error: string | null;
      meta: import('../types').ApiMeta;
    }>('/api/v1/tokens/test-connection', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },
  };
}

export type MarketsApi = ReturnType<typeof createMarketsApi>;
