'use client';

import { useState, useRef, useCallback, useEffect } from 'react';

export interface UseExecutionGuardOptions {
  /** Freshness cutoff in seconds for price-sensitive quotes. Default: 15 seconds. */
  defaultStaleThresholdSec?: number;
}

export interface QuoteFreshnessCheck {
  isStale: boolean;
  ageSec: number | null;
}

/** Why the most recent `execute()` call resolved null. */
export type ExecutionRejectionReason = 'busy' | 'error';

export interface UseExecutionGuardResult {
  isPending: boolean;
  lastError: string | null;
  /**
   * Distinguishes why the most recent `execute()` resolved `null`:
   * - `'busy'`: a previous execution was still in flight (nothing ran)
   * - `'error'`: the action threw (`lastError` carries the message)
   * - `null`: no rejection since the last successful start / clearError()
   */
  lastRejectionReason: ExecutionRejectionReason | null;
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
  const [lastRejectionReason, setLastRejectionReason] = useState<ExecutionRejectionReason | null>(null);

  const lockRef = useRef(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const execute = useCallback(async <T,>(action: () => Promise<T>): Promise<T | null> => {
    if (lockRef.current) {
      // Re-entrant call while a previous execution is unresolved. `null` here
      // means "busy" — distinguishable from an action failure below.
      if (mountedRef.current) setLastRejectionReason('busy');
      return null;
    }

    lockRef.current = true;
    if (mountedRef.current) {
      setIsPending(true);
      setLastError(null);
      setLastRejectionReason(null);
    }

    try {
      const result = await action();
      return result;
    } catch (err: unknown) {
      const msg = (err as Error)?.message || 'Execution error';
      if (mountedRef.current) {
        setLastError(msg);
        setLastRejectionReason('error');
      }
      return null;
    } finally {
      lockRef.current = false;
      if (mountedRef.current) setIsPending(false);
    }
  }, []);

  const clearError = useCallback(() => {
    setLastError(null);
    setLastRejectionReason(null);
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
    lastRejectionReason,
    clearError,
    execute,
    checkQuoteFreshness,
  };
}
