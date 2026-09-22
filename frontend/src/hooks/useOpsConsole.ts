'use client';

/* Ops Console data hook (operator surface, not a trading desk).
   Pattern mirrors useSignalDesk: Promise.allSettled group loads, per-group
   error strings, useSmartInterval polling. Overview + health poll at 30s
   while the market is open and 5min when closed; infra (cache / breakers /
   pipeline) loads once on mount and refreshes on demand only. */

import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { errorMessage } from '@/lib/errors';
import { dataFreshness, maxPayloadTimestampMs } from '@/lib/signalsNormalize';
import { useMarketSession } from '@/hooks/useMarketSession';
import { useSmartInterval } from './useSmartInterval';

export type OpsActionResult = {
  ok: boolean;
  message: string;
  data?: unknown;
};

export type HealthProbeKey =
  | 'live'
  | 'ready'
  | 'subsystems'
  | 'marketData'
  | 'database'
  | 'feed'
  | 'forecastConfig';

export type ProbeState = {
  data: unknown;
  error: string | null;
};

const EMPTY_PROBES: Record<HealthProbeKey, ProbeState> = {
  live: { data: null, error: null },
  ready: { data: null, error: null },
  subsystems: { data: null, error: null },
  marketData: { data: null, error: null },
  database: { data: null, error: null },
  feed: { data: null, error: null },
  forecastConfig: { data: null, error: null },
};

function settledData<T>(result: PromiseSettledResult<T>): T | null {
  return result.status === 'fulfilled' ? result.value : null;
}

function settledError(result: PromiseSettledResult<unknown>, fallback: string): string | null {
  return result.status === 'rejected' ? errorMessage(result.reason, fallback) : null;
}

export function useOpsConsole() {
  const { isOpen } = useMarketSession();
  const requestIdRef = useRef(0);

  const [summary, setSummary] = useState<any>(null);
  const [quotes, setQuotes] = useState<any[]>([]);
  const [marketStatus, setMarketStatus] = useState<any>(null);
  const [overviewErrors, setOverviewErrors] = useState<Record<string, string>>({});
  const [overviewLoading, setOverviewLoading] = useState(true);
  const [overviewRefreshing, setOverviewRefreshing] = useState(false);
  const [overviewUpdatedAt, setOverviewUpdatedAt] = useState<number | null>(null);

  const [symbolDash, setSymbolDash] = useState<{ symbol: string; data: any } | null>(null);
  const [symbolLoading, setSymbolLoading] = useState(false);
  const [symbolError, setSymbolError] = useState<string | null>(null);

  const [probes, setProbes] = useState<Record<HealthProbeKey, ProbeState>>(EMPTY_PROBES);
  const [healthLoading, setHealthLoading] = useState(true);
  const [healthUpdatedAt, setHealthUpdatedAt] = useState<number | null>(null);

  const [cacheStats, setCacheStats] = useState<any>(null);
  const [breaker, setBreaker] = useState<any>(null);
  const [orders, setOrders] = useState<any[]>([]);
  const [pipelineStats, setPipelineStats] = useState<any>(null);
  const [infraErrors, setInfraErrors] = useState<Record<string, string>>({});
  const [infraLoading, setInfraLoading] = useState(true);
  const [infraRefreshing, setInfraRefreshing] = useState(false);

  const [mutating, setMutating] = useState(false);

  const loadOverview = useCallback(async (showSpinner: boolean) => {
    const requestId = ++requestIdRef.current;
    if (showSpinner) setOverviewRefreshing(true);
    const [summaryRes, quotesRes, statusRes] = await Promise.allSettled([
      api.getDashboardSummary(),
      api.getQuotes(),
      api.getMarketStatus(),
    ]);
    if (requestIdRef.current !== requestId) return;
    const errors: Record<string, string> = {};
    const summaryErr = settledError(summaryRes, 'Dashboard summary unavailable');
    if (summaryErr) errors.summary = summaryErr;
    const quotesErr = settledError(quotesRes, 'Quotes unavailable');
    if (quotesErr) errors.quotes = quotesErr;
    const statusErr = settledError(statusRes, 'Market status unavailable');
    if (statusErr) errors.status = statusErr;
    setOverviewErrors(errors);
    if (settledData(summaryRes)) setSummary((settledData(summaryRes) as any)?.data ?? null);
    if (settledData(quotesRes)) setQuotes(((settledData(quotesRes) as any)?.data ?? []) as any[]);
    if (settledData(statusRes)) setMarketStatus((settledData(statusRes) as any)?.data ?? null);
    // Payload instants only — a failed or undated batch keeps the last age.
    const payloadTs = maxPayloadTimestampMs([
      summaryRes.status === 'fulfilled' ? summaryRes.value : null,
      quotesRes.status === 'fulfilled' ? quotesRes.value : null,
      statusRes.status === 'fulfilled' ? statusRes.value : null,
    ]);
    if (payloadTs !== null) {
      setOverviewUpdatedAt(payloadTs);
    }
    setOverviewLoading(false);
    if (showSpinner) setOverviewRefreshing(false);
  }, []);

  const loadHealth = useCallback(async () => {
    const requestId = ++requestIdRef.current;
    const [liveRes, readyRes, subsystemsRes, marketDataRes, dbRes, feedRes, forecastRes] =
      await Promise.allSettled([
        api.healthLive(),
        api.healthReady(),
        api.getSignalsSubsystemsHealth(),
        api.getMarketHealth(),
        api.getDbHealth(),
        api.getSignalsFeedHealth(),
        api.getForecastConfig(),
      ]);
    if (requestIdRef.current !== requestId) return;
    setProbes({
      live: { data: settledData(liveRes), error: settledError(liveRes, 'Liveness probe failed') },
      ready: { data: settledData(readyRes), error: settledError(readyRes, 'Readiness probe failed') },
      subsystems: { data: settledData(subsystemsRes), error: settledError(subsystemsRes, 'Subsystems probe failed') },
      marketData: { data: settledData(marketDataRes), error: settledError(marketDataRes, 'Market-data health unavailable') },
      database: { data: settledData(dbRes), error: settledError(dbRes, 'Database health unavailable') },
      feed: { data: settledData(feedRes), error: settledError(feedRes, 'Feed health unavailable') },
      forecastConfig: { data: settledData(forecastRes), error: settledError(forecastRes, 'Forecast config unavailable') },
    });
    // Payload instants only — a failed or undated batch keeps the last age.
    const payloadTs = maxPayloadTimestampMs([
      liveRes.status === 'fulfilled' ? liveRes.value : null,
      readyRes.status === 'fulfilled' ? readyRes.value : null,
      subsystemsRes.status === 'fulfilled' ? subsystemsRes.value : null,
      marketDataRes.status === 'fulfilled' ? marketDataRes.value : null,
      dbRes.status === 'fulfilled' ? dbRes.value : null,
      feedRes.status === 'fulfilled' ? feedRes.value : null,
      forecastRes.status === 'fulfilled' ? forecastRes.value : null,
    ]);
    if (payloadTs !== null) {
      setHealthUpdatedAt(payloadTs);
    }
    setHealthLoading(false);
  }, []);

  const loadInfra = useCallback(async (showSpinner: boolean) => {
    const requestId = ++requestIdRef.current;
    if (showSpinner) setInfraRefreshing(true);
    const [cacheRes, breakerRes, ordersRes, pipeRes] = await Promise.allSettled([
      api.getCacheStats(),
      api.getCircuitBreakerStatus(),
      api.listExecutionOrders(),
      api.getPipelineStats(),
    ]);
    if (requestIdRef.current !== requestId) return;
    const errors: Record<string, string> = {};
    const cacheErr = settledError(cacheRes, 'Cache stats unavailable');
    if (cacheErr) errors.cache = cacheErr;
    const breakerErr = settledError(breakerRes, 'Breaker status unavailable');
    if (breakerErr) errors.breaker = breakerErr;
    const ordersErr = settledError(ordersRes, 'Execution orders unavailable');
    if (ordersErr) errors.orders = ordersErr;
    const pipeErr = settledError(pipeRes, 'Pipeline stats unavailable');
    if (pipeErr) errors.pipeline = pipeErr;
    setInfraErrors(errors);
    if (settledData(cacheRes)) setCacheStats((settledData(cacheRes) as any)?.data ?? null);
    if (settledData(breakerRes)) setBreaker((settledData(breakerRes) as any)?.data ?? null);
    const ordersData = settledData(ordersRes) as any;
    if (ordersData) setOrders(Array.isArray(ordersData?.data) ? ordersData.data : []);
    if (settledData(pipeRes)) setPipelineStats((settledData(pipeRes) as any)?.data ?? null);
    setInfraLoading(false);
    if (showSpinner) setInfraRefreshing(false);
  }, []);

  useEffect(() => {
    void loadOverview(false);
    void loadHealth();
    void loadInfra(false);
  }, [loadOverview, loadHealth, loadInfra]);

  useSmartInterval(
    useCallback(() => {
      void loadOverview(false);
      void loadHealth();
    }, [loadOverview, loadHealth]),
    isOpen ? 30_000 : 300_000,
    { fireOnMount: false },
  );

  const refreshAll = useCallback(async () => {
    await Promise.all([loadOverview(true), loadHealth(), loadInfra(true)]);
  }, [loadOverview, loadHealth, loadInfra]);

  const loadSymbol = useCallback(async (symbol: string) => {
    const sym = symbol.trim().toUpperCase();
    if (!sym) {
      setSymbolError('Enter a symbol first.');
      return;
    }
    setSymbolLoading(true);
    setSymbolError(null);
    try {
      const payload = await api.getDashboardSymbol(sym);
      setSymbolDash({ symbol: sym, data: payload.data ?? null });
    } catch (err) {
      setSymbolDash(null);
      setSymbolError(errorMessage(err, `Dashboard for ${sym} unavailable`));
    } finally {
      setSymbolLoading(false);
    }
  }, []);

  const searchInstruments = useCallback(
    async (query: string): Promise<OpsActionResult & { results?: any[]; total?: number }> => {
      const q = query.trim();
      if (!q) return { ok: false, message: 'Enter a search query first.' };
      try {
        const payload = await api.searchInstruments(q);
        const results = payload.data?.results ?? [];
        return {
          ok: true,
          message: results.length === 0 ? `No instruments match "${q}".` : `${results.length} instrument(s) match "${q}".`,
          data: payload.data,
          results,
          total: payload.data?.total ?? results.length,
        };
      } catch (err) {
        return { ok: false, message: errorMessage(err, 'Instrument search unavailable') };
      }
    },
    [],
  );

  const runMutation = useCallback(
    async (label: string, fn: () => Promise<unknown>): Promise<OpsActionResult> => {
      setMutating(true);
      try {
        const data = await fn();
        return { ok: true, message: `${label} completed.`, data };
      } catch (err) {
        return { ok: false, message: errorMessage(err, `${label} failed`) };
      } finally {
        setMutating(false);
      }
    },
    [],
  );

  const clearCache = useCallback(async (): Promise<OpsActionResult> => {
    const result = await runMutation('Cache clear', () => api.clearCache());
    if (result.ok) void loadInfra(false);
    return result;
  }, [runMutation, loadInfra]);

  const resetBreaker = useCallback(async (): Promise<OpsActionResult> => {
    const result = await runMutation('Breaker reset', () => api.resetCircuitBreaker());
    if (result.ok) void loadInfra(false);
    return result;
  }, [runMutation, loadInfra]);

  const tripBreaker = useCallback(async (): Promise<OpsActionResult> => {
    const result = await runMutation('Breaker trip', () => api.tripCircuitBreaker());
    if (result.ok) void loadInfra(false);
    return result;
  }, [runMutation, loadInfra]);

  const captureState = useCallback(
    async (symbol: string, currentPrice: number, atr: number, regime: string): Promise<OpsActionResult> => {
      return runMutation('State capture', () => api.captureMarketState(symbol, currentPrice, atr, regime));
    },
    [runMutation],
  );

  const evaluateTrigger = useCallback(
    async (symbol: string, triggerType: string, currentPrice: number, significance?: number): Promise<OpsActionResult> => {
      return runMutation('Trigger evaluate', () => api.evaluateTrigger(symbol, triggerType, currentPrice, significance));
    },
    [runMutation],
  );

  const checkStaleness = useCallback(
    async (payload: Record<string, unknown>): Promise<OpsActionResult> => {
      return runMutation('Staleness check', () => api.checkStaleness(payload));
    },
    [runMutation],
  );

  const calculatePricing = useCallback(
    async (payload: Record<string, unknown>): Promise<OpsActionResult> => {
      return runMutation('Pricing calculate', () => api.calculatePricing(payload));
    },
    [runMutation],
  );

  const overviewFreshness = dataFreshness(overviewUpdatedAt);
  const healthFreshness = dataFreshness(healthUpdatedAt);

  return {
    isOpen,
    summary,
    quotes,
    marketStatus,
    overviewErrors,
    overviewLoading,
    overviewRefreshing,
    overviewUpdatedAt,
    overviewAgeMs: overviewFreshness.ageMs,
    overviewStale: overviewFreshness.stale,
    source: 'rest' as const,
    liveSource: 'rest' as const,
    symbolDash,
    symbolLoading,
    symbolError,
    probes,
    healthLoading,
    healthUpdatedAt,
    healthAgeMs: healthFreshness.ageMs,
    healthStale: healthFreshness.stale,
    cacheStats,
    breaker,
    orders,
    pipelineStats,
    infraErrors,
    infraLoading,
    infraRefreshing,
    mutating,
    refreshAll,
    refreshOverview: () => loadOverview(true),
    refreshHealth: () => loadHealth(),
    refreshInfra: () => loadInfra(true),
    loadSymbol,
    searchInstruments,
    clearCache,
    resetBreaker,
    tripBreaker,
    captureState,
    evaluateTrigger,
    checkStaleness,
    calculatePricing,
  };
}

export type OpsConsole = ReturnType<typeof useOpsConsole>;
