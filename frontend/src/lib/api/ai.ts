import type { ApiCore } from './client';

export function createAiApi(core: ApiCore) {
  return {
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
      return (core as unknown as { generateAIAnalysisWithModel(payload: unknown): Promise<never> }).generateAIAnalysisWithModel(payload);
    }
    const headers: Record<string, string> = {};
    if (opts?.openRouterApiKey) headers['X-OpenRouter-Key'] = opts.openRouterApiKey as string;
    if (opts?.geminiApiKey) headers['X-Gemini-Key'] = opts.geminiApiKey as string;
    const qp = opts?.openRouterApiKey ? `&openRouterApiKey=${encodeURIComponent(opts.openRouterApiKey as string)}` : '';
    const body = opts && Object.keys(opts).length > 0 ? JSON.stringify(opts) : undefined;
    return core.request<{ data: import('../types').AIInsightResponse; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/ai/analyze/${encodeURIComponent(symbol)}?provider=${normProvider}${qp}`, {
      method: 'POST',
      headers,
      body,
    });
  },

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
    return core.request<{ data: import('../types').AIInsightResponse; error: string | null; meta: import('../types').ApiMeta; model_used?: string; latency_ms?: number; hint?: string }>('/api/v1/ai/analyze', {
      method: 'POST',
      body: JSON.stringify(norm),
    });
  },

    async getAIHistory(symbol: string) {
    return core.request<{ data: import('../types').AIHistoryItem[]; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/ai/history/${encodeURIComponent(symbol)}`);
  },

    async getAIModels(params?: { free_only?: boolean; pricing?: string; refresh?: boolean }) {
    const query = new URLSearchParams();
    if (params?.free_only !== undefined) query.set('free_only', String(params.free_only));
    if (params?.pricing) query.set('pricing', params.pricing);
    if (params?.refresh) query.set('refresh', 'true');
    const qs = query.toString();
    return core.request<{ data: { provider: string; updated_at: string; free_only: boolean; pricing_filter: string; models: import('../types').OpenRouterModel[]; default_model: import('../types').OpenRouterModel | null; total_count: number; free_count: number; paid_count: number; using_cached: boolean; cache_error?: string; cache_age_seconds: number }; error: string | null; meta: import('../types').ApiMeta; using_cached?: boolean }>(`/api/v1/ai/models${qs ? `?${qs}` : ''}`);
  },

    async getAIModelsCompat(params?: { free_only?: boolean; pricing?: string; refresh?: boolean }) {
    const query = new URLSearchParams();
    if (params?.free_only !== undefined) query.set('free_only', String(params.free_only));
    if (params?.pricing) query.set('pricing', params.pricing);
    if (params?.refresh) query.set('refresh', 'true');
    const qs = query.toString();
    return core.request<{ data: any; error: string | null; meta: import('../types').ApiMeta }>(`/api/ai/models${qs ? `?${qs}` : ''}`);
  },

    async getMarketBriefing(symbol: string, sessionType: string = 'PRE_MARKET') {
    return core.request<{ data: import('../types').AIDailyBriefingResponse; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/ai/briefing/${encodeURIComponent(symbol)}?session_type=${sessionType}`);
  },

    async recommendOptionsStrategy(payload: import('../types').AIOptionsStrategyRequest) {
    const headers: Record<string, string> = {};
    if (payload.openrouter_api_key) headers['X-OpenRouter-Key'] = payload.openrouter_api_key;
    if (payload.gemini_api_key) headers['X-Gemini-Key'] = payload.gemini_api_key;
    return core.request<{ data: import('../types').AIOptionsStrategyRecommendation; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/ai/strategy/recommend', {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    });
  },

    async refreshAIModels() {
    return core.request<{ data: { provider: string; updated_at: string; free_only: boolean; models: import('../types').OpenRouterModel[]; default_model: import('../types').OpenRouterModel | null; using_cached: boolean }; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/ai/models/refresh`, { method: 'POST' });
  },

    async streamAIChat(
    payload: import('../types').AIChatRequest,
    onChunk: (chunk: import('../types').AIChatStreamChunk) => void,
    onError: (err: string) => void,
    onDone: () => void,
    signal?: AbortSignal
  ) {
    const url = `${core.getBaseUrl()}/api/v1/ai/chat/stream`;
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (core.getToken()) {
      headers['Authorization'] = `Bearer ${core.getToken()}`;
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
            const chunk: import('../types').AIChatStreamChunk = JSON.parse(jsonStr);
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
  },

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
    return core.request<{ data: { success: boolean; provider: string; model: string; latency_ms: number; schema_valid: boolean; is_mock?: boolean; message?: string; error?: string; hint?: string; insight?: import('../types').AIInsightResponse }; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/ai/test', {
      method: 'POST',
      body: JSON.stringify(norm),
    });
  },

    async validateTradeSetup(payload: import('../types').AITradeValidationRequest) {
    const headers: Record<string, string> = {};
    if (payload.openrouter_api_key) headers['X-OpenRouter-Key'] = payload.openrouter_api_key;
    if (payload.gemini_api_key) headers['X-Gemini-Key'] = payload.gemini_api_key;
    return core.request<{ data: import('../types').AITradeValidationResponse; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/ai/trade/validate', {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    });
  },
  };
}

export type AiApi = ReturnType<typeof createAiApi>;
