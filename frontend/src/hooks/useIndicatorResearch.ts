'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '@/lib/api';
import type {
  AblationResponse,
  BacktestRequest,
  BacktestResponse,
  CompareRequest,
  CompareResponse,
  DataSelection,
  ExperimentSummary,
  IndicatorCatalog,
  IndicatorMetadata,
  IndicatorSpecInput,
  OptimizeResponse,
  PredictResponse,
  PredictionRequest,
  PreviewRequest,
  PreviewResponse,
  ResearchCatalog,
  ResearchPreset,
  RobustnessResponse,
  RuleSet,
  SelectivityResponse,
  WalkForwardResponse,
} from '@/lib/api/indicatorResearch';
import { CANONICAL_PRESETS } from '@/lib/indicatorPresets';
import {
  STARTING_SETTINGS,
  cloneRules,
  daysAgoIso,
  defaultRulesFor,
  todayIso,
} from '@/lib/indicatorResearch';

export type SettingsState = typeof STARTING_SETTINGS;
export type ResearchTab = 'chart' | 'results' | 'selectivity' | 'robustness' | 'compare' | 'predict' | 'optimize' | 'experiments';

export type SelectionState = {
  instrument: string;
  timeframe: string;
  start: string;
  end: string;
  version: string | null;
  maxBars: number;
};

type AsyncResult<T> = { status: 'idle' | 'loading' | 'ready' | 'error'; data: T | null; error: string | null };

const IDLE = { status: 'idle' as const, data: null, error: null };

/**
 * Dates go over the wire as plain `yyyy-mm-dd` — the backend validates them as
 * pydantic `date`s, which reject datetime strings with a non-zero time
 * component. The time-of-day boundaries are applied backend-side.
 */
function toDataSelection(selection: SelectionState): DataSelection {
  return {
    instrument: selection.instrument,
    timeframe: selection.timeframe,
    start: selection.start || null,
    end: selection.end || null,
    version: selection.version ?? null,
    max_bars: selection.maxBars || null,
  };
}

function paramsFromMetadata(meta: IndicatorMetadata): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const p of meta.parameters) out[p.name] = p.default;
  return out;
}

export function useIndicatorResearch() {
  const [catalog, setCatalog] = useState<AsyncResult<IndicatorCatalog>>(IDLE);
  const [researchCatalog, setResearchCatalog] = useState<AsyncResult<ResearchCatalog>>(IDLE);
  const [isolation, setIsolation] = useState<{ isolated: boolean; guarantees: string[] } | null>(null);

  const [instrument, setInstrument] = useState('NIFTY');
  // Must match the backend's SUPPORTED_TIMEFRAMES values exactly ('5m', not '5').
  const [timeframe, setTimeframe] = useState('5m');
  const [start, setStart] = useState(() => daysAgoIso(30));
  const [end, setEnd] = useState(() => todayIso());
  const [version, setVersion] = useState<string | null>(null);
  const [maxBars, setMaxBars] = useState(20_000);

  const [selected, setSelected] = useState<IndicatorSpecInput[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [rules, setRules] = useState<RuleSet>({ long: null, short: null });
  const [rulesMode, setRulesMode] = useState<'auto' | 'custom'>('auto');
  const [settings, setSettings] = useState<SettingsState>(() => JSON.parse(JSON.stringify(STARTING_SETTINGS)) as SettingsState);

  const [preview, setPreview] = useState<AsyncResult<PreviewResponse>>(IDLE);
  const [backtest, setBacktest] = useState<AsyncResult<BacktestResponse>>(IDLE);
  const [selectivity, setSelectivity] = useState<AsyncResult<SelectivityResponse>>(IDLE);
  const [robustness, setRobustness] = useState<AsyncResult<RobustnessResponse>>(IDLE);
  const [ablation, setAblation] = useState<AsyncResult<AblationResponse>>(IDLE);
  const [presets, setPresets] = useState<AsyncResult<ResearchPreset[]>>({
    status: 'ready',
    data: CANONICAL_PRESETS,
    error: null,
  });
  const [optimize, setOptimize] = useState<AsyncResult<OptimizeResponse>>(IDLE);
  const [walkForward, setWalkForward] = useState<AsyncResult<WalkForwardResponse>>(IDLE);
  const [compare, setCompare] = useState<AsyncResult<CompareResponse>>(IDLE);
  const [predict, setPredict] = useState<AsyncResult<PredictResponse>>(IDLE);
  const [experiments, setExperiments] = useState<AsyncResult<ExperimentSummary[]>>(IDLE);
  const [saveNotice, setSaveNotice] = useState<string | null>(null);

  const requestSeq = useRef(0);

  /* ── Catalogue & Presets ────────────────────────────────────────────────── */

  useEffect(() => {
    let cancelled = false;
    setCatalog((s) => ({ ...s, status: 'loading', error: null }));
    api
      .getIndicatorCatalog()
      .then((data) => !cancelled && setCatalog({ status: 'ready', data, error: null }))
      .catch((err: unknown) =>
        !cancelled && setCatalog({ status: 'error', data: null, error: err instanceof Error ? err.message : 'Failed to load indicators' }),
      );
    api
      .getResearchCatalog()
      .then((data) => {
        if (cancelled) return;
        setResearchCatalog({ status: 'ready', data, error: null });
        // Snap the selection onto a timeframe the backend actually offers
        // (values arrive as '1m'/'5m'/…; free-text guesses would 422).
        setTimeframe((cur) => (data.timeframes?.includes(cur) ? cur : data.timeframes?.[0] ?? cur));
      })
      .catch((err: unknown) =>
        !cancelled &&
        setResearchCatalog({ status: 'error', data: null, error: err instanceof Error ? err.message : 'Failed to load research catalogue' }),
      );
    api
      .getResearchIsolation()
      .then((data) => !cancelled && setIsolation(data))
      .catch(() => undefined);
    api
      .listResearchPresets()
      .then((res) => {
        if (!cancelled && res?.presets?.length) {
          setPresets({ status: 'ready', data: res.presets, error: null });
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  /* Default the selection to the first instrument/timeframe the backend can actually serve. */
  useEffect(() => {
    const entries = researchCatalog.data?.entries ?? [];
    if (entries.length === 0) return;
    const available = entries.find((e) => e.available);
    if (!available) return;
    setInstrument((cur) => (entries.some((e) => e.instrument === cur) ? cur : available.instrument));
    setTimeframe((cur) => (entries.some((e) => e.instrument === instrument && e.timeframe === cur) ? cur : available.timeframe));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [researchCatalog.status]);

  const metaById = useMemo(() => {
    const map = new Map<string, IndicatorMetadata>();
    for (const m of catalog.data?.indicators ?? []) map.set(m.id, m);
    return map;
  }, [catalog.data]);

  const activeSpec = useMemo(
    () => selected.find((s) => s.indicator_id === activeId) ?? selected[0] ?? null,
    [selected, activeId],
  );
  const activeMeta = activeSpec ? metaById.get(activeSpec.indicator_id) ?? null : null;

  /* ── Selection / indicator mutation ──────────────────────────────────── */

  const addIndicator = useCallback(
    (meta: IndicatorMetadata) => {
      setSelected((prev) => {
        if (prev.some((s) => s.indicator_id === meta.id)) return prev;
        return [...prev, { indicator_id: meta.id, params: paramsFromMetadata(meta) }];
      });
      setActiveId((cur) => cur ?? meta.id);
      setRules((cur) => {
        // First indicator: adopt its own defaults. Adding one later must not
        // silently overwrite rules the user already built.
        if (cur.long || cur.short) return cur;
        return defaultRulesFor(meta);
      });
      setRulesMode((cur) => (cur === 'custom' ? cur : 'auto'));
    },
    [],
  );

  const removeIndicator = useCallback((id: string) => {
    setSelected((prev) => prev.filter((s) => s.indicator_id !== id));
    setActiveId((cur) => (cur === id ? null : cur));
  }, []);

  const setParams = useCallback((id: string, params: Record<string, unknown>) => {
    setSelected((prev) => prev.map((s) => (s.indicator_id === id ? { ...s, params } : s)));
  }, []);

  const resetParams = useCallback(
    (id: string) => {
      const meta = metaById.get(id);
      if (!meta) return;
      setParams(id, paramsFromMetadata(meta));
    },
    [metaById, setParams],
  );

  const useIndicatorDefaults = useCallback(() => {
    if (!activeMeta) return;
    setRules(cloneRules(defaultRulesFor(activeMeta)));
    setRulesMode('auto');
  }, [activeMeta]);

  const loadPreset = useCallback((preset: ResearchPreset) => {
    setInstrument(preset.instrument);
    setTimeframe(preset.timeframe);
    setSelected(preset.indicators.map((ind) => ({ indicator_id: ind.indicator_id, params: { ...ind.params } })));
    setActiveId(preset.indicators[0]?.indicator_id ?? null);
    setRules(JSON.parse(JSON.stringify(preset.rules)));
    setRulesMode('custom');
    if (preset.settings) {
      setSettings((prev) => ({
        ...prev,
        ...preset.settings,
        execution: { ...prev.execution, ...(((preset.settings as Record<string, unknown>).execution as Record<string, unknown>) || {}) },
        exits: { ...prev.exits, ...(((preset.settings as Record<string, unknown>).exits as Record<string, unknown>) || {}) },
      }));
    }
  }, []);

  /* ── Request building ────────────────────────────────────────────────── */

  const payload = useCallback(
    (extra?: Partial<BacktestRequest & PreviewRequest>) => ({
      data: toDataSelection({ instrument, timeframe, start, end, version, maxBars }),
      indicators: selected,
      // In auto mode ship the flag rather than nothing: the backend only
      // falls back to an indicator's declared defaults when asked to.
      rules: rulesMode === 'auto' ? { use_indicator_defaults: true } : rules,
      ...extra,
    }),
    [instrument, timeframe, start, end, version, maxBars, selected, rules, rulesMode],
  );

  const canRun = selected.length > 0;

  /**
   * The backend's settings dict accepts only execution/exits/costs;
   * verify_causality, include_trades, include_equity_curve and
   * max_equity_points are top-level request fields (extra="forbid" would
   * 422 otherwise).
   */
  const splitSettings = useCallback((s: SettingsState) => {
    const { execution, exits, costs } = s;
    return {
      settings: { execution, exits, costs },
      verify_causality: s.verify_causality,
      include_trades: s.include_trades,
      include_equity_curve: s.include_equity_curve,
      max_equity_points: s.max_equity_points,
    };
  }, []);

  const runPreview = useCallback(async () => {
    if (!canRun) return;
    const seq = ++requestSeq.current;
    setPreview({ status: 'loading', data: null, error: null });
    try {
      // PreviewRequest is extra="forbid" and has no settings field — sending
      // execution/cost config here would 422.
      const data = await api.previewFeatures(payload({ preview_bars: 600 }));
      if (seq !== requestSeq.current) return;
      setPreview({ status: 'ready', data, error: data.ok ? null : data.error ?? 'Preview failed' });
    } catch (err) {
      if (seq !== requestSeq.current) return;
      setPreview({ status: 'error', data: null, error: err instanceof Error ? err.message : 'Preview failed' });
    }    }, [canRun, payload]);

  const runBacktest = useCallback(async () => {
    if (!canRun) return;
    const seq = ++requestSeq.current;
    setBacktest({ status: 'loading', data: null, error: null });
    try {
      const data = await api.runResearchBacktest({ ...payload(), ...splitSettings(settings) });
      if (seq !== requestSeq.current) return;
      setBacktest({ status: 'ready', data, error: data.ok ? null : data.error ?? 'Backtest failed' });
    } catch (err) {
      if (seq !== requestSeq.current) return;
      setBacktest({ status: 'error', data: null, error: err instanceof Error ? err.message : 'Backtest failed' });
    }
  }, [canRun, payload, settings]);

  const runSelectivity = useCallback(
    async (
      feature: string,
      thresholds: number[],
      operator = '>',
      direction: 'long' | 'short' = 'long',
      forwardHorizon = 5,
    ) => {
      if (!canRun) return;
      setSelectivity({ status: 'loading', data: null, error: null });
      try {
        const data = await api.runResearchSelectivity({
          data: toDataSelection({ instrument, timeframe, start, end, version, maxBars }),
          indicators: selected,
          rules: rulesMode === 'auto' ? { use_indicator_defaults: true } : rules,
          settings: splitSettings(settings).settings,
          feature,
          thresholds,
          operator,
          direction,
          forward_horizon: forwardHorizon,
        });
        setSelectivity({ status: 'ready', data, error: data.ok ? null : data.error ?? 'Selectivity test failed' });
      } catch (err) {
        setSelectivity({ status: 'error', data: null, error: err instanceof Error ? err.message : 'Selectivity test failed' });
      }
    },
    [canRun, instrument, timeframe, start, end, version, maxBars, selected, rules, rulesMode, settings, splitSettings],
  );

  const runRobustness = useCallback(
    async (perturbationPcts?: number[], costMultipliers?: number[]) => {
      if (!canRun) return;
      setRobustness({ status: 'loading', data: null, error: null });
      try {
        const data = await api.runResearchRobustness({
          data: toDataSelection({ instrument, timeframe, start, end, version, maxBars }),
          indicators: selected,
          rules: rulesMode === 'auto' ? { use_indicator_defaults: true } : rules,
          settings: splitSettings(settings).settings,
          perturbation_pcts: perturbationPcts,
          cost_multipliers: costMultipliers,
        });
        setRobustness({ status: 'ready', data, error: data.ok ? null : data.error ?? 'Robustness test failed' });
      } catch (err) {
        setRobustness({ status: 'error', data: null, error: err instanceof Error ? err.message : 'Robustness test failed' });
      }
    },
    [canRun, instrument, timeframe, start, end, version, maxBars, selected, rules, rulesMode, settings, splitSettings],
  );

  const runAblation = useCallback(
    async (objective = 'sharpe_annualized') => {
      if (selected.length < 2) return;
      setAblation({ status: 'loading', data: null, error: null });
      try {
        const data = await api.runResearchAblation({
          data: toDataSelection({ instrument, timeframe, start, end, version, maxBars }),
          indicators: selected,
          rules: rulesMode === 'auto' ? { use_indicator_defaults: true } : rules,
          settings: splitSettings(settings).settings,
          objective,
        });
        setAblation({ status: 'ready', data, error: data.ok ? null : data.error ?? 'Ablation study failed' });
      } catch (err) {
        setAblation({ status: 'error', data: null, error: err instanceof Error ? err.message : 'Ablation study failed' });
      }
    },
    [selected, instrument, timeframe, start, end, version, maxBars, rules, rulesMode, settings, splitSettings],
  );

  const runOptimize = useCallback(
    async (
      objective: string,
      maxCombinations = 200,
      minTrades = 20,
      parameterOverrides?: Record<string, Array<number | string>>,
      searchMode: 'grid' | 'random' = 'grid',
    ) => {
      if (!activeSpec) return;
      setOptimize({ status: 'loading', data: null, error: null });
      try {
        const data = await api.runResearchOptimize({
          data: toDataSelection({ instrument, timeframe, start, end, version, maxBars }),
          indicators: [activeSpec],
          rules: rulesMode === 'auto' ? { use_indicator_defaults: true } : rules,
          settings: splitSettings(settings).settings,
          objective,
          search_mode: searchMode,
          max_combinations: maxCombinations,
          min_trades: minTrades,
          parameter_overrides:
            parameterOverrides && Object.keys(parameterOverrides).length > 0 ? parameterOverrides : undefined,
        });
        setOptimize({ status: 'ready', data, error: data.ok ? null : data.error ?? 'Optimisation failed' });
      } catch (err) {
        setOptimize({ status: 'error', data: null, error: err instanceof Error ? err.message : 'Optimisation failed' });
      }
    },
    [activeSpec, instrument, timeframe, start, end, version, maxBars, rules, rulesMode, settings, splitSettings],
  );

  const runWalkForward = useCallback(
    async (
      objective: string,
      folds = 5,
      purgeBars = 10,
      parameterOverrides?: Record<string, Array<number | string>>,
    ) => {
      if (!activeSpec) return;
      setWalkForward({ status: 'loading', data: null, error: null });
      try {
        const data = await api.runResearchWalkForward({
          data: toDataSelection({ instrument, timeframe, start, end, version, maxBars }),
          indicators: [activeSpec],
          rules: rulesMode === 'auto' ? { use_indicator_defaults: true } : rules,
          settings: splitSettings(settings).settings,
          objective,
          folds,
          purge_bars: purgeBars,
          parameter_overrides:
            parameterOverrides && Object.keys(parameterOverrides).length > 0 ? parameterOverrides : undefined,
        });
        setWalkForward({ status: 'ready', data, error: data.ok ? null : data.error ?? 'Walk-forward failed' });
      } catch (err) {
        setWalkForward({ status: 'error', data: null, error: err instanceof Error ? err.message : 'Walk-forward failed' });
      }
    },
    [activeSpec, instrument, timeframe, start, end, version, maxBars, rules, rulesMode, settings],
  );

  const runCompare = useCallback(
    async (indicatorIds: string[], objective = 'net_profit', useDefaultRules = true) => {
      setCompare({ status: 'loading', data: null, error: null });
      try {
        const request: CompareRequest = {
          data: toDataSelection({ instrument, timeframe, start, end, version, maxBars }),
          indicator_ids: indicatorIds,
          use_default_rules: useDefaultRules,
          settings,
          objective,
        };
        const data = await api.runResearchCompare(request);
        setCompare({ status: 'ready', data, error: data.ok ? null : data.error ?? 'Comparison failed' });
      } catch (err) {
        setCompare({ status: 'error', data: null, error: err instanceof Error ? err.message : 'Comparison failed' });
      }
    },
    [instrument, timeframe, start, end, version, maxBars, settings],
  );

  const runPredict = useCallback(
    async (horizons: number[]) => {
      if (!canRun) return;
      setPredict({ status: 'loading', data: null, error: null });
      try {
        // PredictionRequest is extra="forbid" with no settings field — the
        // study is gross of costs by design, so settings must not be sent.
        const request: PredictionRequest = { ...payload(), horizons };
        const data = await api.runResearchPredict(request);
        setPredict({ status: 'ready', data, error: data.ok ? null : data.error ?? 'Prediction study failed' });
      } catch (err) {
        setPredict({ status: 'error', data: null, error: err instanceof Error ? err.message : 'Prediction study failed' });
      }
    },
    [canRun, payload],
  );

  /* ── Experiment persistence ──────────────────────────────────────────── */

  const refreshExperiments = useCallback(async () => {
    setExperiments((s) => ({ ...s, status: 'loading', error: null }));
    try {
      const res = await api.listResearchExperiments();
      setExperiments({ status: 'ready', data: res.experiments ?? [], error: null });
    } catch (err) {
      setExperiments({ status: 'error', data: null, error: err instanceof Error ? err.message : 'Failed to load experiments' });
    }
  }, []);

  useEffect(() => {
    void refreshExperiments();
  }, [refreshExperiments]);

  const saveExperiment = useCallback(
    async (name: string, notes: string) => {
      if (!activeSpec) return;
      const validation = backtest.data?.validation ?? null;
      const config = {
        data: toDataSelection({ instrument, timeframe, start, end, version, maxBars }),
        indicators: selected,
        rules: rulesMode === 'auto' ? { use_indicator_defaults: true } : rules,
        settings,
      };
      const result = backtest.data;
      try {
        const res = await api.saveResearchExperiment({
          name: name || null,
          notes: notes || null,
          config,
          result_summary: result
            ? {
                trade_count: result.trade_count ?? 0,
                net_profit: result.metrics?.net_profit ?? null,
                total_return_pct: result.metrics?.total_return_pct ?? null,
                win_rate_pct: result.metrics?.win_rate_pct ?? null,
                profit_factor: result.metrics?.profit_factor ?? null,
                max_drawdown_pct: result.metrics?.max_drawdown_pct ?? null,
                total_costs: result.metrics?.total_costs ?? null,
                objective_scope: 'in_sample',
              }
            : { saved_without_backtest: true, objective_scope: 'in_sample' },
          validation: validation ? { no_lookahead: validation.no_lookahead, repaint_free: validation.repaint_free, badge: validation.badge } : {},
          data_provenance: result?.data ? { ...result.data } : {},
        });
        setSaveNotice(`Saved experiment ${res.experiment.id}`);
        await refreshExperiments();
      } catch (err) {
        setSaveNotice(err instanceof Error ? err.message : 'Failed to save experiment');
      }
    },
    [activeSpec, backtest.data, instrument, timeframe, start, end, version, maxBars, selected, rules, rulesMode, settings, refreshExperiments],
  );

  const deleteExperiment = useCallback(
    async (id: string) => {
      try {
        await api.deleteResearchExperiment(id);
        await refreshExperiments();
      } catch (err) {
        setSaveNotice(err instanceof Error ? err.message : 'Failed to delete experiment');
      }
    },
    [refreshExperiments],
  );

  const exportUrl = useCallback((id: string, format: 'json' | 'csv') => api.getResearchExperimentExportUrl(id, format), []);

  return {
    // catalogue
    catalog,
    researchCatalog,
    isolation,
    metaById,
    // selection
    instrument,
    setInstrument,
    timeframe,
    setTimeframe,
    start,
    setStart,
    end,
    setEnd,
    version,
    setVersion,
    maxBars,
    setMaxBars,
    // indicators & rules
    selected,
    activeId: activeSpec?.indicator_id ?? null,
    setActiveId,
    activeSpec,
    activeMeta,
    addIndicator,
    removeIndicator,
    setParams,
    resetParams,
    rules,
    setRules,
    rulesMode,
    setRulesMode,
    useIndicatorDefaults,
    presets,
    loadPreset,
    // settings
    settings,
    setSettings,
    // results
    preview,
    backtest,
    selectivity,
    robustness,
    ablation,
    optimize,
    walkForward,
    compare,
    predict,
    experiments,
    saveNotice,
    setSaveNotice,
    // actions
    canRun,
    runPreview,
    runBacktest,
    runSelectivity,
    runRobustness,
    runAblation,
    runOptimize,
    runWalkForward,
    runCompare,
    runPredict,
    refreshExperiments,
    saveExperiment,
    deleteExperiment,
    exportUrl,
  };
}

export type IndicatorResearchStore = ReturnType<typeof useIndicatorResearch>;
