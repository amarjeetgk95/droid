'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import type { PapLive } from '@/lib/api/pap';
import { errorMessage } from '@/lib/errors';
import { dataFreshness, payloadTimestampMs } from '@/lib/signalsNormalize';
import { useSmartInterval } from './useSmartInterval';

export type PapLiveState = {
  live: PapLive | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  updatedAt: number | null;
  ageMs: number | null;
  stale: boolean;
  refresh: () => Promise<void>;
};

/** Live PAP poller: 15s while the market is open, manual otherwise. */
export function usePapLive(instrument: string, pollWhileOpen: boolean): PapLiveState {
  const [live, setLive] = useState<PapLive | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const reqRef = useRef(0);

  const load = useCallback(
    async (isRefresh: boolean) => {
      const id = ++reqRef.current;
      if (isRefresh) setRefreshing(true);
      else setLoading(true);
      try {
        const data = await api.getLive(instrument);
        if (reqRef.current !== id) return;
        setLive(data);
        setError(null);
        // Backend timestamp only — never bump to Date.now() on undated payloads.
        const ts = payloadTimestampMs(data);
        if (ts !== null) setUpdatedAt(ts);
      } catch (err) {
        if (reqRef.current !== id) return;
        setError(errorMessage(err, 'PAP DATA UNAVAILABLE'));
      } finally {
        if (reqRef.current === id) {
          setLoading(false);
          setRefreshing(false);
        }
      }
    },
    [instrument],
  );

  useEffect(() => {
    setLoading(true);
    setLive(null);
    setError(null);
    void load(false);
  }, [load]);

  useSmartInterval(
    useCallback(() => load(true), [load]),
    pollWhileOpen ? 15_000 : null,
    { fireOnMount: false },
  );

  const refresh = useCallback(async () => {
    await load(true);
  }, [load]);

  const freshness = dataFreshness(updatedAt);
  return { live, loading, refreshing, error, updatedAt, ageMs: freshness.ageMs, stale: freshness.stale, refresh };
}
