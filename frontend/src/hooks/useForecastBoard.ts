'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { errorMessage } from '@/lib/errors';
import { FORECAST_HORIZONS, type ForecastHorizonId } from '@/lib/forecastBoard';
import type { HourForecast } from '@/lib/types';
import { useSmartInterval } from './useSmartInterval';

export type ForecastBoardState = {
  forecasts: Partial<Record<ForecastHorizonId, HourForecast>>;
  errors: Partial<Record<ForecastHorizonId, string>>;
  loading: boolean;
  refreshing: boolean;
  updatedAt: number | null;
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

      setForecasts(nextForecasts);
      setErrors(nextErrors);
      // Prefer the backend's generation time so a replayed cache payload can
      // never look freshly generated under the browser clock.
      setUpdatedAt(serverTimes.length ? Math.max(...serverTimes) : Date.now());
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

  return { forecasts, errors, loading, refreshing, updatedAt, refresh };
}
