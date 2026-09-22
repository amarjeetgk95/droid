'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { errorMessage } from '@/lib/errors';
import { FORECAST_HORIZONS, type ForecastHorizonId } from '@/lib/forecastBoard';
import { dataFreshness } from '@/lib/signalsNormalize';
import type { HourForecast } from '@/lib/types';
import { useSmartInterval } from './useSmartInterval';

export type ForecastBoardState = {
  forecasts: Partial<Record<ForecastHorizonId, HourForecast>>;
  errors: Partial<Record<ForecastHorizonId, string>>;
  loading: boolean;
  refreshing: boolean;
  updatedAt: number | null;
  /** Age of `updatedAt` in ms. Null when the payload carried no instant. */
  ageMs: number | null;
  /** True when `updatedAt` is missing or older than the staleness window. */
  stale: boolean;
  source: 'rest';
  liveSource: 'rest';
  refresh: (options?: { record?: boolean }) => Promise<void>;
};

export function useForecastBoard(
  instrument: string,
  options: { autoRefreshMs?: number | null } = {},
): ForecastBoardState {
  const { autoRefreshMs = null } = options;
  const [forecasts, setForecasts] = useState<Partial<Record<ForecastHorizonId, HourForecast>>>({});
  const [errors, setErrors] = useState<Partial<Record<ForecastHorizonId, string>>>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const requestIdRef = useRef(0);

  const run = useCallback(
    async (record: boolean, showSpinner: boolean) => {
      const requestId = ++requestIdRef.current;
      if (showSpinner) setRefreshing(true);

      // Primary path: single-snapshot board — one shared anchor_price and
      // generated_at for all five horizons.
      try {
        const board = await api.getTacticalBiasBoard(instrument, record, true);
        if (requestIdRef.current !== requestId) return;
        const nextForecasts: Partial<Record<ForecastHorizonId, HourForecast>> = {};
        const nextErrors: Partial<Record<ForecastHorizonId, string>> = {};
        for (const horizon of FORECAST_HORIZONS) {
          const forecast = board.horizons?.[horizon];
          if (forecast) {
            nextForecasts[horizon] = forecast;
          } else {
            nextErrors[horizon] = 'Forecast unavailable';
          }
        }
        setForecasts(nextForecasts);
        setErrors(nextErrors);
        // Single shared instant — never max() across horizons here. When the
        // backend omits generated_at, keep the last age instead of bumping to
        // Date.now() (a replayed cache must never look freshly generated).
        const boardTs = Date.parse(String(board.generated_at ?? ''));
        if (Number.isFinite(boardTs)) {
          setUpdatedAt(boardTs);
        }
        setLoading(false);
        if (showSpinner) setRefreshing(false);
        return;
      } catch {
        // Board route missing (old backend) or any board failure: fall back
        // to the legacy 5-call path so the UI never regresses. A superseded
        // request must not fall back either.
        if (requestIdRef.current !== requestId) return;
      }

      // Fallback path: legacy 5 parallel single-horizon calls.
      const results = await Promise.allSettled(
        FORECAST_HORIZONS.map((horizon) =>
          api.getTacticalBias(instrument, horizon, record, true),
        ),
      );
      if (requestIdRef.current !== requestId) return;

      const nextForecasts: Partial<Record<ForecastHorizonId, HourForecast>> = {};
      const nextErrors: Partial<Record<ForecastHorizonId, string>> = {};
      const serverTimes: number[] = [];
      results.forEach((result, index) => {
        const horizon = FORECAST_HORIZONS[index];
        if (result.status === 'fulfilled') {
          nextForecasts[horizon] = result.value;
          const ts = Date.parse(String(result.value.generated_at ?? ''));
          if (Number.isFinite(ts)) serverTimes.push(ts);
        } else {
          nextErrors[horizon] = errorMessage(result.reason, 'Forecast unavailable');
        }
      });

      // Only publish rows when at least one horizon succeeded; a total failure
      // keeps the last book (and its age) instead of blanking to an empty map.
      if (serverTimes.length > 0 || Object.keys(nextForecasts).length > 0) {
        setForecasts(nextForecasts);
        setErrors(nextErrors);
      } else {
        setErrors(nextErrors);
      }
      // Prefer the backend's generation time so a replayed cache payload can
      // never look freshly generated under the browser clock. No server time
      // → keep the last age (never Date.now()).
      if (serverTimes.length > 0) {
        setUpdatedAt(Math.max(...serverTimes));
      }
      setLoading(false);
      if (showSpinner) setRefreshing(false);
    },
    [instrument],
  );

  useEffect(() => {
    requestIdRef.current += 1;
    setForecasts({});
    setErrors({});
    setLoading(true);
    setUpdatedAt(null);
    void run(false, false);
  }, [run]);

  const autoTick = useCallback(() => run(false, false), [run]);

  useSmartInterval(autoTick, autoRefreshMs, { fireOnMount: false });

  const refresh = useCallback(
    async (refreshOptions?: { record?: boolean }) => {
      await run(refreshOptions?.record ?? true, true);
    },
    [run],
  );

  const freshness = dataFreshness(updatedAt);

  return {
    forecasts,
    errors,
    loading,
    refreshing,
    updatedAt,
    ageMs: freshness.ageMs,
    stale: freshness.stale,
    source: 'rest',
    liveSource: 'rest',
    refresh,
  };
}
