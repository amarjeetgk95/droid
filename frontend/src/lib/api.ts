// Local dev defaults to the local backend; production falls back to the hosted one.
const DEFAULT_API_URL =
  typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
    ? 'http://localhost:8000'
    : 'https://droid-backend-emeq.onrender.com';

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_URL).replace(/\/+$/, '');

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

    // Hard timeout — a hung backend must not leak stacked polling requests.
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10_000);

    let response: Response;
    try {
      response = await fetch(url, {
        ...options,
        headers,
        signal: options?.signal ?? controller.signal,
      });
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        throw new Error(`Request to ${this.baseUrl} timed out after 10s.`);
      }
      throw new Error(`Cannot reach backend at ${this.baseUrl}. Make sure the backend server is running.`);
    } finally {
      clearTimeout(timeoutId);
    }

    const contentType = response.headers.get('content-type') || '';

    if (!response.ok) {
      // Global 401 signal — lets AuthProvider/logout listeners react instead of
      // silent infinite 401 polling loops.
      if (response.status === 401 && typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('auth:unauthorized', { detail: { url } }));
      }
      if (contentType.includes('application/json')) {
        const error = await response.json().catch(() => ({ detail: response.statusText }));
        // Surface FREE-only guard hint and catalog fallback clearly
        const detail = error.detail || error.error || error.message || `API Error ${response.status}: ${response.statusText}`;
        const hint = error.hint ? ` Hint: ${error.hint}` : '';
        const extra = error.detail && error.detail.toLowerCase().includes('paid models are disabled')
          ? ' Hint: Select a FREE OpenRouter model (prompt=0 & completion=0). Try Auto — Best Free, or enable Allow Paid Models in Settings. Catalog will fallback to cached models if OpenRouter is temporarily unavailable.'
          : hint;
        const retry = response.status === 502 && error.detail && error.detail.toLowerCase().includes('openrouter catalog')
          ? ' (Retrying will use cached model list if available)'
          : '';
        throw new Error(`${detail}${extra}${retry}`);
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

  async getCandles(symbol: string, timeframe: string = '5m', limit?: number) {
    const qs = limit && limit > 0 ? `&limit=${Math.round(limit)}` : '';
    return this.request<{ data: import('./types').NormalizedCandle[]; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/markets/${encodeURIComponent(symbol)}/candles?timeframe=${timeframe}${qs}`);
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

  async refreshToken(payload?: Record<string, unknown>) {
    return this.request<{ data: { refreshed: boolean; provider: string; has_token: boolean }; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/tokens/refresh', {
      method: 'POST',
      body: payload ? JSON.stringify(payload) : undefined,
    });
  }

  async testBrokerConnection(payload: { provider: string; credentials: Record<string, unknown> }) {
    return this.request<{
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
      meta: import('./types').ApiMeta;
    }>('/api/v1/tokens/test-connection', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
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

  async getInstitutionalFlow(symbol: string, expiry?: string) {
    const query = expiry ? `?expiry=${expiry}` : '';
    return this.request<{ data: import('./types').InstitutionalFlowResponse; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/options/${encodeURIComponent(symbol)}/institutional-flow${query}`);
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

  // AI Market Analyst & Structured Insights (Phase 8) — Settings-driven (no hardcode)
  // NOTE: generateAIAnalysis is deprecated for gemini/ollama — use generateAIAnalysisWithModel (POST /api/v1/ai/analyze) for all connection modes.
  // Kept for back-compat; now forwards correctly to unified endpoint where needed.
  async generateAIAnalysis(
    symbol: string,
    provider: string = 'openrouter',
    opts?: {
      openRouterApiKey?: string;
      geminiApiKey?: string;
      geminiModel?: string;
      ollamaBaseUrl?: string;
      ollamaModel?: string;
      openaiApiKey?: string;
      openaiModel?: string;
      openaiBaseUrl?: string;
      novitaApiKey?: string;
      novitaModel?: string;
      novitaBaseUrl?: string;
      nvidiaApiKey?: string;
      nvidiaModel?: string;
      nvidiaBaseUrl?: string;
      customOpenaiApiKey?: string;
      customOpenaiModel?: string;
      customOpenaiBaseUrl?: string;
      apiKey?: string;
      model?: string;
      base_url?: string;
      [key: string]: unknown;
    },
  ) {
    // compat: mock_ai -> openrouter
    const normProvider = provider === 'mock_ai' ? 'openrouter' : provider;
    // For any non-openrouter via legacy endpoint, route via unified model-aware endpoint to ensure keys forwarded (gemini/ollama/direct providers)
    if (normProvider !== 'openrouter') {
      const payload: Record<string, unknown> = {
        symbol,
        provider: normProvider,
        ...opts,
      };
      // Ensure at least one key/model field propagates — fallback to unified endpoint which handles per-request key -> config fallback
      return this.generateAIAnalysisWithModel(payload as any);
    }
    const headers: Record<string, string> = {};
    if (opts?.openRouterApiKey) headers['X-OpenRouter-Key'] = opts.openRouterApiKey as string;
    if (opts?.geminiApiKey) headers['X-Gemini-Key'] = opts.geminiApiKey as string;
    const qp = opts?.openRouterApiKey ? `&openRouterApiKey=${encodeURIComponent(opts.openRouterApiKey as string)}` : '';
    const body = opts && Object.keys(opts).length > 0 ? JSON.stringify(opts) : undefined;
    return this.request<{ data: import('./types').AIInsightResponse; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/ai/analyze/${encodeURIComponent(symbol)}?provider=${normProvider}${qp}`, {
      method: 'POST',
      headers,
      body,
    });
  }

  async generateAIAnalysisWithModel(payload: {
    symbol?: string;
    model?: string;
    provider?: string;
    analysis_type?: string;
    allow_paid?: boolean;
    openRouterApiKey?: string;
    geminiApiKey?: string;
    geminiModel?: string;
    ollamaBaseUrl?: string;
    ollamaModel?: string;
    openaiApiKey?: string;
    openaiModel?: string;
    openaiBaseUrl?: string;
    novitaApiKey?: string;
    novitaModel?: string;
    novitaBaseUrl?: string;
    nvidiaApiKey?: string;
    nvidiaModel?: string;
    nvidiaBaseUrl?: string;
    customOpenaiApiKey?: string;
    customOpenaiModel?: string;
    customOpenaiBaseUrl?: string;
    apiKey?: string;
    base_url?: string;
    customBaseUrl?: string;
    [key: string]: unknown;
  }) {
    // compat: mock_ai -> openrouter for unified path
    const norm = { ...payload };
    if (norm.provider === 'mock_ai') norm.provider = 'openrouter';
    // Ollama local-only hint: if base_url is localhost, inform caller but still attempt (backend will gate with clear message)
    return this.request<{ data: import('./types').AIInsightResponse; error: string | null; meta: import('./types').ApiMeta; model_used?: string; latency_ms?: number; hint?: string }>('/api/v1/ai/analyze', {
      method: 'POST',
      body: JSON.stringify(norm),
    });
  }

  async testAIProvider(payload: {
    provider: string;
    symbol?: string;
    geminiApiKey?: string;
    geminiModel?: string;
    openRouterApiKey?: string;
    openRouterModel?: string;
    ollamaBaseUrl?: string;
    ollamaModel?: string;
    openaiApiKey?: string;
    openaiModel?: string;
    openaiBaseUrl?: string;
    novitaApiKey?: string;
    novitaModel?: string;
    novitaBaseUrl?: string;
    nvidiaApiKey?: string;
    nvidiaModel?: string;
    nvidiaBaseUrl?: string;
    customOpenaiApiKey?: string;
    customOpenaiModel?: string;
    customOpenaiBaseUrl?: string;
    apiKey?: string;
    model?: string;
    base_url?: string;
    customBaseUrl?: string;
    [key: string]: unknown;
  }) {
    // compat mock_ai -> openrouter
    const norm = { ...payload };
    if (norm.provider === 'mock_ai') norm.provider = 'openrouter';
    return this.request<{ data: { success: boolean; provider: string; model: string; latency_ms: number; schema_valid: boolean; is_mock?: boolean; message?: string; error?: string; hint?: string; insight?: import('./types').AIInsightResponse }; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/ai/test', {
      method: 'POST',
      body: JSON.stringify(norm),
    });
  }

  async getAIHistory(symbol: string) {
    return this.request<{ data: import('./types').AIHistoryItem[]; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/ai/history/${encodeURIComponent(symbol)}`);
  }

  // Live Interactive Streaming Copilot (SSE)
  async streamAIChat(
    payload: import('./types').AIChatRequest,
    onChunk: (chunk: import('./types').AIChatStreamChunk) => void,
    onError: (err: string) => void,
    onDone: () => void,
    signal?: AbortSignal
  ) {
    const url = `${this.baseUrl}/api/v1/ai/chat/stream`;
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }
    if (payload.openrouter_api_key) {
      headers['X-OpenRouter-Key'] = payload.openrouter_api_key;
    }
    if (payload.gemini_api_key) {
      headers['X-Gemini-Key'] = payload.gemini_api_key;
    }
    if (payload.openai_api_key) {
      headers['X-OpenAI-Key'] = payload.openai_api_key;
    }

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
        signal,
      });

      if (!response.ok) {
        const errText = await response.text();
        onError(`Server error ${response.status}: ${errText.slice(0, 300)}`);
        return;
      }

      const reader = response.body?.getReader();
      if (!reader) {
        onError('No readable stream available in response.');
        return;
      }

      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed || !trimmed.startsWith('data: ')) continue;
          const jsonStr = trimmed.slice(6).trim();
          if (jsonStr === '[DONE]') {
            onDone();
            return;
          }
          try {
            const chunk: import('./types').AIChatStreamChunk = JSON.parse(jsonStr);
            onChunk(chunk);
            if (chunk.type === 'done') {
              onDone();
            } else if (chunk.type === 'error') {
              onError(chunk.delta || 'Unknown stream error');
            }
          } catch {
            // Ignore parse errors on partial chunks
          }
        }
      }
      onDone();
    } catch (err: any) {
      if (err.name === 'AbortError') {
        onDone();
      } else {
        onError(err.message || 'Stream connection failed.');
      }
    }
  }

  // Options Strategy Architect
  async recommendOptionsStrategy(payload: import('./types').AIOptionsStrategyRequest) {
    const headers: Record<string, string> = {};
    if (payload.openrouter_api_key) headers['X-OpenRouter-Key'] = payload.openrouter_api_key;
    if (payload.gemini_api_key) headers['X-Gemini-Key'] = payload.gemini_api_key;
    return this.request<{ data: import('./types').AIOptionsStrategyRecommendation; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/ai/strategy/recommend', {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    });
  }

  // Trade Thesis & Invalidation Auditor
  async validateTradeSetup(payload: import('./types').AITradeValidationRequest) {
    const headers: Record<string, string> = {};
    if (payload.openrouter_api_key) headers['X-OpenRouter-Key'] = payload.openrouter_api_key;
    if (payload.gemini_api_key) headers['X-Gemini-Key'] = payload.gemini_api_key;
    return this.request<{ data: import('./types').AITradeValidationResponse; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/ai/trade/validate', {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    });
  }

  // Daily Market Briefing (Pre/Post-Market)
  async getMarketBriefing(symbol: string, sessionType: string = 'PRE_MARKET') {
    return this.request<{ data: import('./types').AIDailyBriefingResponse; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/ai/briefing/${encodeURIComponent(symbol)}?session_type=${sessionType}`);
  }

  // Dynamic OpenRouter Model Catalog (Free-Model-Only)
  async getAIModels(params?: { free_only?: boolean; pricing?: string; refresh?: boolean }) {
    const query = new URLSearchParams();
    if (params?.free_only !== undefined) query.set('free_only', String(params.free_only));
    if (params?.pricing) query.set('pricing', params.pricing);
    if (params?.refresh) query.set('refresh', 'true');
    const qs = query.toString();
    return this.request<{ data: { provider: string; updated_at: string; free_only: boolean; pricing_filter: string; models: import('./types').OpenRouterModel[]; default_model: import('./types').OpenRouterModel | null; total_count: number; free_count: number; paid_count: number; using_cached: boolean; cache_error?: string; cache_age_seconds: number }; error: string | null; meta: import('./types').ApiMeta; using_cached?: boolean }>(`/api/v1/ai/models${qs ? `?${qs}` : ''}`);
  }

  async refreshAIModels() {
    return this.request<{ data: { provider: string; updated_at: string; free_only: boolean; models: import('./types').OpenRouterModel[]; default_model: import('./types').OpenRouterModel | null; using_cached: boolean }; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/ai/models/refresh`, { method: 'POST' });
  }

  // Back-compat alias for spec: /api/ai/models
  async getAIModelsCompat(params?: { free_only?: boolean; pricing?: string; refresh?: boolean }) {
    const query = new URLSearchParams();
    if (params?.free_only !== undefined) query.set('free_only', String(params.free_only));
    if (params?.pricing) query.set('pricing', params.pricing);
    if (params?.refresh) query.set('refresh', 'true');
    const qs = query.toString();
    return this.request<{ data: any; error: string | null; meta: import('./types').ApiMeta }>(`/api/ai/models${qs ? `?${qs}` : ''}`);
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

  // Historical Intelligence v2 — Pattern Outcomes & Hit Rates
  async getPatternHitRates(symbol: string, timeframe?: string) {
    const query = timeframe ? `?timeframe=${timeframe}` : '';
    return this.request<{ data: import('./types').PatternHitRateResponse; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/history/${encodeURIComponent(symbol)}/hit-rates${query}`);
  }

  async getPatternOutcomes(symbol: string, patternTypes?: string, timeframe?: string, limit: number = 20) {
    const params = new URLSearchParams();
    if (patternTypes) params.set('pattern_types', patternTypes);
    if (timeframe) params.set('timeframe', timeframe);
    params.set('limit', limit.toString());
    return this.request<{ data: import('./types').PatternOutcomeRecord[]; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/history/${encodeURIComponent(symbol)}/outcomes?${params.toString()}`);
  }

  async labelPatternOutcomes(symbol: string, patternTypes?: string, timeframe?: string) {
    const params = new URLSearchParams();
    if (patternTypes) params.set('pattern_types', patternTypes);
    if (timeframe) params.set('timeframe', timeframe);
    return this.request<{ data: { symbol: string; labeled_count: number; status: string }; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/history/${encodeURIComponent(symbol)}/label-outcomes`, {
      method: 'POST',
      body: JSON.stringify({ pattern_types: patternTypes, timeframe }),
    });
  }

  async refreshHitRatesView() {
    return this.request<{ data: { refreshed: boolean }; error: string | null; meta: import('./types').ApiMeta }>('/api/v1/history/hit-rates/refresh', {
      method: 'POST',
    });
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

  // ============================================================================
  // Telegram Integration
  // ============================================================================

  async getTelegramStatus() {
    return this.request<{
      bot_configured: boolean;
      bot_username: string | null;
      webhook_configured: boolean;
      binding: { linked: boolean; telegram_chat_id: string | null; linked_at: number | null; status: string };
      environment: string;
      queue_stats: Record<string, unknown>;
    }>('/api/v1/telegram/status');
  }

  async generateTelegramLink() {
    return this.request<{ url: string; ttl_seconds: number; bot_username: string }>(
      '/api/v1/telegram/link/generate',
      { method: 'POST' },
    );
  }

  async revokeTelegramLink() {
    return this.request<{ status: string }>('/api/v1/telegram/link/revoke', { method: 'POST' });
  }

  async getTelegramPreferences() {
    return this.request<import('./types').TelegramPreferences>('/api/v1/telegram/preferences');
  }

  async updateTelegramPreferences(prefs: import('./types').TelegramPreferences) {
    return this.request<import('./types').TelegramPreferences>('/api/v1/telegram/preferences', {
      method: 'PUT',
      body: JSON.stringify(prefs),
    });
  }

  async sendTelegramTestMessage() {
    return this.request<{ status: string; notification_id: string }>('/api/v1/telegram/test', {
      method: 'POST',
    });
  }

  async getTelegramAudit(limit = 50) {
    return this.request<{ records: Record<string, unknown>[] }>(
      `/api/v1/telegram/audit?limit=${limit}`,
    );
  }

  async resetTelegramPreferences() {
    return this.request<import('./types').TelegramPreferences>('/api/v1/telegram/preferences/reset', { method: 'POST' });
  }

  async bulkTelegramPreferences(enable: boolean) {
    return this.request<import('./types').TelegramPreferences>('/api/v1/telegram/preferences/bulk', {
      method: 'POST',
      body: JSON.stringify({ enable }),
    });
  }

  async previewTelegramEvent(event: Record<string, unknown>) {
    return this.request<{ event_type: string; instrument: string; preview: string }>('/api/v1/telegram/dev/preview', {
      method: 'POST',
      body: JSON.stringify(event),
    });
  }

  async quickTestTelegram(params: { instrument: string; event_type: string; candle_timeframe: string; direction: string; setup_type?: string }) {
    const qs = new URLSearchParams({
      instrument: params.instrument,
      event_type: params.event_type,
      candle_timeframe: params.candle_timeframe,
      direction: params.direction,
      setup_type: params.setup_type || (params.direction === 'BEARISH' ? 'BREAKDOWN' : 'BREAKOUT'),
    }).toString();
    return this.request<{ status: string; notification_ids: string[]; signal_id: string; preview: string; event: Record<string, unknown> }>(
      `/api/v1/telegram/dev/quick-test?${qs}`,
      { method: 'POST' },
    );
  }

  async devPublishTelegramEvent(event: Record<string, unknown>) {
    return this.request<{ status: string; notification_ids: string[] }>('/api/v1/telegram/dev/publish-event', {
      method: 'POST',
      body: JSON.stringify(event),
    });
  }

  async getTelegramStats() {
    return this.request<{ notification_queue: Record<string, unknown>; outbound_queue_size: number; link_count: number }>(
      '/api/v1/telegram/stats',
    );
  }

  // Instruments Search
  async searchInstruments(q: string, asset_class?: string, fno_only?: boolean) {
    const params = new URLSearchParams({ q });
    if (asset_class) params.set('asset_class', asset_class);
    if (fno_only) params.set('fno_only', 'true');
    return this.request<{ data: { query: string; results: any[]; total: number }; error: string | null; meta: import('./types').ApiMeta }>(`/api/v1/instruments/search?${params.toString()}`);
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

  // Pipeline & Safety Gates (§4, §6, §7, §22, §23, §25, §28, §40) — forecast validation removed
  async captureMarketState(symbol: string = 'NIFTY') {
    return this.request<any>(`/api/v1/pipeline/state/capture?symbol=${encodeURIComponent(symbol)}`, { method: 'POST' });
  }
  async checkStaleness(payload: any) {
    return this.request<any>('/api/v1/pipeline/staleness/check', { method: 'POST', body: JSON.stringify(payload) });
  }
  async calculatePricing(payload: any) {
    return this.request<any>('/api/v1/pipeline/pricing/calculate', { method: 'POST', body: JSON.stringify(payload) });
  }
  async createExecutionSignal(symbol: string, side: string, quantity: number) {
    return this.request<any>(`/api/v1/pipeline/execution/signal?symbol=${encodeURIComponent(symbol)}&side=${side}&quantity=${quantity}`, { method: 'POST' });
  }
  async listExecutionOrders() {
    return this.request<any>('/api/v1/pipeline/execution/orders');
  }
  async transitionExecution(orderId: string, toState: string) {
    return this.request<any>(`/api/v1/pipeline/execution/${encodeURIComponent(orderId)}/transition?to_state=${toState}`, { method: 'POST' });
  }
  async getDashboard(symbol: string = 'NIFTY') {
    return this.request<any>(`/api/v1/dashboard/${encodeURIComponent(symbol)}`);
  }

  async getDashboardSummary() {
    return this.request<{
      data: {
        cards: any[];
        breadth: any;
        health: any;
        market_status: any;
        ml_prediction: any;
        fii_dii: any;
        regime_overview: any;
        errors: Record<string, string>;
        degraded: boolean;
        generated_at: string;
      };
      error: string | null;
      meta: import('./types').ApiMeta;
    }>('/api/v1/dashboard/summary');
  }

  // Historical Pattern Intelligence (HPI) — user-controlled derivative & historical data
  async getHpiUniverse() {
    return this.request<{ data: import('./types').HpiUniverse; error: string | null; meta: any }>('/api/v1/hpi/universe');
  }
  async getHpiSelection() {
    return this.request<{ data: import('./types').HpiSelectionState; error: string | null; meta: any }>('/api/v1/hpi/selection');
  }
  async updateHpiSelection(entries: import('./types').HpiSelectionEntry[]) {
    return this.request<{ data: import('./types').HpiSelectionState; error: string | null; meta: any }>('/api/v1/hpi/selection', { method: 'PUT', body: JSON.stringify({ entries }) });
  }
  async listHpiPolicies(symbol?: string) {
    const q = symbol ? `?symbol=${encodeURIComponent(symbol)}` : '';
    return this.request<{ data: import('./types').HpiPolicy[]; error: string | null; meta: any }>(`/api/v1/hpi/policies${q}`);
  }
  async createHpiPolicy(policy: Partial<import('./types').HpiPolicy>) {
    return this.request<{ data: import('./types').HpiPolicy; error: string | null; meta: any }>('/api/v1/hpi/policies', { method: 'POST', body: JSON.stringify(policy) });
  }
  async updateHpiPolicy(policyId: string, patch: Partial<import('./types').HpiPolicy>) {
    return this.request<{ data: import('./types').HpiPolicy; error: string | null; meta: any }>(`/api/v1/hpi/policies/${encodeURIComponent(policyId)}`, { method: 'PATCH', body: JSON.stringify(patch) });
  }
  async deleteHpiPolicy(policyId: string) {
    return this.request<any>(`/api/v1/hpi/policies/${encodeURIComponent(policyId)}`, { method: 'DELETE' });
  }
  async getHpiStorageReport() {
    return this.request<{ data: import('./types').HpiStorageReport; error: string | null; meta: any }>('/api/v1/hpi/storage/report');
  }
  async hpiImport(req: Record<string, unknown>) {
    return this.request<{ data: import('./types').HpiImportPreview | import('./types').HpiImportResult; error: string | null; meta: any }>('/api/v1/hpi/import', { method: 'POST', body: JSON.stringify(req) });
  }
  async hpiDeletePreview(req: Record<string, unknown>) {
    return this.request<{ data: import('./types').HpiDeletePreview; error: string | null; meta: any }>('/api/v1/hpi/delete/preview', { method: 'POST', body: JSON.stringify(req) });
  }
  async hpiDeleteConfirm(token: string, reason?: string) {
    return this.request<{ data: any; error: string | null; meta: any }>('/api/v1/hpi/delete/confirm', { method: 'POST', body: JSON.stringify({ confirmation_token: token, reason }) });
  }
  async getHpiAudit(symbol?: string) {
    const q = symbol ? `?symbol=${encodeURIComponent(symbol)}` : '';
    return this.request<{ data: import('./types').HpiAuditEntry[]; error: string | null; meta: any }>(`/api/v1/hpi/audit/deletions${q}`);
  }
  async hpiAutoDelete() {
    return this.request<any>('/api/v1/hpi/maintenance/auto-delete', { method: 'POST' });
  }
  async getHpiCoverage(symbol: string) {
    return this.request<{ data: import('./types').HpiCoverageReport; error: string | null; meta: any }>(`/api/v1/hpi/coverage/${encodeURIComponent(symbol)}`);
  }
  async getHpiAnalysis(symbol: string, timeframe: string = '5m') {
    return this.request<{ data: import('./types').HpiAnalysis; error: string | null; meta: any }>(`/api/v1/hpi/analysis/${encodeURIComponent(symbol)}?timeframe=${timeframe}`);
  }

  // Direct Providers testing
  async testDirectProvider(provider: string, payload: any) {
    return this.request<any>('/api/v1/ai/test', { method: 'POST', body: JSON.stringify({ provider, ...payload }) });
  }

  // Institutional — Market Intelligence & Execution Platform §71-76
  async getInstitutionalInstruments() {
    return this.request<any>('/api/v1/institutional/instruments');
  }
  async getInstitutionalMI(payload: any) {
    return this.request<any>('/api/v1/institutional/market-intelligence/evaluate', { method: 'POST', body: JSON.stringify(payload) });
  }
  async getInstitutionalBreakout(payload: any) {
    return this.request<any>('/api/v1/institutional/breakout/evaluate', { method: 'POST', body: JSON.stringify(payload) });
  }
  async getInstitutionalHealth() {
    return this.request<any>('/api/v1/institutional/health/data');
  }
  async getInstitutionalMIDashboard(instrument: string) {
    return this.request<any>(`/api/v1/institutional/dashboard/market-intelligence?instrument_id=${encodeURIComponent(instrument)}`);
  }
  async getInstitutionalDataHealthDashboard() {
    return this.request<any>('/api/v1/institutional/dashboard/data-health');
  }
  async institutionalPipelineIngest(event: any, mockAi?: any) {
    const body: any = { ...event };
    if (mockAi) body.mock_ai_response = mockAi;
    // Actually endpoint is POST /pipeline/ingest with event body + query mock_ai_response
    const qs = mockAi ? `?mock_ai_response=${encodeURIComponent(JSON.stringify(mockAi))}` : '';
    // Use direct fetch to handle async; we fake via JSON body inclusion
    return this.request<any>('/api/v1/institutional/pipeline/ingest', { method: 'POST', body: JSON.stringify(event) });
  }
  async institutionalIngestDirect(event: any) {
    return this.request<any>('/api/v1/institutional/pipeline/ingest', { method: 'POST', body: JSON.stringify(event) });
  }
  async getInstitutionalSignal(signalId: string) {
    return this.request<any>(`/api/v1/institutional/signals/${encodeURIComponent(signalId)}`);
  }
  async getInstitutionalAuditRecent(limit = 20) {
    return this.request<any>(`/api/v1/institutional/audit/recent?limit=${limit}`);
  }

  // Unified Signals Facade — dedicated Signal Generation module
  async getSignalsActive(params?: { instrument?: string; status?: string; engine?: string }) {
    const qs = new URLSearchParams();
    if (params?.instrument) qs.set('instrument', params.instrument);
    if (params?.status) qs.set('status', params.status);
    if (params?.engine) qs.set('engine', params.engine);
    const q = qs.toString() ? `?${qs.toString()}` : '';
    return this.request<{ signals: any[]; count: number; generated_at_ms: number }>(`/api/v1/signals/active${q}`);
  }
  async getSignalsHistory(limit = 20) {
    return this.request<{ records: any[] }>(`/api/v1/signals/history?limit=${limit}`);
  }
  async getSignal(signalId: string) {
    return this.request<any>(`/api/v1/signals/${encodeURIComponent(signalId)}`);
  }
  async getSignalEngines() {
    return this.request<{ engines: any[] }>(`/api/v1/signals/engines`);
  }
  async generateSignal(payload: Record<string, any>) {
    return this.request<{ signal: any; signal_obj: any; telegram: { enqueued: number; notification_ids: string[]; skipped_reason?: string | null }; is_expired: boolean; ttl_remaining_ms: number }>(
      `/api/v1/signals/generate`,
      { method: 'POST', body: JSON.stringify(payload) },
    );
  }
  async previewSignal(payload: Record<string, any>) {
    return this.request<{ preview: string; event: any; event_type: string; instrument: string }>(`/api/v1/signals/preview`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }
}

export const api = new ApiClient(API_BASE);
