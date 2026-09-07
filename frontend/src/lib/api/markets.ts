import type { ApiCore } from './client';

export function createMarketsApi(core: ApiCore) {
  return {
    async checkTradingDay(date?: string) {
    const query = date ? `?target_date=${date}` : '';
    return core.request<{ data: { date: string; is_trading_day: boolean; holiday_name: string | null }; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/calendar/is-trading-day${query}`);
  },

    async getCandles(symbol: string, timeframe: string = '5m', limit?: number) {
    const qs = limit && limit > 0 ? `&limit=${Math.round(limit)}` : '';
    return core.request<{ data: import('../types').NormalizedCandle[]; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/markets/${encodeURIComponent(symbol)}/candles?timeframe=${timeframe}${qs}`);
  },

    async getContractExpiries(symbol: string) {
    return core.request<{ data: import('../types').ExpiryResolution; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/contracts/${encodeURIComponent(symbol)}/expiries`);
  },

    async getContractMaster(symbol: string) {
    return core.request<{ data: import('../types').ContractMaster; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/contracts/${encodeURIComponent(symbol)}/master`);
  },

    async getHolidays(year?: number) {
    const query = year ? `?year=${year}` : '';
    return core.request<{ data: Record<string, string>; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/calendar/holidays${query}`);
  },

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

    async getQuotes() {
    return core.request<{ data: import('../types').NormalizedQuote[]; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/markets/quotes');
  },

    async getSessionInfo(date?: string) {
    const query = date ? `?target_date=${date}` : '';
    return core.request<{ data: { is_trading_day: boolean; is_holiday: boolean; is_weekend: boolean; holiday_name: string | null; is_special_session: boolean; market_open: string | null; market_close: string | null }; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/calendar/session${query}`);
  },

    async getTokenStatus() {
    return core.request<{ data: Record<string, unknown>; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/tokens/status');
  },

    async refreshToken(payload?: Record<string, unknown>) {
    return core.request<{ data: { refreshed: boolean; provider: string; has_token: boolean }; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/tokens/refresh', {
      method: 'POST',
      body: payload ? JSON.stringify(payload) : undefined,
    });
  },

    async searchContracts(params?: { underlying?: string; contract_type?: string; expiry?: string; strike?: number }) {
    const query = new URLSearchParams();
    if (params?.underlying) query.set('underlying', params.underlying);
    if (params?.contract_type) query.set('contract_type', params.contract_type);
    if (params?.expiry) query.set('expiry', params.expiry);
    if (params?.strike) query.set('strike', params.strike.toString());
    return core.request<{ data: import('../types').ContractMaster[]; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/contracts/search?${query.toString()}`);
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
