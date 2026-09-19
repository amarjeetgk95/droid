'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '@/lib/api';
import type { StrategyTemplate } from '@/lib/api/strategy';
import { useCommandSection } from '@/context/AppStreamContext';
import { errorMessage } from '@/lib/errors';
import { getObj } from '@/lib/signalsNormalize';
import type {
  InstitutionalFlowResponse,
  KeyLevelsModel,
  MarketRegimeOverview,
  MaxPainResult,
  OptionChainResponse,
  OptionsAnalytics,
  PortfolioGreeksSummary,
  TechnicalIndicators,
  VixRegimeInfo,
} from '@/lib/types';
import type { FuturesBuildup, FuturesOverviewData, FuturesRollover, FuturesTermStructure } from '@/lib/api/options';
import type { BuiltTemplateStrategy, StrategyLegInput, StrategyScannerData } from '@/lib/api/strategy';
import { normalizeInstrumentKey, pickRegimeStreamEntry, type InstrumentKey } from '@/lib/optionsDesk';
import { useSmartInterval } from './useSmartInterval';

export type ToolOutcome = {
  ok: boolean;
  message: string;
  value: Record<string, unknown> | null;
};

function toRecord(value: unknown): Record<string, unknown> | null {
  return getObj(value);
}

export type OptionsDeskState = {
  instrument: InstrumentKey;
  chain: OptionChainResponse | null;
  analytics: OptionsAnalytics | null;
  analyticsSource: 'stream' | 'rest';
  maxPain: MaxPainResult | null;
  flow: InstitutionalFlowResponse | null;
  regimeOverview: MarketRegimeOverview | null;
  regimeSource: 'stream' | 'rest';
  pivots: KeyLevelsModel | null;
  indicators: TechnicalIndicators | null;
  vix: VixRegimeInfo | null;
  futuresOverview: FuturesOverviewData | null;
  futuresTerm: FuturesTermStructure | null;
  futuresBuildup: FuturesBuildup | null;
  futuresRollover: FuturesRollover | null;
  templates: StrategyTemplate[];
  scanner: StrategyScannerData | null;
  portfolioGreeks: PortfolioGreeksSummary | null;
  research: Record<string, unknown> | null;
  expiries: string[];
  expiry: string | null;
  setExpiry: (expiry: string | null) => void;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  updatedAt: number | null;
  refresh: () => Promise<void>;
  calcGreeks: (params: {
    spot: number;
    strike: number;
    dte_days: number;
    volatility: number;
    option_type: 'CE' | 'PE';
  }) => Promise<ToolOutcome>;
  solveIv: (params: {
    market_price: number;
    spot: number;
    strike: number;
    dte_days: number;
    option_type: 'CE' | 'PE';
  }) => Promise<ToolOutcome>;
  simulatePath: (params: {
    underlying: string;
    spot: number;
    strike: number;
    option_type: 'CE' | 'PE';
    dte_days: number;
    iv: number;
    target_spot: number;
    stop_spot: number;
    quantity: number;
  }) => Promise<ToolOutcome>;
  selectContract: (params: {
    underlying: 'NIFTY' | 'BANKNIFTY' | 'SENSEX';
    spot_price: number;
    direction: 'LONG_CALL' | 'LONG_PUT';
    expected_move_points?: number | null;
    stop_loss_points?: number;
    target_horizon_hours?: number;
    current_iv?: number;
  }) => Promise<ToolOutcome>;
  projectExpectedMove: (params: {
    underlying: string;
    spot: number;
    direction: 'BULLISH' | 'BEARISH';
    horizon?: string;
    current_iv?: number;
    atr?: number | null;
  }) => Promise<ToolOutcome>;
  buildTemplate: (
    templateId: string,
  ) => Promise<ToolOutcome & { strategy: BuiltTemplateStrategy | null }>;
  calcPayoff: (payload: {
    underlying: string;
    spot_price: number;
    expiry?: string | null;
    legs: StrategyLegInput[];
  }) => Promise<ToolOutcome>;
  synthesizeResearch: (params: {
    horizon: string;
    direction: 'BULLISH' | 'BEARISH';
  }) => Promise<ToolOutcome>;
};

export function useOptionsDesk(
  instrumentInput: string,
  options: { safetyRefreshMs?: number | null } = {},
): OptionsDeskState {
  const { safetyRefreshMs = null } = options;
  const instrument = normalizeInstrumentKey(instrumentInput);
  const regimeSection = useCommandSection('regime');

  const [chain, setChain] = useState<OptionChainResponse | null>(null);
  const [restAnalytics, setRestAnalytics] = useState<OptionsAnalytics | null>(null);
  const [maxPain, setMaxPain] = useState<MaxPainResult | null>(null);
  const [flow, setFlow] = useState<InstitutionalFlowResponse | null>(null);
  const [restRegime, setRestRegime] = useState<MarketRegimeOverview | null>(null);
  const [pivots, setPivots] = useState<KeyLevelsModel | null>(null);
  const [indicators, setIndicators] = useState<TechnicalIndicators | null>(null);
  const [vix, setVix] = useState<VixRegimeInfo | null>(null);
  const [futuresOverview, setFuturesOverview] = useState<FuturesOverviewData | null>(null);
  const [futuresTerm, setFuturesTerm] = useState<FuturesTermStructure | null>(null);
  const [futuresBuildup, setFuturesBuildup] = useState<FuturesBuildup | null>(null);
  const [futuresRollover, setFuturesRollover] = useState<FuturesRollover | null>(null);
  const [templates, setTemplates] = useState<StrategyTemplate[]>([]);
  const [scanner, setScanner] = useState<StrategyScannerData | null>(null);
  const [portfolioGreeks, setPortfolioGreeks] = useState<PortfolioGreeksSummary | null>(null);
  const [research, setResearch] = useState<Record<string, unknown> | null>(null);
  const [expiry, setExpiryState] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);

  const requestIdRef = useRef(0);
  const instrumentRef = useRef(instrument);
  instrumentRef.current = instrument;
  const expiryRef = useRef<string | null>(expiry);
  expiryRef.current = expiry;

  const load = useCallback(async (showSpinner: boolean) => {
    const requestId = ++requestIdRef.current;
    if (showSpinner) setRefreshing(true);
    const symbol = instrumentRef.current;
    const selectedExpiry = expiryRef.current ?? undefined;
    const [
      chainResult,
      analyticsResult,
      maxPainResult,
      flowResult,
      regimeResult,
      pivotsResult,
      indicatorsResult,
      vixResult,
      futOverviewResult,
      futTermResult,
      futBuildupResult,
      futRolloverResult,
      templatesResult,
      scannerResult,
      greeksResult,
      researchResult,
    ] = await Promise.allSettled([
      api.getOptionChain(symbol, selectedExpiry),
      api.getOptionsAnalytics(symbol, selectedExpiry),
      api.getMaxPain(symbol, selectedExpiry),
      api.getInstitutionalFlow(symbol, selectedExpiry),
      api.getRegimeOverview(symbol),
      api.getRegimeKeyLevels(symbol),
      api.getRegimeTechnicalIndicators(symbol),
      api.getVixRegime(),
      api.getFuturesOverview(symbol),
      api.getFuturesTermStructure(symbol),
      api.getFuturesBuildup(symbol),
      api.getFuturesRollover(symbol),
      api.getStrategyTemplates(),
      api.getStrategyScanner(),
      api.getPortfolioGreeksSummary(),
      api.getFinancialResearch(symbol),
    ]);
    if (requestIdRef.current !== requestId) return;

    const failures: string[] = [];

    if (chainResult.status === 'fulfilled') {
      setChain(chainResult.value?.data ?? null);
      if (chainResult.value?.error) failures.push(chainResult.value.error);
    } else {
      failures.push(errorMessage(chainResult.reason, 'Option chain unavailable'));
    }
    if (analyticsResult.status === 'fulfilled') {
      setRestAnalytics(analyticsResult.value?.data ?? null);
      if (analyticsResult.value?.error) failures.push(analyticsResult.value.error);
    } else {
      failures.push(errorMessage(analyticsResult.reason, 'Options analytics unavailable'));
    }
    if (maxPainResult.status === 'fulfilled') {
      setMaxPain(maxPainResult.value?.data ?? null);
      if (maxPainResult.value?.error) failures.push(maxPainResult.value.error);
    } else {
      failures.push(errorMessage(maxPainResult.reason, 'Max pain unavailable'));
    }
    if (flowResult.status === 'fulfilled') {
      setFlow(flowResult.value?.data ?? null);
      if (flowResult.value?.error) failures.push(flowResult.value.error);
    } else {
      failures.push(errorMessage(flowResult.reason, 'Institutional flow unavailable'));
    }
    if (regimeResult.status === 'fulfilled') {
      setRestRegime(regimeResult.value?.data ?? null);
      if (regimeResult.value?.error) failures.push(regimeResult.value.error);
    } else {
      failures.push(errorMessage(regimeResult.reason, 'Regime overview unavailable'));
    }
    if (pivotsResult.status === 'fulfilled') {
      setPivots(pivotsResult.value?.data ?? null);
      if (pivotsResult.value?.error) failures.push(pivotsResult.value.error);
    } else {
      failures.push(errorMessage(pivotsResult.reason, 'Key levels unavailable'));
    }
    if (indicatorsResult.status === 'fulfilled') {
      setIndicators(indicatorsResult.value?.data ?? null);
      if (indicatorsResult.value?.error) failures.push(indicatorsResult.value.error);
    } else {
      failures.push(errorMessage(indicatorsResult.reason, 'Technical indicators unavailable'));
    }
    if (vixResult.status === 'fulfilled') {
      setVix(vixResult.value?.data ?? null);
      if (vixResult.value?.error) failures.push(vixResult.value.error);
    } else {
      failures.push(errorMessage(vixResult.reason, 'VIX status unavailable'));
    }
    if (futOverviewResult.status === 'fulfilled') {
      setFuturesOverview(futOverviewResult.value?.data ?? null);
      if (futOverviewResult.value?.error) failures.push(futOverviewResult.value.error);
    } else {
      failures.push(errorMessage(futOverviewResult.reason, 'Futures overview unavailable'));
    }
    if (futTermResult.status === 'fulfilled') {
      setFuturesTerm(futTermResult.value?.data ?? null);
    } else {
      failures.push(errorMessage(futTermResult.reason, 'Futures term structure unavailable'));
    }
    if (futBuildupResult.status === 'fulfilled') {
      setFuturesBuildup(futBuildupResult.value?.data ?? null);
    } else {
      failures.push(errorMessage(futBuildupResult.reason, 'Futures buildup unavailable'));
    }
    if (futRolloverResult.status === 'fulfilled') {
      setFuturesRollover(futRolloverResult.value?.data ?? null);
    } else {
      failures.push(errorMessage(futRolloverResult.reason, 'Futures rollover unavailable'));
    }
    if (templatesResult.status === 'fulfilled') {
      setTemplates(templatesResult.value?.data ?? []);
    } else {
      failures.push(errorMessage(templatesResult.reason, 'Strategy templates unavailable'));
    }
    if (scannerResult.status === 'fulfilled') {
      setScanner(scannerResult.value?.data ?? null);
      if (scannerResult.value?.error) failures.push(scannerResult.value.error);
    } else {
      failures.push(errorMessage(scannerResult.reason, 'Strategy scanner unavailable'));
    }
    if (greeksResult.status === 'fulfilled') {
      setPortfolioGreeks(greeksResult.value ?? null);
    } else {
      failures.push(errorMessage(greeksResult.reason, 'Portfolio Greeks unavailable'));
    }
    if (researchResult.status === 'fulfilled') {
      setResearch(toRecord(researchResult.value));
    } else {
      failures.push(errorMessage(researchResult.reason, 'Financial research unavailable'));
    }

    setError(failures.length > 0 ? failures[0] : null);
    setUpdatedAt(Date.now());
    setLoading(false);
    if (showSpinner) setRefreshing(false);
  }, []);

  // Reset the expiry pin when the instrument changes; the loader effect below
  // re-fetches on both keys.
  useEffect(() => {
    setExpiryState(null);
  }, [instrument]);

  useEffect(() => {
    setLoading(true);
    void load(false);
  }, [load, instrument, expiry]);

  useSmartInterval(
    useCallback(() => load(false), [load]),
    safetyRefreshMs,
    { fireOnMount: false },
  );

  const refresh = useCallback(async () => {
    await load(true);
  }, [load]);

  const setExpiry = useCallback((next: string | null) => {
    setExpiryState(next);
  }, []);

  // Read panels prefer the CommandView regime section; REST is the fallback.
  const streamEntry = useMemo(
    () => pickRegimeStreamEntry(regimeSection?.value, instrument),
    [regimeSection?.value, instrument],
  );
  const streamRegime = useMemo(
    () => getObj(streamEntry.regimeOverview) as MarketRegimeOverview | null,
    [streamEntry.regimeOverview],
  );
  const streamAnalytics = useMemo(
    () => getObj(streamEntry.optionsAnalytics) as OptionsAnalytics | null,
    [streamEntry.optionsAnalytics],
  );
  const regimeOverview = streamRegime ?? restRegime;
  const regimeSource: 'stream' | 'rest' = streamRegime ? 'stream' : 'rest';
  const analytics = streamAnalytics ?? restAnalytics;
  const analyticsSource: 'stream' | 'rest' = streamAnalytics ? 'stream' : 'rest';

  const expiries = useMemo(() => {
    const list = chain?.expiries;
    return Array.isArray(list) ? list.filter((e): e is string => typeof e === 'string' && e.length > 0) : [];
  }, [chain]);

  const runTool = useCallback(
    async (label: string, action: () => Promise<unknown>): Promise<ToolOutcome> => {
      try {
        const value = await action();
        return { ok: true, message: `${label} complete.`, value: toRecord(value) };
      } catch (err) {
        return { ok: false, message: errorMessage(err, `${label} failed`), value: null };
      }
    },
    [],
  );

  const calcGreeks = useCallback(
    (params: { spot: number; strike: number; dte_days: number; volatility: number; option_type: 'CE' | 'PE' }) =>
      runTool('Greeks calculation', () => api.calculateGreeks(params)),
    [runTool],
  );

  const solveIv = useCallback(
    (params: { market_price: number; spot: number; strike: number; dte_days: number; option_type: 'CE' | 'PE' }) =>
      runTool('IV solve', () => api.solveIV(params)),
    [runTool],
  );

  const simulatePath = useCallback(
    (params: {
      underlying: string;
      spot: number;
      strike: number;
      option_type: 'CE' | 'PE';
      dte_days: number;
      iv: number;
      target_spot: number;
      stop_spot: number;
      quantity: number;
    }) => runTool('Path simulation', () => api.simulateOptionPath(params)),
    [runTool],
  );

  const selectContract = useCallback(
    (params: {
      underlying: 'NIFTY' | 'BANKNIFTY' | 'SENSEX';
      spot_price: number;
      direction: 'LONG_CALL' | 'LONG_PUT';
      expected_move_points?: number | null;
      stop_loss_points?: number;
      target_horizon_hours?: number;
      current_iv?: number;
    }) =>
      runTool('Contract selection', () =>
        api.selectOptimalContract({
          ...params,
          expected_move_points: params.expected_move_points ?? undefined,
        }),
      ),
    [runTool],
  );

  const projectExpectedMove = useCallback(
    (params: {
      underlying: string;
      spot: number;
      direction: 'BULLISH' | 'BEARISH';
      horizon?: string;
      current_iv?: number;
      atr?: number | null;
    }) =>
      runTool('Expected-move projection', () =>
        api.projectExpectedMove({
          ...params,
          horizon: params.horizon ?? 'INTRADAY',
          current_iv: params.current_iv ?? 0.15,
          atr: params.atr ?? undefined,
        }),
      ),
    [runTool],
  );

  const buildTemplate = useCallback(
    async (templateId: string): Promise<ToolOutcome & { strategy: BuiltTemplateStrategy | null }> => {
      try {
        const res = await api.buildStrategyTemplate(templateId, instrumentRef.current);
        if (res?.error) {
          return { ok: false, message: res.error, value: null, strategy: null };
        }
        return {
          ok: true,
          message: `Built ${templateId} off live spot ${res.data.spot_price}.`,
          value: toRecord(res.data),
          strategy: res.data ?? null,
        };
      } catch (err) {
        return { ok: false, message: errorMessage(err, 'Template build failed'), value: null, strategy: null };
      }
    },
    [],
  );

  const calcPayoff = useCallback(
    (payload: { underlying: string; spot_price: number; expiry?: string | null; legs: StrategyLegInput[] }) =>
      runTool('Payoff calculation', () => api.calculateStrategyPayoff(payload)),
    [runTool],
  );

  const synthesizeResearch = useCallback(
    async (params: { horizon: string; direction: 'BULLISH' | 'BEARISH' }): Promise<ToolOutcome> => {
      try {
        const value = await api.synthesizeFinancialResearch({
          underlying: instrumentRef.current,
          horizon: params.horizon,
          direction: params.direction,
        });
        setResearch(toRecord(value));
        return { ok: true, message: 'Fresh research synthesized.', value: toRecord(value) };
      } catch (err) {
        return { ok: false, message: errorMessage(err, 'Research synthesis failed'), value: null };
      }
    },
    [],
  );

  return {
    instrument,
    chain,
    analytics,
    analyticsSource,
    maxPain,
    flow,
    regimeOverview,
    regimeSource,
    pivots,
    indicators,
    vix,
    futuresOverview,
    futuresTerm,
    futuresBuildup,
    futuresRollover,
    templates,
    scanner,
    portfolioGreeks,
    research,
    expiries,
    expiry,
    setExpiry,
    loading,
    refreshing,
    error,
    updatedAt,
    refresh,
    calcGreeks,
    solveIv,
    simulatePath,
    selectContract,
    projectExpectedMove,
    buildTemplate,
    calcPayoff,
    synthesizeResearch,
  };
}
