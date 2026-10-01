'use client';

import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { PapCalibration, PapGroupedRow, PapPredictionRow, PapResearchSummary } from '@/lib/api/pap';
import { errorMessage } from '@/lib/errors';
import { horizonToMinutes, isAll } from '@/lib/pap';

export type PapResearchQuery = {
  instrument: string; // ALL | NIFTY | BANKNIFTY | SENSEX
  horizon: string; // ALL | 3M | 5M | 10M
  outcome: string; // ALL | correct | incorrect
  prediction: string; // ALL | UP | DOWN | NEUTRAL
  minConfidence: string; // ALL | number string
  limit: number;
};

export const DEFAULT_PAP_QUERY: PapResearchQuery = {
  instrument: 'ALL',
  horizon: 'ALL',
  outcome: 'ALL',
  prediction: 'ALL',
  minConfidence: 'ALL',
  limit: 100,
};

export type PapResearchState = {
  summary: PapResearchSummary | null;
  predictions: PapPredictionRow[];
  predictionCount: number;
  calibration: PapCalibration | null;
  regimes: PapGroupedRow[];
  sessions: PapGroupedRow[];
  ablation: { status: string; reason: string } | null;
  tradability: Record<string, unknown> | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  refresh: () => Promise<void>;
};

function queryParams(q: PapResearchQuery): { instrument?: string; horizon_minutes?: number } {
  return {
    instrument: isAll(q.instrument) ? undefined : q.instrument,
    horizon_minutes: isAll(q.horizon) ? undefined : horizonToMinutes(q.horizon),
  };
}

export function usePapResearch(query: PapResearchQuery): PapResearchState {
  const [summary, setSummary] = useState<PapResearchSummary | null>(null);
  const [predictions, setPredictions] = useState<PapPredictionRow[]>([]);
  const [predictionCount, setPredictionCount] = useState(0);
  const [calibration, setCalibration] = useState<PapCalibration | null>(null);
  const [regimes, setRegimes] = useState<PapGroupedRow[]>([]);
  const [sessions, setSessions] = useState<PapGroupedRow[]>([]);
  const [ablation, setAblation] = useState<{ status: string; reason: string } | null>(null);
  const [tradability, setTradability] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const key = JSON.stringify(query);

  const load = useCallback(
    async (isRefresh: boolean) => {
      const q: PapResearchQuery = JSON.parse(key) as PapResearchQuery;
      if (isRefresh) setRefreshing(true);
      else setLoading(true);
      setError(null);
      try {
        const base = queryParams(q);
        const minConf = isAll(q.minConfidence) ? undefined : Number(q.minConfidence);
        // allSettled: every section degrades independently so one failing
        // slice (or an older backend without these routes) never blanks the
        // whole research page.
        const [sum, preds, cal, reg, ses, abl, tra] = await Promise.allSettled([
          api.getResearchSummary(base),
          api.getResearchPredictions({
            ...base,
            outcome: isAll(q.outcome) ? undefined : q.outcome,
            prediction: isAll(q.prediction) ? undefined : q.prediction,
            min_confidence: Number.isFinite(minConf) ? minConf : undefined,
            limit: q.limit,
          }),
          api.getResearchCalibration(base),
          api.getResearchRegimes(base),
          api.getResearchSessions(base),
          api.getResearchAblation(),
          api.getResearchTradability(),
        ]);
        const failures: string[] = [];
        if (sum.status === 'fulfilled') setSummary(sum.value);
        else failures.push(`summary: ${errorMessage(sum.reason, 'unavailable')}`);
        if (preds.status === 'fulfilled') {
          setPredictions(preds.value.rows);
          setPredictionCount(preds.value.count);
        } else failures.push(`predictions: ${errorMessage(preds.reason, 'unavailable')}`);
        if (cal.status === 'fulfilled') setCalibration(cal.value);
        else failures.push(`calibration: ${errorMessage(cal.reason, 'unavailable')}`);
        if (reg.status === 'fulfilled') setRegimes(reg.value.regimes);
        else failures.push(`regimes: ${errorMessage(reg.reason, 'unavailable')}`);
        if (ses.status === 'fulfilled') setSessions(ses.value.sessions);
        else failures.push(`sessions: ${errorMessage(ses.reason, 'unavailable')}`);
        if (abl.status === 'fulfilled') setAblation(abl.value);
        else failures.push(`ablation: ${errorMessage(abl.reason, 'unavailable')}`);
        if (tra.status === 'fulfilled') setTradability(tra.value);
        else failures.push(`tradability: ${errorMessage(tra.reason, 'unavailable')}`);
        // Every slice failed: the page cannot say anything honest.
        if (failures.length === 7) {
          setError(`PAP research unavailable — ${failures[0]}`);
        } else if (failures.length > 0) {
          setError(`Partial PAP research: ${failures.join('; ')}`);
        } else {
          setError(null);
        }
      } catch (err) {
        setError(errorMessage(err, 'PAP research unavailable'));
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [key],
  );

  useEffect(() => {
    void load(false);
  }, [load]);

  const refresh = useCallback(async () => {
    await load(true);
  }, [load]);

  return {
    summary,
    predictions,
    predictionCount,
    calibration,
    regimes,
    sessions,
    ablation,
    tradability,
    loading,
    refreshing,
    error,
    refresh,
  };
}
