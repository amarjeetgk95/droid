'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import type {
  PortfolioRiskDTO,
  SwingExitReason,
  SwingPositionDTO,
  SwingRegimeDTO,
  SwingSectorDTO,
  SwingSetupDTO,
  SwingThesisResponse,
} from '@/lib/api/swing';
import { errorMessage } from '@/lib/errors';
import { useSmartInterval } from './useSmartInterval';

export type SwingDeskOutcome = { ok: boolean; message: string };

export type SwingDeskState = {
  regime: SwingRegimeDTO | null;
  sectors: SwingSectorDTO[];
  scanTimestampMs: number | null;
  setups: SwingSetupDTO[];
  openPositions: SwingPositionDTO[];
  closedPositions: SwingPositionDTO[];
  portfolioRisk: PortfolioRiskDTO | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  updatedAt: number | null;
  refresh: () => Promise<void>;
  runScan: () => Promise<SwingDeskOutcome>;
  enterPosition: (setupId: string) => Promise<SwingDeskOutcome>;
  exitPosition: (positionId: string, exitReason?: SwingExitReason) => Promise<SwingDeskOutcome>;
  fetchThesis: (setupId: string) => Promise<SwingThesisResponse | null>;
};

export function useSwingDesk(
  options: { safetyRefreshMs?: number | null } = {},
): SwingDeskState {
  const { safetyRefreshMs = null } = options;
  const [regime, setRegime] = useState<SwingRegimeDTO | null>(null);
  const [sectors, setSectors] = useState<SwingSectorDTO[]>([]);
  const [scanTimestampMs, setScanTimestampMs] = useState<number | null>(null);
  const [setups, setSetups] = useState<SwingSetupDTO[]>([]);
  const [openPositions, setOpenPositions] = useState<SwingPositionDTO[]>([]);
  const [closedPositions, setClosedPositions] = useState<SwingPositionDTO[]>([]);
  const [portfolioRisk, setPortfolioRisk] = useState<PortfolioRiskDTO | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const requestIdRef = useRef(0);
  const equityRef = useRef<number | null>(null);

  const load = useCallback(async (showSpinner: boolean) => {
    const requestId = ++requestIdRef.current;
    if (showSpinner) setRefreshing(true);
    const [regimeResult, setupsResult, positionsResult] = await Promise.allSettled([
      api.getSwingRegime(),
      api.getSwingSetups(),
      api.getSwingPositions(),
    ]);
    if (requestIdRef.current !== requestId) return;

    const failures: string[] = [];

    if (regimeResult.status === 'fulfilled') {
      const payload = regimeResult.value?.data;
      setRegime(payload?.regime ?? null);
      setSectors(payload?.sectors ?? []);
      const ts = payload?.scan_timestamp_utc;
      setScanTimestampMs(typeof ts === 'number' && ts > 0 ? ts * 1000 : null);
      if (regimeResult.value?.error) failures.push(regimeResult.value.error);
    } else {
      failures.push(errorMessage(regimeResult.reason, 'Swing regime unavailable'));
    }

    if (setupsResult.status === 'fulfilled') {
      setSetups(setupsResult.value?.data?.setups ?? []);
      if (setupsResult.value?.error) failures.push(setupsResult.value.error);
    } else {
      failures.push(errorMessage(setupsResult.reason, 'Swing setups unavailable'));
    }

    if (positionsResult.status === 'fulfilled') {
      const payload = positionsResult.value?.data;
      setOpenPositions(payload?.open_positions ?? []);
      setClosedPositions(payload?.closed_positions ?? []);
      setPortfolioRisk(payload?.portfolio_risk ?? null);
      const equity = payload?.portfolio_risk?.total_equity;
      if (typeof equity === 'number' && Number.isFinite(equity) && equity > 0) {
        equityRef.current = equity;
      }
      if (positionsResult.value?.error) failures.push(positionsResult.value.error);
    } else {
      failures.push(errorMessage(positionsResult.reason, 'Swing positions unavailable'));
    }

    setError(failures.length > 0 ? failures[0] : null);
    setUpdatedAt(Date.now());
    setLoading(false);
    if (showSpinner) setRefreshing(false);
  }, []);

  useEffect(() => {
    setLoading(true);
    void load(false);
  }, [load]);

  const refresh = useCallback(async () => {
    await load(true);
  }, [load]);

  useSmartInterval(
    useCallback(() => load(false), [load]),
    safetyRefreshMs,
    { fireOnMount: false },
  );

  const runScan = useCallback(async (): Promise<SwingDeskOutcome> => {
    try {
      const equity = equityRef.current;
      const response = await api.triggerSwingScan({
        force_refresh: true,
        portfolio_equity: equity !== null && equity > 0 ? equity : undefined,
      });
      await load(false);
      const data = response?.data;
      const count = data?.setups?.length ?? 0;
      const duration =
        typeof data?.duration_seconds === 'number' ? ` in ${data.duration_seconds.toFixed(1)}s` : '';
      return { ok: true, message: `Swing scan complete${duration} — ${count} setup(s).` };
    } catch (err) {
      return { ok: false, message: errorMessage(err, 'Swing scan failed') };
    }
  }, [load]);

  const enterPosition = useCallback(
    async (setupId: string): Promise<SwingDeskOutcome> => {
      try {
        const response = await api.enterSwingPosition({ setup_id: setupId });
        await load(false);
        const position = response?.data;
        const lots = position?.num_lots;
        const premium = position?.entry_premium;
        return {
          ok: true,
          message: `Entered ${position?.contract_symbol ?? 'position'}${
            typeof lots === 'number' ? ` · ${lots} lot(s)` : ''
          }${typeof premium === 'number' ? ` @ ₹${premium}` : ''}.`,
        };
      } catch (err) {
        return { ok: false, message: errorMessage(err, 'Entry failed') };
      }
    },
    [load],
  );

  const exitPosition = useCallback(
    async (positionId: string, exitReason: SwingExitReason = 'MANUAL_EXIT'): Promise<SwingDeskOutcome> => {
      try {
        const response = await api.exitSwingPosition({
          position_id: positionId,
          exit_reason: exitReason,
        });
        await load(false);
        const position = response?.data;
        const r = position?.r_multiple;
        const pnl = position?.unrealized_pnl;
        return {
          ok: true,
          message: `Closed ${position?.contract_symbol ?? 'position'}${
            typeof pnl === 'number' ? ` · P&L ₹${pnl}` : ''
          }${typeof r === 'number' ? ` · ${r.toFixed(2)}R` : ''}.`,
        };
      } catch (err) {
        return { ok: false, message: errorMessage(err, 'Exit failed') };
      }
    },
    [load],
  );

  const fetchThesis = useCallback(async (setupId: string): Promise<SwingThesisResponse | null> => {
    try {
      const response = await api.getSwingThesis(setupId);
      return response?.data ?? null;
    } catch {
      return null;
    }
  }, []);

  return {
    regime,
    sectors,
    scanTimestampMs,
    setups,
    openPositions,
    closedPositions,
    portfolioRisk,
    loading,
    refreshing,
    error,
    updatedAt,
    refresh,
    runScan,
    enterPosition,
    exitPosition,
    fetchThesis,
  };
}
