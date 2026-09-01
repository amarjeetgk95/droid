'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import type { NormalizedCandle } from '@/lib/types';

import { useMarketDataContext } from '@/context/MarketDataContext';

/**
 * Back-compat wrapper — the implementation lives in MarketDataContext so there
 * is exactly ONE polling loop for the whole app (the previous duplicate copy
 * here caused drift and double-fetching).
 */
export function useMarketData() {
  return useMarketDataContext();
}

export function useCandles(symbol: string, timeframe: string) {
  const [candles, setCandles] = useState<NormalizedCandle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    api.getCandles(symbol, timeframe)
      .then(res => {
        if (!isMounted) return;
        setCandles(res.data);
        setError(null);
      })
      .catch(err => {
        if (!isMounted) return;
        setError(err instanceof Error ? err.message : 'Failed to fetch candles');
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [symbol, timeframe]);

  return { candles, loading, error };
}
