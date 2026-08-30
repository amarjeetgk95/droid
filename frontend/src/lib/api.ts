const API_BASE = (process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com').replace(/\/+$/, '');

class ApiClient {
  private baseUrl: string;
  private token: string | null = null;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl.replace(/\/+$/, '');
  }

  setToken(token: string | null) {
    this.token = token;
  }

  private async request<T>(path: string, options?: RequestInit): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options?.headers as Record<string, string> || {}),
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    const cleanPath = path.startsWith('/') ? path : `/${path}`;
    const url = `${this.baseUrl}${cleanPath}`;

    let response: Response;
    try {
      response = await fetch(url, {
        ...options,
        headers,
      });
    } catch {
      throw new Error(`Cannot reach backend at ${this.baseUrl}. Make sure the backend server is running.`);
    }

    const contentType = response.headers.get('content-type') || '';

    if (!response.ok) {
      if (contentType.includes('application/json')) {
        const error = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(error.detail || `API Error ${response.status}: ${response.statusText}`);
      } else {
        throw new Error(`Backend at ${this.baseUrl} returned error ${response.status} (${response.statusText}).`);
      }
    }

    if (!contentType.includes('application/json')) {
      throw new Error(`Backend at ${this.baseUrl} returned non-JSON response (${contentType || 'HTML'}). Make sure the backend server is running and accessible.`);
    }

    return response.json();
  }

  // Markets
  async getQuotes() {
    return this.request<{ data: import('./types').NormalizedQuote[]; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/markets/quotes');
  }

  async getQuote(symbol: string) {
    return this.request<{ data: import('./types').NormalizedQuote; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/markets/${encodeURIComponent(symbol)}/quote`);
  }

  async getCandles(symbol: string, timeframe: string = '5m') {
    return this.request<{ data: import('./types').NormalizedCandle[]; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/markets/${encodeURIComponent(symbol)}/candles?timeframe=${timeframe}`);
  }

  async getIndexCards() {
    return this.request<{ data: import('./types').IndexCard[]; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/markets/cards');
  }

  async getMarketStatus() {
    return this.request<{ data: import('./types').MarketStatusResponse; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/markets/status');
  }

  async getMarketBreadth() {
    return this.request<{ data: import('./types').MarketBreadthData; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/markets/breadth');
  }

  async getMarketHealth() {
    return this.request<import('./types').MarketHealthStatus>('/api/v1/health/market-data');
  }

  // Health
  async healthLive() {
    return this.request<{ status: string }>('/health/live');
  }

  async healthReady() {
    return this.request<{ status: string }>('/health/ready');
  }

  // Contracts & Expiries (Phase 2)
  async searchContracts(params?: { underlying?: string; contract_type?: string; expiry?: string; strike?: number }) {
    const query = new URLSearchParams();
    if (params?.underlying) query.set('underlying', params.underlying);
    if (params?.contract_type) query.set('contract_type', params.contract_type);
    if (params?.expiry) query.set('expiry', params.expiry);
    if (params?.strike) query.set('strike', params.strike.toString());
    return this.request<{ data: import('./types').ContractMaster[]; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/contracts/search?${query.toString()}`);
  }

  async getContractExpiries(symbol: string) {
    return this.request<{ data: import('./types').ExpiryResolution; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/contracts/${encodeURIComponent(symbol)}/expiries`);
  }

  async getContractMaster(symbol: string) {
    return this.request<{ data: import('./types').ContractMaster; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/contracts/${encodeURIComponent(symbol)}/master`);
  }

  // Calendar (Phase 2)
  async getHolidays(year?: number) {
    const query = year ? `?year=${year}` : '';
    return this.request<{ data: Record<string, string>; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/calendar/holidays${query}`);
  }

  async checkTradingDay(date?: string) {
    const query = date ? `?target_date=${date}` : '';
    return this.request<{ data: { date: string; is_trading_day: boolean; holiday_name: string | null }; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/calendar/is-trading-day${query}`);
  }

  async getSessionInfo(date?: string) {
    const query = date ? `?target_date=${date}` : '';
    return this.request<{ data: { is_trading_day: boolean; is_holiday: boolean; is_weekend: boolean; holiday_name: string | null; is_special_session: boolean; market_open: string | null; market_close: string | null }; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/calendar/session${query}`);
  }

  // Tokens & Telemetry (Phase 2)
  async getTokenStatus() {
    return this.request<{ data: Record<string, unknown>; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/tokens/status');
  }

  async refreshToken() {
    return this.request<{ data: { refreshed: boolean; provider: string; has_token: boolean }; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/tokens/refresh', { method: 'POST' });
  }

  // Cache & Performance (Phase 3)
  async getCacheStats() {
    return this.request<{ data: Record<string, unknown>; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/cache/stats');
  }

  async clearCache() {
    return this.request<{ data: { cleared: boolean }; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/cache/clear', { method: 'POST' });
  }

  // Circuit Breaker (Phase 3)
  async getCircuitBreakerStatus() {
    return this.request<{ data: Record<string, unknown>; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/circuit-breaker/status');
  }

  async resetCircuitBreaker() {
    return this.request<{ data: Record<string, unknown>; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/circuit-breaker/reset', { method: 'POST' });
  }

  async tripCircuitBreaker() {
    return this.request<{ data: Record<string, unknown>; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/circuit-breaker/trip', { method: 'POST' });
  }

  // Time-Series & Historical Query (Phase 3)
  async getHistoricalTimeSeries(symbol: string, timeframe: string = '5m', limit: number = 500) {
    return this.request<{ data: import('./types').NormalizedCandle[]; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/timeseries/${encodeURIComponent(symbol)}/history?timeframe=${timeframe}&limit=${limit}`);
  }

  async getPipelineStats() {
    return this.request<{ data: { timeseries_store: Record<string, unknown>; write_pipeline: Record<string, unknown> }; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/timeseries/pipeline-stats');
  }

  // Options & Greeks (Phase 4)
  async getOptionChain(symbol: string, expiry?: string) {
    const query = expiry ? `?expiry=${expiry}` : '';
    return this.request<{ data: import('./types').OptionChainResponse; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/options/${encodeURIComponent(symbol)}/chain${query}`);
  }

  async getOptionsAnalytics(symbol: string, expiry?: string) {
    const query = expiry ? `?expiry=${expiry}` : '';
    return this.request<{ data: import('./types').OptionsAnalytics; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/options/${encodeURIComponent(symbol)}/analytics${query}`);
  }

  async getMaxPain(symbol: string, expiry?: string) {
    const query = expiry ? `?expiry=${expiry}` : '';
    return this.request<{ data: import('./types').MaxPainResult; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/options/${encodeURIComponent(symbol)}/max-pain${query}`);
  }

  // Futures & Rollover Analytics (Phase 5)
  async getFuturesOverview(symbol: string) {
    return this.request<{ data: import('./types').FuturesOverview; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/futures/${encodeURIComponent(symbol)}/overview`);
  }

  async getFuturesTermStructure(symbol: string) {
    return this.request<{ data: import('./types').TermStructureCurve; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/futures/${encodeURIComponent(symbol)}/term-structure`);
  }

  async getFuturesBuildup(symbol: string) {
    return this.request<{ data: import('./types').OIBuildupItem; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/futures/${encodeURIComponent(symbol)}/buildup`);
  }

  async getFuturesRollover(symbol: string) {
    return this.request<{ data: import('./types').RolloverMetrics; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/futures/${encodeURIComponent(symbol)}/rollover`);
  }

  // Market Regime & Technical Analytics (Phase 6)
  async getRegimeOverview(symbol: string) {
    return this.request<{ data: import('./types').MarketRegimeOverview; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/regime/${encodeURIComponent(symbol)}/overview`);
  }

  async getRegimeKeyLevels(symbol: string) {
    return this.request<{ data: import('./types').KeyLevelsModel; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/regime/${encodeURIComponent(symbol)}/pivots`);
  }

  async getRegimeTechnicalIndicators(symbol: string) {
    return this.request<{ data: import('./types').TechnicalIndicators; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/regime/${encodeURIComponent(symbol)}/indicators`);
  }

  async getVixRegime() {
    return this.request<{ data: import('./types').VixRegimeInfo; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/regime/vix-status');
  }

  // Strategy Engine & Scanner (Phase 7)
  async calculateStrategyPayoff(payload: import('./types').StrategyPayload) {
    return this.request<{ data: import('./types').StrategyPayoffResult; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/strategy/payoff', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async getStrategyTemplates() {
    return this.request<{ data: import('./types').StrategyTemplate[]; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/strategy/templates');
  }

  async buildStrategyTemplate(templateId: string, symbol: string = 'NIFTY') {
    return this.request<{ data: import('./types').StrategyPayoffResult; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/strategy/build-template?template_id=${templateId}&symbol=${encodeURIComponent(symbol)}`, {
      method: 'POST',
    });
  }

  async scanMarketStrategies(outlook?: string, minPop: number = 35.0) {
    const query = new URLSearchParams();
    if (outlook) query.set('outlook', outlook);
    query.set('min_pop', minPop.toString());
    return this.request<{ data: import('./types').ScannedStrategy[]; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/strategy/scanner?${query.toString()}`);
  }

  // AI Market Analyst & Structured Insights (Phase 8)
  async generateAIAnalysis(symbol: string, provider: string = 'mock_ai') {
    return this.request<{ data: import('./types').AIInsightResponse; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/ai/analyze/${encodeURIComponent(symbol)}?provider=${provider}`, {
      method: 'POST',
    });
  }

  async testAIProvider(payload: { provider: string; symbol?: string; geminiApiKey?: string; geminiModel?: string; openRouterApiKey?: string; openRouterModel?: string; ollamaBaseUrl?: string; ollamaModel?: string }) {
    return this.request<{ data: { success: boolean; provider: string; model: string; latency_ms: number; schema_valid: boolean; is_mock?: boolean; message?: string; error?: string; hint?: string; insight?: import('./types').AIInsightResponse }; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/ai/test', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async getAIHistory(symbol: string) {
    return this.request<{ data: import('./types').AIHistoryItem[]; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/ai/history/${encodeURIComponent(symbol)}`);
  }

  // Historical Intelligence & Pattern Recognition (Phase 9)
  async getDetectedPatterns(symbol: string, timeframe: string = '5m') {
    return this.request<{ data: import('./types').DetectedPatternModel[]; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/history/${encodeURIComponent(symbol)}/patterns?timeframe=${timeframe}`);
  }

  async getHistoricalShifts(symbol: string, days: number = 10) {
    return this.request<{ data: import('./types').HistoricalShiftsResponse; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/history/${encodeURIComponent(symbol)}/shifts?days=${days}`);
  }

  async getSeasonality(symbol: string) {
    return this.request<{ data: import('./types').SeasonalityResponse; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/history/${encodeURIComponent(symbol)}/seasonality`);
  }

  async getWatchlist() {
    return this.request<{ data: import('./types').WatchlistItem[]; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/watchlist');
  }

  async addToWatchlist(symbol: string) {
    return this.request<{ data: { symbol: string; status: string }; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/watchlist/add?symbol=${encodeURIComponent(symbol)}`, {
      method: 'POST',
    });
  }

  async removeFromWatchlist(symbol: string) {
    return this.request<{ data: { symbol: string; status: string }; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/watchlist/remove?symbol=${encodeURIComponent(symbol)}`, {
      method: 'POST',
    });
  }

  // Quantitative Backtesting Engine (Phase 10)
  async runBacktest(payload: import('./types').BacktestPayload) {
    return this.request<{ data: import('./types').BacktestResult; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/backtest/run', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async getBacktestPresets() {
    return this.request<{ data: import('./types').BacktestPreset[]; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/backtest/presets');
  }

  async getBacktestHistory() {
    return this.request<{ data: import('./types').BacktestResult[]; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/backtest/history');
  }

  // Paper Trading & Virtual Execution (Phase 11)
  async getPaperPortfolio() {
    return this.request<{ data: import('./types').PortfolioSummary; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/paper/portfolio');
  }

  async getPaperPositions() {
    return this.request<{ data: import('./types').VirtualPosition[]; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/paper/positions');
  }

  async getPaperOrders() {
    return this.request<{ data: import('./types').VirtualOrder[]; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/paper/orders');
  }

  async placePaperOrder(payload: import('./types').OrderPayload) {
    return this.request<{ data: import('./types').VirtualOrder; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/paper/order', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async placePaperBasket(payload: import('./types').BasketOrderPayload) {
    return this.request<{ data: import('./types').VirtualOrder[]; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/paper/basket', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async squareOffPosition(positionId: string) {
    return this.request<{ data: import('./types').VirtualPosition; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/paper/position/square-off/${encodeURIComponent(positionId)}`, {
      method: 'POST',
    });
  }

  async squareOffAllPositions() {
    return this.request<{ data: import('./types').VirtualPosition[]; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/paper/square-off-all', {
      method: 'POST',
    });
  }

  async resetPaperAccount() {
    return this.request<{ data: import('./types').PortfolioSummary; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/paper/reset', {
      method: 'POST',
    });
  }

  // Real-Time Alerting Engine & System Telemetry (Phase 12)
  async listAlerts() {
    return this.request<{ data: import('./types').AlertRule[]; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/alerts');
  }

  async createAlert(payload: import('./types').AlertPayload) {
    return this.request<{ data: import('./types').AlertRule; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/alerts', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async deleteAlert(alertId: string) {
    return this.request<{ data: { alert_id: string; deleted: boolean }; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/alerts/${encodeURIComponent(alertId)}`, {
      method: 'DELETE',
    });
  }

  async toggleAlert(alertId: string) {
    return this.request<{ data: import('./types').AlertRule; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/alerts/${encodeURIComponent(alertId)}/toggle`, {
      method: 'POST',
    });
  }

  async evaluateAlerts() {
    return this.request<{ data: import('./types').AlertTriggerLog[]; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/alerts/evaluate', {
      method: 'POST',
    });
  }

  async getAlertHistory() {
    return this.request<{ data: import('./types').AlertTriggerLog[]; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/alerts/history');
  }

  async getTelemetry() {
    return this.request<{ data: import('./types').SystemTelemetry; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/alerts/telemetry');
  }

  // ML Prediction Engine
  async getMLPrediction(symbol: string = 'NIFTY') {
    return this.request<{ data: import('./types').MLPredictionResponse; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/ml/predict/${encodeURIComponent(symbol)}`);
  }

  // Institutional FII/DII Positioning & Cash Flows
  async getFIIDIIOverview() {
    return this.request<{ data: import('./types').FIIDIIOverviewResponse; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/fii-dii/overview');
  }

  // Cryptocurrency & Binance API Module
  async getCryptoTickers() {
    return this.request<{ data: import('./types').CryptoTicker[]; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/crypto/tickers');
  }

  async getCryptoQuote(symbol: string) {
    return this.request<{ data: import('./types').CryptoTicker; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/crypto/${encodeURIComponent(symbol)}/quote`);
  }

  async getCryptoCandles(symbol: string, timeframe: string = '1h', limit: number = 100) {
    return this.request<{ data: import('./types').NormalizedCandle[]; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/crypto/${encodeURIComponent(symbol)}/candles?timeframe=${encodeURIComponent(timeframe)}&limit=${limit}`);
  }

  async getCryptoOrderBook(symbol: string, limit: number = 20) {
    return this.request<{ data: import('./types').CryptoOrderBook; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/crypto/${encodeURIComponent(symbol)}/orderbook?limit=${limit}`);
  }

  async getCryptoDerivatives(symbol: string) {
    return this.request<{ data: import('./types').CryptoDerivatives; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/crypto/${encodeURIComponent(symbol)}/derivatives`);
  }

  async getCryptoMarketOverview() {
    return this.request<{ data: import('./types').CryptoMarketOverview; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/crypto/market-overview');
  }

  // Auth
  async getProfile() {
    return this.request<{ user_id: string; email: string | null; role: string }>('/api/v1/auth/profile');
  }

  async getFullProfile() {
    return this.request<import('./types').ProfileResponse>('/api/v1/auth/profile/full');
  }

  async updateProfile(display_name: string | null) {
    return this.request<import('./types').ProfileResponse>('/api/v1/auth/profile', {
      method: 'PATCH',
      body: JSON.stringify({ display_name }),
    });
  }

  // Settings
  async getSettings() {
    return this.request<import('./types').UserSettingsResponse>('/api/v1/settings');
  }

  async updateSettings(settings: Partial<import('./types').UserSettingsUpdate>) {
    return this.request<import('./types').UserSettingsResponse>('/api/v1/settings', {
      method: 'PATCH',
      body: JSON.stringify(settings),
    });
  }

  async createSettings(settings: import('./types').UserSettingsUpdate) {
    return this.request<import('./types').UserSettingsResponse>('/api/v1/settings', {
      method: 'POST',
      body: JSON.stringify(settings),
    });
  }

  // Chart Forecast & Multi-Timeframe
  async searchInstruments(q: string, asset_class?: string, fno_only?: boolean) {
    const params = new URLSearchParams({ q });
    if (asset_class) params.set('asset_class', asset_class);
    if (fno_only) params.set('fno_only', 'true');
    return this.request<{ data: { query: string; results: any[]; total: number }; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/instruments/search?${params.toString()}`);
  }
  async getChartAnalysis(symbol: string, timeframe?: string) {
    const qs = timeframe ? `?timeframe=${timeframe}` : '';
    return this.request<{ data: any; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/chart-analysis/${encodeURIComponent(symbol)}${qs}`);
  }

  // Watchlists (new Supabase-backed endpoints)
  async listWatchlists() {
    return this.request<import('./types').WatchlistResponse[]>('/api/v1/watchlists');
  }

  async getWatchlistById(watchlistId: string) {
    return this.request<import('./types').WatchlistResponse>(`/api/v1/watchlists/${watchlistId}`);
  }

  async createWatchlist(name: string) {
    return this.request<import('./types').WatchlistResponse>('/api/v1/watchlists', {
      method: 'POST',
      body: JSON.stringify({ name }),
    });
  }

  async updateWatchlist(watchlistId: string, name: string) {
    return this.request<import('./types').WatchlistResponse>(`/api/v1/watchlists/${watchlistId}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    });
  }

  async deleteWatchlist(watchlistId: string) {
    return this.request<void>(`/api/v1/watchlists/${watchlistId}`, { method: 'DELETE' });
  }

  async listWatchlistItems(watchlistId: string) {
    return this.request<import('./types').WatchlistItemResponse[]>(`/api/v1/watchlists/${watchlistId}/items`);
  }

  async addWatchlistItem(watchlistId: string, symbol: string) {
    return this.request<import('./types').WatchlistItemResponse>(`/api/v1/watchlists/${watchlistId}/items`, {
      method: 'POST',
      body: JSON.stringify({ symbol }),
    });
  }

  async updateWatchlistItem(watchlistId: string, itemId: string, data: { display_order?: number; symbol?: string }) {
    return this.request<import('./types').WatchlistItemResponse>(`/api/v1/watchlists/${watchlistId}/items/${itemId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async removeWatchlistItem(watchlistId: string, itemId: string) {
    return this.request<void>(`/api/v1/watchlists/${watchlistId}/items/${itemId}`, { method: 'DELETE' });
  }
}

export const api = new ApiClient(API_BASE);
