'use client';

import { useState, useRef, useCallback } from 'react';

export interface UseExecutionGuardOptions {
  /** Freshness cutoff in seconds for price-sensitive quotes. Default: 15 seconds. */
  defaultStaleThresholdSec?: number;
}

export interface QuoteFreshnessCheck {
  isStale: boolean;
  ageSec: number | null;
}

export interface UseExecutionGuardResult {
  isPending: boolean;
  lastError: string | null;
  clearError: () => void;
  /**
   * Safely wraps an order/action execution promise.
   * Prevents rapid concurrent clicks or re-entrant calls while a previous request is unresolved.
   */
  execute: <T>(action: () => Promise<T>) => Promise<T | null>;
  /**
   * Evaluates quote freshness against the cutoff threshold.
   */
  checkQuoteFreshness: (updatedAtMs: number | null, thresholdSec?: number) => QuoteFreshnessCheck;
}

export function useExecutionGuard(options: UseExecutionGuardOptions = {}): UseExecutionGuardResult {
  const { defaultStaleThresholdSec = 15 } = options;
  const [isPending, setIsPending] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);

  const lockRef = useRef(false);

  const execute = useCallback(async <T,>(action: () => Promise<T>): Promise<T | null> => {
    if (lockRef.current) {
      return null;
    }

    try {
      lockRef.current = true;
      setIsPending(true);
      setLastError(null);

      const result = await action();
      return result;
    } catch (err: unknown) {
      const msg = (err as Error)?.message || 'Execution error';
      setLastError(msg);
      return null;
    } finally {
      lockRef.current = false;
      setIsPending(false);
    }
  }, []);

  const clearError = useCallback(() => {
    setLastError(null);
  }, []);

  const checkQuoteFreshness = useCallback(
    (updatedAtMs: number | null, thresholdSec = defaultStaleThresholdSec): QuoteFreshnessCheck => {
      if (!updatedAtMs || !Number.isFinite(updatedAtMs) || updatedAtMs <= 0) {
        return { isStale: true, ageSec: null };
      }
      const ageSec = Math.max(0, Math.floor((Date.now() - updatedAtMs) / 1000));
      return {
        isStale: ageSec > thresholdSec,
        ageSec,
      };
    },
    [defaultStaleThresholdSec]
  );

  return {
    isPending,
    lastError,
    clearError,
    execute,
    checkQuoteFreshness,
  };
}
