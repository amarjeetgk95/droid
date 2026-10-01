'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import type { FisherMacdStatus, FisherMacdPerformance } from '@/lib/api/fisherMacd';
import { useSmartInterval } from './useSmartInterval';

export interface UseFisherMacdHUDOptions {
  initialSymbol?: string;
  refreshIntervalMs?: number;
}

export function useFisherMacdHUD({
  initialSymbol = 'NIFTY',
  refreshIntervalMs = 5000,
}: UseFisherMacdHUDOptions = {}) {
  const [symbol, setSymbol] = useState(initialSymbol);
  const [status, setStatus] = useState<FisherMacdStatus | null>(null);
  const [performance, setPerformance] = useState<FisherMacdPerformance | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);

  const symbolRef = useRef(symbol);
  symbolRef.current = symbol;

  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const currentSymbol = symbolRef.current;
      const [statusData, perfData] = await Promise.all([
        api.getFisherMacdStatus(currentSymbol),
        api.getFisherMacdPerformance(),
      ]);
      setStatus(statusData);
      setPerformance(perfData);
      setUpdatedAt(statusData.timestamp_ms);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load Fisher-MACD telemetry';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    void fetchData();
  }, [symbol, fetchData]);

  useSmartInterval(
    useCallback(() => {
      if (!autoRefresh) return;
      void fetchData();
    }, [autoRefresh, fetchData]),
    autoRefresh ? refreshIntervalMs : null
  );

  return {
    symbol,
    setSymbol,
    status,
    performance,
    loading,
    error,
    autoRefresh,
    setAutoRefresh,
    updatedAt,
    refresh: fetchData,
  };
}
