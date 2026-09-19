'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { errorMessage } from '@/lib/errors';
import { unwrapMlData } from '@/lib/labDesk';
import { useSmartInterval } from './useSmartInterval';

export type MlAction = { ok: boolean; message: string };

async function unwrap<T extends Record<string, unknown>>(p: Promise<{ data: T }>): Promise<T | null> {
  const res = await p;
  return unwrapMlData(res as unknown) as T | null;
}

export function useMlDesk(symbol: string, pollWhileOpen: boolean) {
  const [prediction, setPrediction] = useState<Record<string, unknown> | null>(null);
  const [predError, setPredError] = useState<string | null>(null);
  const [predLoading, setPredLoading] = useState(true);

  const [modelInfo, setModelInfo] = useState<Record<string, unknown> | null>(null);
  const [modelError, setModelError] = useState<string | null>(null);
  const [regime, setRegime] = useState<Record<string, unknown> | null>(null);
  const [regimeError, setRegimeError] = useState<string | null>(null);
  const [challenger, setChallenger] = useState<Record<string, unknown> | null>(null);
  const [champion, setChampion] = useState<Record<string, unknown> | null>(null);
  const [manifestError, setManifestError] = useState<string | null>(null);
  const [shadow, setShadow] = useState<Record<string, unknown> | null>(null);
  const [shadowError, setShadowError] = useState<string | null>(null);
  const [targets, setTargets] = useState<Record<string, unknown> | null>(null);
  const [targetsError, setTargetsError] = useState<string | null>(null);
  const [calibration, setCalibration] = useState<Record<string, unknown> | null>(null);
  const [calError, setCalError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);

  const reqRef = useRef(0);

  const loadPrediction = useCallback(async () => {
    const id = ++reqRef.current;
    try {
      const data = await unwrap(api.getMLPrediction(symbol));
      if (reqRef.current !== id) return;
      setPrediction(data);
      setPredError(null);
      setUpdatedAt(Date.now());
      if (data === null) setPredError('No prediction for this symbol yet');
    } catch (err) {
      if (reqRef.current !== id) return;
      setPredError(errorMessage(err, 'ML prediction unavailable'));
    } finally {
      if (reqRef.current === id) setPredLoading(false);
    }
  }, [symbol]);

  const loadStatic = useCallback(async () => {
    const [mi, rg, ch, cp, sh, tg, cal] = await Promise.allSettled([
      unwrap(api.getMLModelInfo()),
      unwrap(api.getMLCurrentRegime(symbol)),
      unwrap(api.getMLChallengerInfo()),
      unwrap(api.getMLChampionInfo()),
      unwrap(api.getMLShadowGateEval()),
      unwrap(api.getMLTargets()),
      unwrap(api.getMLCalibration(symbol)),
    ]);
    if (mi.status === 'fulfilled') {
      setModelInfo(mi.value);
      setModelError(null);
    } else setModelError(errorMessage(mi.reason, 'Model info unavailable'));
    if (rg.status === 'fulfilled') {
      setRegime(rg.value);
      setRegimeError(null);
    } else setRegimeError(errorMessage(rg.reason, 'Regime unavailable'));
    if (ch.status === 'fulfilled' && cp.status === 'fulfilled') {
      setChallenger(ch.value);
      setChampion(cp.value);
      setManifestError(null);
    } else {
      setManifestError(errorMessage(ch.status === 'rejected' ? ch.reason : cp.status === 'rejected' ? (cp as PromiseRejectedResult).reason : 'Manifests unavailable', 'Manifests unavailable'));
    }
    if (sh.status === 'fulfilled') {
      setShadow(sh.value);
      setShadowError(null);
    } else setShadowError(errorMessage(sh.reason, 'Shadow gate unavailable'));
    if (tg.status === 'fulfilled') {
      setTargets(tg.value);
      setTargetsError(null);
    } else setTargetsError(errorMessage(tg.reason, 'Targets unavailable'));
    if (cal.status === 'fulfilled') {
      setCalibration(cal.value);
      setCalError(null);
    } else setCalError(errorMessage(cal.reason, 'Calibration unavailable'));
  }, [symbol]);

  useEffect(() => {
    setPredLoading(true);
    void loadPrediction();
    void loadStatic();
  }, [loadPrediction, loadStatic]);

  useSmartInterval(
    useCallback(() => loadPrediction(), [loadPrediction]),
    pollWhileOpen ? 60_000 : null,
    { fireOnMount: false },
  );

  const refresh = useCallback(async () => {
    await Promise.all([loadPrediction(), loadStatic()]);
  }, [loadPrediction, loadStatic]);

  const settleOutcome = useCallback(async (params: { prediction_id: string; outcome_spot: number; atr_at_t: number; spot_at_t: number }): Promise<MlAction> => {
    setBusy(true);
    try {
      await api.settleMLOutcome(params);
      await loadPrediction();
      return { ok: true, message: 'Outcome settled (append-only).' };
    } catch (err) {
      return { ok: false, message: errorMessage(err, 'Settle failed') };
    } finally {
      setBusy(false);
    }
  }, [loadPrediction]);

  const runSettlement = useCallback(async (limit = 100): Promise<MlAction> => {
    setBusy(true);
    try {
      await api.runMLSettlement(symbol, limit);
      await loadPrediction();
      return { ok: true, message: 'Auto-settlement pass completed.' };
    } catch (err) {
      return { ok: false, message: errorMessage(err, 'Settlement run failed') };
    } finally {
      setBusy(false);
    }
  }, [symbol, loadPrediction]);

  return {
    prediction, predError, predLoading, updatedAt,
    modelInfo, modelError, regime, regimeError,
    challenger, champion, manifestError,
    shadow, shadowError, targets, targetsError,
    calibration, calError, busy, refresh,
    settleOutcome, runSettlement,
  };
}

export function useMlTrain() {
  const [busy, setBusy] = useState(false);
  const train = useCallback(async (params: { features: number[][]; labels: number[]; horizon_minutes?: number }): Promise<MlAction> => {
    setBusy(true);
    try {
      await api.trainMLEnsemble(params);
      return { ok: true, message: 'Training finished — ensemble artifacts updated.' };
    } catch (err) {
      return { ok: false, message: errorMessage(err, 'Training failed') };
    } finally {
      setBusy(false);
    }
  }, []);
  return { train, busy };
}
