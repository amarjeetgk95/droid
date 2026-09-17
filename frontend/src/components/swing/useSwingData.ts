'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { errorMessage } from '@/lib/errors';
import type { SwingSetupDTO, SwingPositionDTO, PortfolioRiskDTO } from '@/lib/api/swing';

export type SwingFilterParams = {
  strategy?: string;
  underlying?: string;
  sector?: string;
  min_score?: number;
  state?: string;
  direction?: string;
  horizon?: string;
};

export type SwingRegime = {
  regime: string;
  confidence: number;
  persistence_bars: number;
  benchmark_symbol: string;
  benchmark_price: number;
  benchmark_change_pct: number;
  ma_alignment_score: number;
  recent_drawdown_pct: number;
  iv_percentile: number;
  iv_regime: string;
  reasons: string[];
};

export type SwingSector = {
  sector: string;
  trend: string;
  relative_strength: number;
  return_20d_pct: number;
  leading_stocks: string[];
};

export type SwingErrorKind = 'load' | 'scan';
export type SwingError = { kind: SwingErrorKind; message: string };

/** Filter chips are debounced so a keystroke in Min Score is one request. */
const FILTER_DEBOUNCE_MS = 300;

/**
 * Data layer for the swing desk.
 *
 * Truth rules enforced here:
 *  - Every refetch is sequenced; a late response from an old filter set can
 *    never overwrite the current one.
 *  - A failed section keeps its previous values but reports the failure
 *    (`setupsError` / `positionsError` / `regimeError`), so the UI can mark
 *    data stale instead of silently showing it as fresh.
 *  - `triggerScan` never rethrows (no unhandled rejection) and always reloads
 *    through the filter path, because `/scan` returns the unfiltered universe
 *    and omits the closed history.
 */
export function useSwingData(filters?: SwingFilterParams) {
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [scanning, setScanning] = useState<boolean>(false);
  const [loaded, setLoaded] = useState<boolean>(false);
  const [stale, setStale] = useState<boolean>(false);

  const [setups, setSetups] = useState<SwingSetupDTO[]>([]);
  const [openPositions, setOpenPositions] = useState<SwingPositionDTO[]>([]);
  const [closedPositions, setClosedPositions] = useState<SwingPositionDTO[]>([]);
  const [portfolioRisk, setPortfolioRisk] = useState<PortfolioRiskDTO | null>(null);
  const [regime, setRegime] = useState<SwingRegime | null>(null);
  const [sectors, setSectors] = useState<SwingSector[]>([]);

  const [setupsError, setSetupsError] = useState<string | null>(null);
  const [positionsError, setPositionsError] = useState<string | null>(null);
  const [regimeError, setRegimeError] = useState<string | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);
  const [errorDismissed, setErrorDismissed] = useState<boolean>(false);

  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null);
  const [positionsUpdatedAt, setPositionsUpdatedAt] = useState<number | null>(null);
  const [regimeUpdatedAt, setRegimeUpdatedAt] = useState<number | null>(null);

  const filtersRef = useRef<SwingFilterParams | undefined>(filters);
  const requestSeqRef = useRef(0);
  const mountedRef = useRef(true);
  const loadedRef = useRef(false);

  useEffect(() => {
    filtersRef.current = filters;
  }, [filters]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const refresh = useCallback(async () => {
    const seq = ++requestSeqRef.current;
    setRefreshing(true);
    const params = filtersRef.current;

    const [setupsRes, positionsRes, regimeRes] = await Promise.allSettled([
      api.getSwingSetups(params),
      api.getSwingPositions(),
      api.getSwingRegime(),
    ]);

    // Superseded by a newer request (filter change / scan): drop the result.
    if (!mountedRef.current || seq !== requestSeqRef.current) return;

    const nextSetupsError =
      setupsRes.status === 'rejected' ? errorMessage(setupsRes.reason, 'setups unavailable') : null;
    const nextPositionsError =
      positionsRes.status === 'rejected'
        ? errorMessage(positionsRes.reason, 'positions unavailable')
        : null;
    const nextRegimeError =
      regimeRes.status === 'rejected' ? errorMessage(regimeRes.reason, 'regime unavailable') : null;

    if (setupsRes.status === 'fulfilled') {
      setSetups(setupsRes.value?.data?.setups ?? []);
      setLastUpdatedAt(Date.now());
    }
    if (positionsRes.status === 'fulfilled') {
      setOpenPositions(positionsRes.value?.data?.open_positions ?? []);
      setClosedPositions(positionsRes.value?.data?.closed_positions ?? []);
      setPortfolioRisk(positionsRes.value?.data?.portfolio_risk ?? null);
      setPositionsUpdatedAt(Date.now());
    }
    if (regimeRes.status === 'fulfilled') {
      setRegime(regimeRes.value?.data?.regime ?? null);
      setSectors(regimeRes.value?.data?.sectors ?? []);
      const scanAt = regimeRes.value?.data?.scan_timestamp_utc;
      setRegimeUpdatedAt(typeof scanAt === 'number' && Number.isFinite(scanAt) ? scanAt : null);
    }

    setSetupsError(nextSetupsError);
    setPositionsError(nextPositionsError);
    setRegimeError(nextRegimeError);

    const failed = Boolean(nextSetupsError || nextPositionsError || nextRegimeError);
    if (failed) {
      setStale(loadedRef.current);
      setErrorDismissed(false);
    } else {
      loadedRef.current = true;
      setLoaded(true);
      setStale(false);
      setScanError(null);
    }

    setRefreshing(false);
    setLoading(false);
  }, []);

  // Debounced filter-driven refetch. Cleanup cancels the pending timer, so a
  // burst of keystrokes collapses into one request for the final filter set.
  useEffect(() => {
    const timer = setTimeout(() => {
      void refresh();
    }, FILTER_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [filters, refresh]);

  const triggerScan = useCallback(
    async (forceRefresh: boolean = false, horizon?: string) => {
      setScanning(true);
      try {
        const res = await api.triggerSwingScan({
          force_refresh: forceRefresh,
          horizon: horizon || filtersRef.current?.horizon,
        });
        if (!mountedRef.current) return null;

        // The scan supersedes any in-flight filtered refresh: invalidate it
        // before applying scan-derived state so a late response cannot
        // overwrite the freshly scanned portfolio.
        requestSeqRef.current += 1;

        if (res?.data) {
          setOpenPositions(res.data.open_positions ?? []);
          setPortfolioRisk(res.data.portfolio_risk ?? null);
          setRegime(res.data.regime ?? null);
          setSectors(res.data.sectors ?? []);
          setPositionsUpdatedAt(Date.now());
          const scanAt = res.data.scan_timestamp_utc;
          if (typeof scanAt === 'number' && Number.isFinite(scanAt)) setRegimeUpdatedAt(scanAt);
        }

        // `/scan` returns the unfiltered universe and omits the closed
        // history. Reload through the filter path so the setups list honours
        // the active chips and auto-closed positions leave the open table.
        await refresh();
        return res?.data ?? null;
      } catch (err) {
        if (mountedRef.current) {
          setScanError(errorMessage(err, 'Scan execution failed.'));
          setErrorDismissed(false);
        }
        return null;
      } finally {
        if (mountedRef.current) setScanning(false);
      }
    },
    [refresh],
  );

  const enterTrade = useCallback(
    async (setupId: string, fillPremium?: number, numLots?: number) => {
      const res = await api.enterSwingPosition({
        setup_id: setupId,
        fill_premium: fillPremium,
        num_lots: numLots,
      });
      await refresh();
      return res?.data;
    },
    [refresh],
  );

  const exitTrade = useCallback(
    async (positionId: string, exitPremium?: number, exitReason: string = 'MANUAL_EXIT') => {
      const res = await api.exitSwingPosition({
        position_id: positionId,
        exit_premium: exitPremium,
        exit_reason: exitReason,
      });
      await refresh();
      return res?.data;
    },
    [refresh],
  );

  const error: SwingError | null = useMemo(() => {
    if (scanError) return { kind: 'scan', message: scanError };
    const parts: string[] = [];
    if (setupsError) parts.push(`Setups: ${setupsError}`);
    if (positionsError) parts.push(`Positions: ${positionsError}`);
    if (regimeError) parts.push(`Regime: ${regimeError}`);
    if (parts.length === 0) return null;
    return { kind: 'load', message: parts.join(' · ') };
  }, [scanError, setupsError, positionsError, regimeError]);

  const dismissError = useCallback(() => setErrorDismissed(true), []);

  return {
    loading: loading && !loaded,
    refreshing,
    scanning,
    loaded,
    stale,
    setups,
    openPositions,
    closedPositions,
    portfolioRisk,
    regime,
    sectors,
    error: errorDismissed ? null : error,
    setupsError,
    positionsError,
    regimeError,
    lastUpdatedAt,
    positionsUpdatedAt,
    regimeUpdatedAt,
    refresh,
    triggerScan,
    enterTrade,
    exitTrade,
    dismissError,
  };
}
