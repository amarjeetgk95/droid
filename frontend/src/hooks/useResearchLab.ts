'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { errorMessage } from '@/lib/errors';
import { forecastInstrument } from '@/lib/forecastBoard';
import { toAnnotationSummary, toIndicatorSummary, toPredictionSummary, toSnapshotSummary, type AnnotationSummary, type IndicatorSummary, type PredictionSummary, type SnapshotSummary } from '@/lib/labDesk';
import type { HourForecast } from '@/lib/types';
import { useForecastBoard } from './useForecastBoard';

export type ResearchLabAction = { ok: boolean; message: string };

export function useResearchLab(instrument: string, marketOpen: boolean) {
  const apiInstrument = forecastInstrument(instrument);
  const board = useForecastBoard(apiInstrument, { autoRefreshMs: marketOpen ? 60_000 : null });

  const [predictions, setPredictions] = useState<PredictionSummary[]>([]);
  const [predLoading, setPredLoading] = useState(true);
  const [predError, setPredError] = useState<string | null>(null);
  const [predLimit] = useState(50);

  const [detail, setDetail] = useState<Record<string, unknown> | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<Record<string, unknown> | null>(null);
  const [outcomeError, setOutcomeError] = useState<string | null>(null);
  const [measuring, setMeasuring] = useState(false);

  const [chartState, setChartState] = useState<Record<string, unknown> | null>(null);
  const [chartFeatures, setChartFeatures] = useState<Record<string, unknown> | null>(null);
  const [chartError, setChartError] = useState<string | null>(null);
  const [optionsContext, setOptionsContext] = useState<Record<string, unknown> | null>(null);
  const [optionsError, setOptionsError] = useState<string | null>(null);

  const [health, setHealth] = useState<Awaited<ReturnType<typeof api.getForecastHealth>> | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [config, setConfig] = useState<Awaited<ReturnType<typeof api.getForecastConfig>> | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);

  const [indicators, setIndicators] = useState<IndicatorSummary[]>([]);
  const [indLoading, setIndLoading] = useState(true);
  const [indError, setIndError] = useState<string | null>(null);
  const [indicatorDetail, setIndicatorDetail] = useState<Record<string, unknown> | null>(null);
  const [calcResult, setCalcResult] = useState<Record<string, unknown> | null>(null);
  const [calcBusy, setCalcBusy] = useState(false);

  const [experiment, setExperiment] = useState<Record<string, unknown> | null>(null);
  const [expBusy, setExpBusy] = useState(false);
  const [expError, setExpError] = useState<string | null>(null);

  const [snapshots, setSnapshots] = useState<SnapshotSummary[]>([]);
  const [snapError, setSnapError] = useState<string | null>(null);
  const [annotations, setAnnotations] = useState<AnnotationSummary[]>([]);
  const [annError, setAnnError] = useState<string | null>(null);
  const [mutating, setMutating] = useState(false);
  const [snapshotDetail, setSnapshotDetail] = useState<Record<string, unknown> | null>(null);
  const [snapshotDetailError, setSnapshotDetailError] = useState<string | null>(null);
  const [promoting, setPromoting] = useState(false);
  const [promoteResult, setPromoteResult] = useState<{ promoted: string[]; count: number } | null>(null);

  const reqRef = useRef(0);

  const loadPredictions = useCallback(async () => {
    const id = ++reqRef.current;
    setPredLoading(true);
    try {
      const rows = await api.listResearchPredictions({ instrument: apiInstrument, limit: predLimit });
      if (reqRef.current !== id) return;
      setPredictions((rows ?? []).map((r) => toPredictionSummary(r)).filter((r): r is NonNullable<typeof r> => r !== null));
      setPredError(null);
    } catch (err) {
      if (reqRef.current !== id) return;
      setPredError(errorMessage(err, 'Predictions unavailable'));
    } finally {
      if (reqRef.current === id) setPredLoading(false);
    }
  }, [apiInstrument, predLimit]);

  const loadIndicators = useCallback(async () => {
    setIndLoading(true);
    try {
      const rows = await api.getResearchIndicators();
      setIndicators((rows ?? []).map((r) => toIndicatorSummary(r)).filter((r): r is NonNullable<typeof r> => r !== null));
      setIndError(null);
    } catch (err) {
      setIndError(errorMessage(err, 'Indicators unavailable'));
    } finally {
      setIndLoading(false);
    }
  }, []);

  const loadChart = useCallback(async (timeframe: string) => {
    try {
      const [state, features, ctx] = await Promise.allSettled([
        api.getResearchChartState(apiInstrument, timeframe),
        api.getResearchChartFeatures(apiInstrument, timeframe),
        api.getResearchOptionsContext(apiInstrument),
      ]);
      if (state.status === 'fulfilled') {
        setChartState(state.value as Record<string, unknown>);
        setChartError(null);
      } else {
        setChartError(errorMessage(state.reason, 'Chart state unavailable'));
      }
      if (features.status === 'fulfilled') setChartFeatures(features.value as Record<string, unknown>);
      if (ctx.status === 'fulfilled') {
        setOptionsContext(ctx.value as Record<string, unknown>);
        setOptionsError(null);
      } else {
        setOptionsError(errorMessage(ctx.reason, 'Options context unavailable'));
      }
    } catch (err) {
      setChartError(errorMessage(err, 'Chart readouts unavailable'));
    }
  }, [apiInstrument]);

  const loadMonitoring = useCallback(async () => {
    const [h, c] = await Promise.allSettled([api.getForecastHealth(30), api.getForecastConfig()]);
    if (h.status === 'fulfilled') {
      setHealth(h.value);
      setHealthError(null);
    } else {
      setHealthError(errorMessage(h.reason, 'Forecast health unavailable'));
    }
    if (c.status === 'fulfilled') {
      setConfig(c.value);
      setConfigError(null);
    } else {
      setConfigError(errorMessage(c.reason, 'Forecast config unavailable'));
    }
  }, []);

  const loadSnapshots = useCallback(async () => {
    try {
      const rows = await api.listResearchSnapshots(apiInstrument, 30);
      setSnapshots((rows ?? []).map((r) => toSnapshotSummary(r)).filter((r): r is NonNullable<typeof r> => r !== null));
      setSnapError(null);
    } catch (err) {
      setSnapError(errorMessage(err, 'Snapshots unavailable'));
    }
  }, [apiInstrument]);

  const loadAnnotations = useCallback(async () => {
    try {
      const rows = await api.listResearchAnnotations(apiInstrument);
      setAnnotations((rows ?? []).map((r) => toAnnotationSummary(r)).filter((r): r is NonNullable<typeof r> => r !== null));
      setAnnError(null);
    } catch (err) {
      setAnnError(errorMessage(err, 'Annotations unavailable'));
    }
  }, [apiInstrument]);

  useEffect(() => {
    void loadPredictions();
    void loadIndicators();
    void loadChart('5m');
    void loadMonitoring();
    void loadSnapshots();
    void loadAnnotations();
  }, [loadPredictions, loadIndicators, loadChart, loadMonitoring, loadSnapshots, loadAnnotations]);

  const openPrediction = useCallback(async (id: string) => {
    setDetailId(id);
    setDetailLoading(true);
    setDetail(null);
    setOutcome(null);
    setDetailError(null);
    setOutcomeError(null);
    const [d, o] = await Promise.allSettled([api.getResearchPrediction(id), api.getResearchPredictionOutcome(id)]);
    if (d.status === 'fulfilled') setDetail(d.value as unknown as Record<string, unknown>);
    else setDetailError(errorMessage(d.reason, 'Prediction detail unavailable'));
    if (o.status === 'fulfilled') setOutcome(o.value as unknown as Record<string, unknown>);
    else setOutcomeError(errorMessage(o.reason, 'No outcome recorded yet'));
    setDetailLoading(false);
  }, []);

  const measurePrediction = useCallback(async (id: string): Promise<ResearchLabAction> => {
    setMeasuring(true);
    try {
      const res = await api.measureResearchPrediction(id);
      setOutcome(res as unknown as Record<string, unknown>);
      setOutcomeError(null);
      return { ok: true, message: 'Outcome measured and appended.' };
    } catch (err) {
      return { ok: false, message: errorMessage(err, 'Measure failed') };
    } finally {
      setMeasuring(false);
    }
  }, []);

  const createPrediction = useCallback(async (params: Record<string, unknown>): Promise<ResearchLabAction> => {
    setMutating(true);
    try {
      await api.createResearchPrediction(params);
      await loadPredictions();
      return { ok: true, message: 'Prediction recorded (immutable).' };
    } catch (err) {
      return { ok: false, message: errorMessage(err, 'Record failed') };
    } finally {
      setMutating(false);
    }
  }, [loadPredictions]);

  const openIndicator = useCallback(async (id: string) => {
    try {
      const res = await api.getResearchIndicator(id);
      setIndicatorDetail(res as unknown as Record<string, unknown>);
    } catch {
      setIndicatorDetail(null);
    }
  }, []);

  const calculateIndicator = useCallback(async (id: string, params: { instrument: string; timeframe: string; parameters?: Record<string, unknown> }): Promise<ResearchLabAction> => {
    setCalcBusy(true);
    try {
      const res = await api.calculateResearchIndicator(id, params);
      setCalcResult(res as unknown as Record<string, unknown>);
      return { ok: true, message: 'Indicator calculated on demand.' };
    } catch (err) {
      return { ok: false, message: errorMessage(err, 'Calculate failed') };
    } finally {
      setCalcBusy(false);
    }
  }, []);

  const runExperiment = useCallback(async (params: { indicator_id: string; instrument: string; timeframe: string; horizon_candles?: number; stride?: number }): Promise<ResearchLabAction> => {
    setExpBusy(true);
    setExpError(null);
    try {
      const res = await api.runResearchExperiment(params);
      setExperiment(res as unknown as Record<string, unknown>);
      return { ok: true, message: 'Experiment completed.' };
    } catch (err) {
      const msg = errorMessage(err, 'Experiment failed');
      setExpError(msg);
      return { ok: false, message: msg };
    } finally {
      setExpBusy(false);
    }
  }, []);

  const createSnapshot = useCallback(async (params: Record<string, unknown>): Promise<ResearchLabAction> => {
    setMutating(true);
    try {
      await api.createResearchSnapshot(params);
      await loadSnapshots();
      return { ok: true, message: 'Snapshot saved.' };
    } catch (err) {
      return { ok: false, message: errorMessage(err, 'Snapshot failed') };
    } finally {
      setMutating(false);
    }
  }, [loadSnapshots]);

  const createAnnotation = useCallback(async (params: Record<string, unknown>): Promise<ResearchLabAction> => {
    setMutating(true);
    try {
      await api.createResearchAnnotation(params);
      await loadAnnotations();
      return { ok: true, message: 'Annotation recorded.' };
    } catch (err) {
      return { ok: false, message: errorMessage(err, 'Annotation failed') };
    } finally {
      setMutating(false);
    }
  }, [loadAnnotations]);

  const openSnapshot = useCallback(async (id: string) => {
    setSnapshotDetailError(null);
    try {
      const res = await api.getResearchSnapshot(id);
      setSnapshotDetail(res as unknown as Record<string, unknown>);
    } catch {
      setSnapshotDetail(null);
      setSnapshotDetailError('Snapshot unavailable');
    }
  }, []);

  const promoteChallenger = useCallback(async (prefixes?: string[]): Promise<ResearchLabAction> => {
    setPromoting(true);
    setPromoteResult(null);
    try {
      const res = await api.promoteChallenger(prefixes);
      setPromoteResult(res);
      return { ok: true, message: `Promoted ${res.count} artifact(s) to champion.` };
    } catch (err) {
      return { ok: false, message: errorMessage(err, 'Promotion failed') };
    } finally {
      setPromoting(false);
    }
  }, []);

  const refreshAll = useCallback(async () => {
    await Promise.all([loadPredictions(), loadIndicators(), loadMonitoring(), loadSnapshots(), loadAnnotations()]);
    await board.refresh({ record: false });
  }, [loadPredictions, loadIndicators, loadMonitoring, loadSnapshots, loadAnnotations, board]);

  return {
    apiInstrument,
    board: board as { forecasts: Partial<Record<string, HourForecast>>; errors: Partial<Record<string, string>>; loading: boolean; refreshing: boolean; updatedAt: number | null; refresh: (o?: { record?: boolean }) => Promise<void> },
    predictions, predLoading, predError, loadPredictions,
    detail, detailId, detailLoading, detailError, outcome, outcomeError, measuring, openPrediction, measurePrediction, createPrediction,
    chartState, chartFeatures, chartError, optionsContext, optionsError, loadChart,
    health, healthError, config, configError,
    indicators, indLoading, indError, indicatorDetail, calcResult, calcBusy, openIndicator, calculateIndicator,
    experiment, expBusy, expError, runExperiment,
    snapshots, snapError, snapshotDetail, snapshotDetailError, openSnapshot,
    annotations, annError, mutating, createSnapshot, createAnnotation,
    promoting, promoteChallenger, promoteResult,
    refreshAll,
  };
}
