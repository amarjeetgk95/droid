'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import {
  vortexDataAgeMs,
  vortexLastCandleMs,
  vortexServerNowMs,
  type VortexMicrostructureHUD,
  type VortexStatus,
} from '@/lib/api/vortex';
import { DEFAULT_STALE_AFTER_MS } from '@/lib/feedState';
import { payloadTimestampMs } from '@/lib/signalsNormalize';
import { useSmartInterval } from './useSmartInterval';

export interface UseVortexHUDOptions {
  initialSymbol?: string;
  refreshIntervalMs?: number;
}

export function useVortexHUD({
  initialSymbol = 'SENSEX',
  refreshIntervalMs = 5000,
}: UseVortexHUDOptions = {}) {
  const [symbol, setSymbol] = useState(initialSymbol);
  const [hud, setHud] = useState<VortexMicrostructureHUD | null>(null);
  const [status, setStatus] = useState<VortexStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  // Backend payload instant (hud.timestamp). Kept across fetch failures —
  // never bumped to Date.now() so STALE age stays honest.
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  // Client clock when the last successful payload arrived — lets server-age
  // keep growing between fetches when a poll fails.
  const [fetchedAtMs, setFetchedAtMs] = useState<number | null>(null);

  const symbolRef = useRef(symbol);
  symbolRef.current = symbol;

  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const currentSymbol = symbolRef.current;
      const [hudData, statusData] = await Promise.all([
        api.getVortexMicrostructure(currentSymbol, 120),
        api.getVortexStatus(),
      ]);
      setHud(hudData);
      setStatus(statusData);
      setFetchedAtMs(Date.now());
      // Prefer the last-candle instant (freshness evidence), then any payload
      // timestamp. On failure (or missing timestamp) keep the last age — a
      // failed poll must never look freshly generated.
      const ts =
        vortexLastCandleMs(hudData) ??
        payloadTimestampMs(hudData) ??
        (typeof hudData.timestamp === 'string' ? Date.parse(hudData.timestamp) : null);
      if (typeof ts === 'number' && Number.isFinite(ts)) {
        setUpdatedAt(ts);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load VORTEX-SNAP microstructure state';
      setError(msg);
      // Keep last updatedAt — a failed fetch must not look fresh.
    } finally {
      setLoading(false);
    }
  }, []);

  // Immediate load on mount and whenever symbol changes
  useEffect(() => {
    setLoading(true);
    void fetchData();
  }, [symbol, fetchData]);

  // Periodic safety refresh via smart interval (pauses when tab is hidden, prevents overlap)
  useSmartInterval(
    useCallback(() => {
      if (autoRefresh) {
        return fetchData();
      }
    }, [autoRefresh, fetchData]),
    autoRefresh ? refreshIntervalMs : null,
    { fireOnMount: false },
  );

  const isSimulated = hud?.data_source?.is_simulated === true;
  const dataSource = hud?.data_source ?? null;
  // Freshness evidence: last candle + backend server clock when present.
  // Server-clock age is frozen at generation, so add client elapsed time since
  // receipt — a failed poll must keep aging, never look permanently fresh.
  const lastCandleTimestampMs = vortexLastCandleMs(hud);
  const serverNowMs = vortexServerNowMs(hud);
  const baseAgeMs = vortexDataAgeMs(hud);
  const clientElapsedMs = fetchedAtMs === null ? 0 : Math.max(0, Date.now() - fetchedAtMs);
  const ageMs = baseAgeMs === null ? null : baseAgeMs + (serverNowMs !== null ? clientElapsedMs : 0);
  // Missing candle time is stale — unknown freshness is never "live".
  const stale = ageMs === null || ageMs > DEFAULT_STALE_AFTER_MS;
  // A simulated or stale feed can never claim LIVE.
  const live = hud !== null && !isSimulated && !stale;
  // Fail-closed gate: SIMULATED or STALE marks must not drive trade actions.
  const tradingDisabled = !live;

  return {
    symbol,
    setSymbol,
    hud,
    status,
    loading,
    error,
    autoRefresh,
    setAutoRefresh,
    refresh: fetchData,
    updatedAt,
    ageMs,
    stale,
    live,
    lastCandleTimestampMs,
    serverNowMs,
    source: 'rest' as const,
    liveSource: 'rest' as const,
    isSimulated,
    tradingDisabled,
    dataSource,
  };
}
