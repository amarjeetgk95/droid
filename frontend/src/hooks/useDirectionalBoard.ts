'use client';

import { useCallback, useMemo } from 'react';
import { buildDirectionalConsensus, type DirectionalConsensus } from '@/lib/directionalConsensus';
import { useForecastBoard, type ForecastBoardState } from './useForecastBoard';
import { usePapLive, type PapLiveState } from './usePapLive';
import { useSignalDesk, type SignalDeskState } from './useSignalDesk';

export type DirectionalBoard = {
  /** Tactical forecast board (1m–60m). */
  forecast: ForecastBoardState;
  /** PAP shadow predictions. */
  pap: PapLiveState;
  /** Live signal desk book. */
  signals: SignalDeskState;
  /** Unified directional verdict across the three modules. */
  consensus: DirectionalConsensus;
  /** True while any of the three sources is doing a manual refresh. */
  refreshing: boolean;
  /** Re-run all three sources and record the forecast predictions. */
  refresh: () => Promise<void>;
};

/**
 * Mounts the three modules that used to require separate navigation — the
 * tactical forecast board, the live signal book and the PAP shadow model —
 * and returns their fused directional verdict. All polling lives in the
 * underlying hooks so components never own a timer.
 */
export function useDirectionalBoard(
  apiInstrument: string,
  displayInstrument: string,
  options: { isOpen: boolean },
): DirectionalBoard {
  const { isOpen } = options;

  const forecast = useForecastBoard(apiInstrument, { autoRefreshMs: isOpen ? 60_000 : null });
  const pap = usePapLive(displayInstrument, isOpen);
  const signals = useSignalDesk(
    { instrument: displayInstrument },
    { safetyRefreshMs: isOpen ? 15_000 : null, includeClosed: true },
  );

  const forecasts = forecast.forecasts;
  const papLive = pap.live;
  const signalRows = signals.rows;

  const consensus = useMemo(
    () => buildDirectionalConsensus({ forecasts, pap: papLive, signals: signalRows }).consensus,
    [forecasts, papLive, signalRows],
  );

  const { refresh: refreshForecast } = forecast;
  const { refresh: refreshPap } = pap;
  const { refresh: refreshSignals } = signals;

  const refresh = useCallback(async () => {
    await Promise.all([
      refreshForecast({ record: true }),
      refreshPap(),
      refreshSignals(),
    ]);
  }, [refreshForecast, refreshPap, refreshSignals]);

  return {
    forecast,
    pap,
    signals,
    consensus,
    refreshing: forecast.refreshing || pap.refreshing || signals.refreshing,
    refresh,
  };
}
