'use client';

/* AI Copilot data hooks. All network I/O for the /copilot module lives here —
   components stay render-only (no timers, no polling, no fetch). */

import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { useInstrument } from '@/context/InstrumentContext';
import {
  buildAnalyzePayload,
  buildChatBase,
  missingKeyHint,
  resolveAISettings,
  toBackendSymbol,
  useAISettings,
} from '@/lib/aiPayload';
import { errorMessage } from '@/lib/errors';
import {
  applyChatChunk,
  buildChatMessages,
  copilotErrorHint,
  createPendingAssistant,
  createUserMessage,
  normalizeAnalyzeReport,
  normalizeBriefing,
  normalizeHistoryList,
  normalizeModelOptions,
  normalizeStrategy,
  normalizeValidation,
  parseChatChunk,
  flattenReport,
  type AnalyzeReport,
  type BriefingCard,
  type CopilotMessage,
  type HistoryRow,
  type ModelOption,
  type StrategyPlan,
  type ValidationVerdict,
} from '@/lib/copilot';
import type {
  AIChatRequest,
  AIOptionsStrategyRequest,
  AITradeValidationRequest,
  OpenRouterModel,
} from '@/lib/types';

// ---------------------------------------------------------------------------
// Composite: instrument-aware defaults + settings-derived provider for headers
// ---------------------------------------------------------------------------

export function useCopilot() {
  const { instrument, setInstrument, allInstruments } = useInstrument();
  const settings = useAISettings();
  const resolved = resolveAISettings(settings);
  return {
    instrument,
    setInstrument,
    allInstruments,
    provider: resolved.provider,
    model: resolved.model,
    keyHint: missingKeyHint(settings),
  };
}

// ---------------------------------------------------------------------------
// Streaming chat session (POST /api/v1/ai/chat/stream via api.streamAIChat)
// ---------------------------------------------------------------------------

export type AiChatOptions = {
  symbol?: string;
  /** Model override from the picker; falls back to the Settings default. */
  model?: string | null;
};

export type AiChatState = {
  messages: CopilotMessage[];
  sending: boolean;
  streamError: string | null;
  streamHint: string | null;
  provider: string;
  modelId: string | null;
  keyHint: string | null;
  send: (text: string) => void;
  stop: () => void;
  clear: () => void;
};

export function useAiChat(options: AiChatOptions = {}): AiChatState {
  const { instrument } = useInstrument();
  const settings = useAISettings();
  const symbol = toBackendSymbol(options.symbol ?? instrument);
  const resolved = resolveAISettings(settings);
  const pickerModel = (options.model ?? '').trim();
  const modelId = pickerModel || resolved.model || null;

  const [messages, setMessages] = useState<CopilotMessage[]>([]);
  const [sending, setSending] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [streamHint, setStreamHint] = useState<string | null>(null);

  const messagesRef = useRef<CopilotMessage[]>([]);
  const settingsRef = useRef(settings);
  const abortRef = useRef<AbortController | null>(null);
  const sendingRef = useRef(false);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);
  useEffect(() => {
    settingsRef.current = settings;
  }, [settings]);

  useEffect(() => {
    const active = abortRef.current;
    return () => {
      try {
        active?.abort();
      } catch {
        // ignore
      }
    };
  }, []);

  const finish = useCallback((assistantId: string, err: string | null) => {
    sendingRef.current = false;
    abortRef.current = null;
    setSending(false);
    setMessages((prev) =>
      prev.map((m) => (m.id === assistantId ? { ...m, pending: false, error: m.error ?? err } : m)),
    );
    if (err) {
      setStreamError(err);
      setStreamHint(copilotErrorHint(err).hint);
    }
  }, []);

  const send = useCallback(
    (text: string) => {
      const body = text.trim();
      if (!body || sendingRef.current) return;
      sendingRef.current = true;
      setSending(true);
      setStreamError(null);
      setStreamHint(null);

      const user = createUserMessage(body);
      const assistant = createPendingAssistant();
      const history = messagesRef.current;
      setMessages((prev) => [...prev, user, assistant]);

      const base = buildChatBase(settingsRef.current, symbol, 'copilot');
      const payload: AIChatRequest = {
        messages: buildChatMessages(history, body),
        temperature: 0.3,
        ...base,
        model: modelId,
      };

      const controller = new AbortController();
      abortRef.current = controller;
      const assistantId = assistant.id;

      api.streamAIChat(
        payload,
        (chunk) => {
          const safe = parseChatChunk(chunk);
          if (!safe) return; // never fabricate content from unparseable frames
          if (safe.type === 'error') {
            setStreamError(safe.delta || 'Stream error');
            setStreamHint(copilotErrorHint(safe.delta || '').hint);
          }
          setMessages((prev) => prev.map((m) => (m.id === assistantId ? applyChatChunk(m, safe) : m)));
        },
        (err) => finish(assistantId, err),
        () => finish(assistantId, null),
        controller.signal,
      );
    },
    [finish, modelId, symbol],
  );

  const stop = useCallback(() => {
    try {
      abortRef.current?.abort();
    } catch {
      // ignore
    }
  }, []);

  const clear = useCallback(() => {
    try {
      abortRef.current?.abort();
    } catch {
      // ignore
    }
    abortRef.current = null;
    sendingRef.current = false;
    setMessages([]);
    setSending(false);
    setStreamError(null);
    setStreamHint(null);
  }, []);

  return {
    messages,
    sending,
    streamError,
    streamHint,
    provider: resolved.provider,
    modelId,
    keyHint: missingKeyHint(settings),
    send,
    stop,
    clear,
  };
}

// ---------------------------------------------------------------------------
// Model catalog (GET /models, POST /models/refresh, GET /models/cache-status)
// ---------------------------------------------------------------------------

export type ModelsCache = {
  usingCached: boolean;
  ageSeconds: number | null;
  totalCount: number | null;
};

export type CopilotModelsState = {
  models: OpenRouterModel[];
  options: ModelOption[];
  defaultModelId: string | null;
  totalCount: number | null;
  freeCount: number | null;
  paidCount: number | null;
  cache: ModelsCache | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  refresh: () => Promise<void>;
};

export function useCopilotModels(): CopilotModelsState {
  const [models, setModels] = useState<OpenRouterModel[]>([]);
  const [defaultModelId, setDefaultModelId] = useState<string | null>(null);
  const [totalCount, setTotalCount] = useState<number | null>(null);
  const [freeCount, setFreeCount] = useState<number | null>(null);
  const [paidCount, setPaidCount] = useState<number | null>(null);
  const [cache, setCache] = useState<ModelsCache | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  const applyCatalog = useCallback(
    (data: {
      models?: unknown;
      default_model?: { id?: unknown } | null;
      total_count?: unknown;
      free_count?: unknown;
      paid_count?: unknown;
      using_cached?: unknown;
      cache_age_seconds?: unknown;
    }) => {
      const list = Array.isArray(data.models) ? (data.models as OpenRouterModel[]) : [];
      setModels(list);
      const defId = data.default_model && typeof data.default_model.id === 'string' ? data.default_model.id : null;
      setDefaultModelId(defId);
      setTotalCount(typeof data.total_count === 'number' ? data.total_count : list.length);
      setFreeCount(typeof data.free_count === 'number' ? data.free_count : null);
      setPaidCount(typeof data.paid_count === 'number' ? data.paid_count : null);
      setCache({
        usingCached: data.using_cached === true,
        ageSeconds: typeof data.cache_age_seconds === 'number' ? data.cache_age_seconds : null,
        totalCount: typeof data.total_count === 'number' ? data.total_count : list.length,
      });
    },
    [],
  );

  const load = useCallback(async () => {
    const requestId = ++requestIdRef.current;
    setLoading(true);
    const [catalogResult, cacheResult] = await Promise.allSettled([
      api.getAIModels(),
      api.getAIModelsCacheStatus(),
    ]);
    if (requestIdRef.current !== requestId) return;
    if (catalogResult.status === 'fulfilled') {
      applyCatalog((catalogResult.value as { data?: unknown }).data as never);
      const envelopeError = (catalogResult.value as { error?: unknown }).error;
      setError(typeof envelopeError === 'string' && envelopeError ? envelopeError : null);
    } else {
      setError(errorMessage(catalogResult.reason, 'Model catalog unavailable'));
    }
    if (cacheResult.status === 'fulfilled') {
      const data = (cacheResult.value as { data?: Record<string, unknown> }).data ?? {};
      setCache((prev) => ({
        usingCached: data.using_cached === true || data.cached === true,
        ageSeconds: typeof data.age_seconds === 'number' ? data.age_seconds : (prev?.ageSeconds ?? null),
        totalCount: typeof data.total_count === 'number' ? data.total_count : (prev?.totalCount ?? null),
      }));
    }
    setLoading(false);
  }, [applyCatalog]);

  useEffect(() => {
    void load();
  }, [load]);

  const refresh = useCallback(async () => {
    const requestId = ++requestIdRef.current;
    setRefreshing(true);
    try {
      const result = await api.refreshAIModels();
      if (requestIdRef.current !== requestId) return;
      applyCatalog((result as { data?: unknown }).data as never);
      setError(null);
    } catch (err) {
      if (requestIdRef.current !== requestId) return;
      setError(errorMessage(err, 'Model refresh failed'));
    } finally {
      if (requestIdRef.current === requestId) setRefreshing(false);
    }
  }, [applyCatalog]);

  return {
    models,
    options: normalizeModelOptions(models),
    defaultModelId,
    totalCount,
    freeCount,
    paidCount,
    cache,
    loading,
    refreshing,
    error,
    refresh,
  };
}

// ---------------------------------------------------------------------------
// Briefing (GET /briefing/{symbol} + GET /deep-insight/{symbol})
// ---------------------------------------------------------------------------

export type CopilotBriefingState = {
  briefing: BriefingCard | null;
  deepRows: Array<{ label: string; value: string }>;
  deepError: string | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  session: string;
  setSession: (s: string) => void;
  refresh: () => Promise<void>;
};

export function useCopilotBriefing(symbol: string): CopilotBriefingState {
  const clean = toBackendSymbol(symbol);
  const [briefing, setBriefing] = useState<BriefingCard | null>(null);
  const [deepRows, setDeepRows] = useState<Array<{ label: string; value: string }>>([]);
  const [deepError, setDeepError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [session, setSession] = useState('PRE_MARKET');
  const requestIdRef = useRef(0);

  const refresh = useCallback(async () => {
    const requestId = ++requestIdRef.current;
    setRefreshing(true);
    const [briefingResult, deepResult] = await Promise.allSettled([
      api.getMarketBriefing(clean, session),
      api.getDeepInsight(clean),
    ]);
    if (requestIdRef.current !== requestId) return;
    if (briefingResult.status === 'fulfilled') {
      const card = normalizeBriefing((briefingResult.value as { data?: unknown }).data);
      setBriefing(card);
      setError(card ? null : 'Briefing payload was empty or unparseable.');
    } else {
      setBriefing(null);
      setError(errorMessage(briefingResult.reason, 'Briefing unavailable'));
    }
    if (deepResult.status === 'fulfilled') {
      const envelope = deepResult.value as { data?: unknown; error?: unknown };
      const rows = flattenReport(envelope.data);
      setDeepRows(rows);
      setDeepError(typeof envelope.error === 'string' && envelope.error ? envelope.error : null);
    } else {
      setDeepRows([]);
      setDeepError(errorMessage(deepResult.reason, 'Deep insight unavailable'));
    }
    setLoading(false);
    setRefreshing(false);
  }, [clean, session]);

  useEffect(() => {
    setLoading(true);
    void refresh();
  }, [refresh]);

  return { briefing, deepRows, deepError, loading, refreshing, error, session, setSession, refresh };
}

// ---------------------------------------------------------------------------
// Analyze (POST /analyze or /analyze/{symbol}/with-model + GET /history/{symbol})
// ---------------------------------------------------------------------------

export type CopilotAnalyzeState = {
  report: AnalyzeReport | null;
  modelUsed: string | null;
  history: HistoryRow[];
  analyzing: boolean;
  historyLoading: boolean;
  error: string | null;
  historyError: string | null;
  analyze: (symbol: string, modelOverride: string) => Promise<boolean>;
  loadHistory: (symbol: string) => Promise<void>;
};

export function useCopilotAnalyze(): CopilotAnalyzeState {
  const settings = useAISettings();
  const settingsRef = useRef(settings);
  useEffect(() => {
    settingsRef.current = settings;
  }, [settings]);

  const [report, setReport] = useState<AnalyzeReport | null>(null);
  const [modelUsed, setModelUsed] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryRow[]>([]);
  const [analyzing, setAnalyzing] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const analyze = useCallback(async (symbol: string, modelOverride: string): Promise<boolean> => {
    const clean = toBackendSymbol(symbol);
    const override = modelOverride.trim();
    setAnalyzing(true);
    setError(null);
    try {
      if (override) {
        const stored = settingsRef.current;
        const resolved = resolveAISettings(stored);
        const result = await api.analyzeSymbolWithModel(clean, {
          model: override,
          allow_paid: resolved.allow_paid,
          openRouterApiKey: resolved.openRouterApiKey || undefined,
          geminiApiKey: resolved.geminiApiKey || undefined,
        });
        const parsed = normalizeAnalyzeReport((result as { data?: unknown }).data);
        if (!parsed) throw new Error('Analyze payload was empty or unparseable.');
        setReport(parsed);
        setModelUsed(typeof (result as { model_used?: unknown }).model_used === 'string' ? (result as { model_used?: string }).model_used ?? null : null);
      } else {
        const result = await api.generateAIAnalysisWithModel(buildAnalyzePayload(clean, settingsRef.current));
        const parsed = normalizeAnalyzeReport((result as { data?: unknown }).data);
        if (!parsed) throw new Error('Analyze payload was empty or unparseable.');
        setReport(parsed);
        setModelUsed(typeof (result as { model_used?: unknown }).model_used === 'string' ? (result as { model_used?: string }).model_used ?? null : null);
      }
      return true;
    } catch (err) {
      setError(errorMessage(err, 'Analysis failed'));
      return false;
    } finally {
      setAnalyzing(false);
    }
  }, []);

  const loadHistory = useCallback(async (symbol: string): Promise<void> => {
    const clean = toBackendSymbol(symbol);
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const result = await api.getAIHistory(clean);
      setHistory(normalizeHistoryList((result as { data?: unknown }).data));
    } catch (err) {
      setHistory([]);
      setHistoryError(errorMessage(err, 'History unavailable'));
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  return { report, modelUsed, history, analyzing, historyLoading, error, historyError, analyze, loadHistory };
}

// ---------------------------------------------------------------------------
// Validate (POST /trade/validate, POST /strategy/recommend, POST /test)
// ---------------------------------------------------------------------------

export type TradeSetupInput = {
  symbol: string;
  direction: 'BUY' | 'SELL';
  entry: number;
  stop: number;
  target: number;
  thesis?: string;
};

export type StrategyInput = {
  symbol: string;
  outlook: AIOptionsStrategyRequest['outlook'];
  query?: string;
  risk?: AIOptionsStrategyRequest['max_risk_tolerance'];
};

export type BackendTestResult = {
  success: boolean;
  provider: string;
  model: string | null;
  latencyMs: number | null;
  detail: string | null;
};

export type CopilotValidateState = {
  verdict: ValidationVerdict | null;
  strategy: StrategyPlan | null;
  testResult: BackendTestResult | null;
  busy: string | null;
  error: string | null;
  validateTrade: (input: TradeSetupInput) => Promise<boolean>;
  recommendStrategy: (input: StrategyInput) => Promise<boolean>;
  runTest: (symbol: string) => Promise<boolean>;
};

export function useCopilotValidate(): CopilotValidateState {
  const settings = useAISettings();
  const settingsRef = useRef(settings);
  useEffect(() => {
    settingsRef.current = settings;
  }, [settings]);

  const [verdict, setVerdict] = useState<ValidationVerdict | null>(null);
  const [strategy, setStrategy] = useState<StrategyPlan | null>(null);
  const [testResult, setTestResult] = useState<BackendTestResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const validateTrade = useCallback(async (input: TradeSetupInput): Promise<boolean> => {
    setBusy('validate');
    setError(null);
    try {
      const base = buildChatBase(settingsRef.current, toBackendSymbol(input.symbol), 'copilot');
      const payload: AITradeValidationRequest = {
        symbol: toBackendSymbol(input.symbol),
        timeframe: '15m',
        direction: input.direction,
        entry_price: input.entry,
        stop_loss: input.stop,
        target_price: input.target,
        thesis_notes: input.thesis?.trim() ? input.thesis.trim() : null,
        provider: base.provider,
        model: base.model,
        allow_paid: base.allow_paid,
        openrouter_api_key: base.openrouter_api_key,
        gemini_api_key: base.gemini_api_key,
      };
      const result = await api.validateTradeSetup(payload);
      const parsed = normalizeValidation((result as { data?: unknown }).data);
      if (!parsed) throw new Error('Validation payload was empty or unparseable.');
      setVerdict(parsed);
      return true;
    } catch (err) {
      setError(errorMessage(err, 'Trade validation failed'));
      return false;
    } finally {
      setBusy(null);
    }
  }, []);

  const recommendStrategy = useCallback(async (input: StrategyInput): Promise<boolean> => {
    setBusy('strategy');
    setError(null);
    try {
      const base = buildChatBase(settingsRef.current, toBackendSymbol(input.symbol), 'copilot');
      const payload: AIOptionsStrategyRequest = {
        symbol: toBackendSymbol(input.symbol),
        outlook: input.outlook,
        custom_query: input.query?.trim() ? input.query.trim() : null,
        max_risk_tolerance: input.risk ?? 'MODERATE',
        provider: base.provider,
        model: base.model,
        allow_paid: base.allow_paid,
        openrouter_api_key: base.openrouter_api_key,
        gemini_api_key: base.gemini_api_key,
      };
      const result = await api.recommendOptionsStrategy(payload);
      const parsed = normalizeStrategy((result as { data?: unknown }).data);
      if (!parsed) throw new Error('Strategy payload was empty or unparseable.');
      setStrategy(parsed);
      return true;
    } catch (err) {
      setError(errorMessage(err, 'Strategy recommendation failed'));
      return false;
    } finally {
      setBusy(null);
    }
  }, []);

  const runTest = useCallback(async (symbol: string): Promise<boolean> => {
    setBusy('test');
    setError(null);
    try {
      const resolved = resolveAISettings(settingsRef.current);
      const result = await api.testAi({ provider: resolved.provider, symbol: toBackendSymbol(symbol), model: resolved.model });
      const data = (result as { data?: Record<string, unknown> }).data ?? {};
      const success = data.success === true;
      setTestResult({
        success,
        provider: typeof data.provider === 'string' ? data.provider : resolved.provider,
        model: typeof data.model === 'string' ? data.model : null,
        latencyMs: typeof data.latency_ms === 'number' ? data.latency_ms : null,
        detail:
          typeof data.error === 'string' && data.error
            ? data.error
            : typeof data.hint === 'string' && data.hint
              ? data.hint
              : null,
      });
      if (!success) {
        const hint = copilotErrorHint(
          `${typeof data.error === 'string' ? data.error : ''} ${typeof data.hint === 'string' ? data.hint : ''}`,
        );
        setError(hint.hint);
      }
      return success;
    } catch (err) {
      setTestResult(null);
      setError(errorMessage(err, 'Backend check failed'));
      return false;
    } finally {
      setBusy(null);
    }
  }, []);

  return { verdict, strategy, testResult, busy, error, validateTrade, recommendStrategy, runTest };
}
