import type { ApiCore } from './client';

export function createCryptoApi(core: ApiCore) {
  return {
    async deleteCryptoScalpSignal(signalId: string) {
    return core.request<{ status: string; signal_id: string }>(`/api/v1/crypto/scalp-signals/${signalId}`, {
      method: 'DELETE',
    });
  },

    async deleteCryptoScalpTrade(tradeId: string) {
    return core.request<{ status: string; trade_id: string }>(`/api/v1/crypto/scalp-signals/ledger/${tradeId}`, {
      method: 'DELETE',
    });
  },

    async getCryptoCandles(symbol: string, timeframe: string = '1h', limit: number = 100) {
    return core.request<{ data: import('../types').NormalizedCandle[]; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/crypto/${encodeURIComponent(symbol)}/candles?timeframe=${encodeURIComponent(timeframe)}&limit=${limit}`);
  },

    async getCryptoComparison() {
    return core.request<{ data: import('../types').CryptoPairComparison; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/crypto/comparison');
  },

    async getCryptoDerivatives(symbol: string) {
    return core.request<{ data: import('../types').CryptoDerivatives; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/crypto/${encodeURIComponent(symbol)}/derivatives`);
  },

    async getCryptoHealth() {
    return core.request<{ data: import('../types').CryptoHealthResponse; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/crypto/health');
  },

    async getCryptoMarketOverview() {
    return core.request<{ data: import('../types').CryptoMarketOverview; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/crypto/market-overview');
  },

    async getCryptoOrderBook(symbol: string, limit: number = 20, market: string = 'spot') {
    return core.request<{ data: import('../types').CryptoOrderBook; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/crypto/${encodeURIComponent(symbol)}/orderbook?limit=${limit}&market=${market}`);
  },

    async getCryptoQuote(symbol: string) {
    return core.request<{ data: import('../types').CryptoTicker; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/crypto/${encodeURIComponent(symbol)}/quote`);
  },

    async getCryptoScalpDiagnostics() {
    return core.request<import('../types').CryptoScalpDiagnostics>('/api/v1/crypto/scalp-signals/diagnostics');
  },

    async getCryptoScalpHistory(params?: { symbol?: string; limit?: number }) {
    const query = new URLSearchParams();
    if (params?.symbol) query.set('symbol', params.symbol);
    if (params?.limit) query.set('limit', String(params.limit));
    const qs = query.toString() ? `?${query.toString()}` : '';
    return core.request<import('../types').CryptoScalpSignal[]>(`/api/v1/crypto/scalp-signals/history${qs}`);
  },

    async getCryptoScalpLedger(params?: { symbol?: string; state?: string; limit?: number }) {
    const query = new URLSearchParams();
    if (params?.symbol) query.set('symbol', params.symbol);
    if (params?.state) query.set('state', params.state);
    if (params?.limit) query.set('limit', String(params.limit));
    const qs = query.toString() ? `?${query.toString()}` : '';
    return core.request<import('../types').CryptoScalpExecutionRecord[]>(`/api/v1/crypto/scalp-signals/ledger${qs}`);
  },

    async getCryptoScalpPerformance() {
    return core.request<import('../types').CryptoScalpPerformanceMetrics>('/api/v1/crypto/scalp-signals/performance');
  },

    async getCryptoScalpSignals(params?: { symbol?: string; direction?: string }) {
    const query = new URLSearchParams();
    if (params?.symbol) query.set('symbol', params.symbol);
    if (params?.direction) query.set('direction', params.direction);
    const qs = query.toString() ? `?${query.toString()}` : '';
    return core.request<import('../types').CryptoScalpSignalsResponse>(`/api/v1/crypto/scalp-signals${qs}`);
  },

    async getCryptoScalpTradeDetail(tradeId: string) {
    return core.request<import('../types').CryptoScalpExecutionRecord>(`/api/v1/crypto/scalp-signals/ledger/${tradeId}`);
  },

    async getCryptoSignals(symbol?: string) {
    const path = symbol ? `/api/v1/crypto/${encodeURIComponent(symbol)}/signals` : '/api/v1/crypto/signals';
    return core.request<{ data: import('../types').CryptoSignalsResponse; error: string | null; meta: import('../types').ApiMeta }>(path);
  },

    async getCryptoTickers() {
    return core.request<{ data: import('../types').CryptoTicker[]; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/crypto/tickers');
  },

    async triggerCryptoScalpScan() {
    return core.request<import('../types').CryptoScalpSignalsResponse>('/api/v1/crypto/scalp-signals/scan', {
      method: 'POST',
    });
  },

    async updateCryptoScalpConfig(config: import('../types').CryptoScalpConfig) {
    return core.request<import('../types').CryptoScalpConfig>('/api/v1/crypto/scalp-signals/config', {
      method: 'PATCH',
      body: JSON.stringify(config),
    });
  },
  };
}

export type CryptoApi = ReturnType<typeof createCryptoApi>;
