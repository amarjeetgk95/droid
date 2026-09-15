'use client';

import { useEffect, useRef, useCallback, useState } from 'react';

export interface UseSmartIntervalOptions {
  /** Whether to execute immediately on mount. Default: true */
  fireOnMount?: boolean;
  /** Whether to execute immediately when document visibility becomes visible. Default: true */
  fireOnVisible?: boolean;
  /** Whether to pause the interval when document is hidden. Default: true */
  pauseWhenHidden?: boolean;
}

export interface UseSmartIntervalResult {
  refresh: () => Promise<void>;
  active: boolean;
}

/**
 * Reusable timer primitive for periodic polling.
 * Handles:
 * 1. Automatic pause when tab is hidden (document.hidden)
 * 2. Overlap prevention: skips interval tick if previous run is still unresolved
 * 3. Immediate execution on visibility return without rapid burst double-fire (resets next tick to now + intervalMs)
 * 4. Stale closure protection via internal ref
 */
export function useSmartInterval(
  callback: () => Promise<void> | void,
  intervalMs: number | null,
  options: UseSmartIntervalOptions = {}
): UseSmartIntervalResult {
  const {
    fireOnMount = true,
    fireOnVisible = true,
    pauseWhenHidden = true,
  } = options;

  const callbackRef = useRef(callback);
  callbackRef.current = callback;

  const isExecutingRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);
  const [active, setActive] = useState<boolean>(intervalMs !== null && intervalMs > 0);

  const executeOnce = useCallback(async () => {
    if (!mountedRef.current) return;
    if (isExecutingRef.current) return;

    try {
      isExecutingRef.current = true;
      await callbackRef.current();
    } catch {
      // Ignore background fetch error to prevent unhandled rejection crashes
    } finally {
      isExecutingRef.current = false;
    }
  }, []);

  const clearExistingTimer = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    setActive(intervalMs !== null && intervalMs > 0);

    if (intervalMs === null || intervalMs <= 0) {
      clearExistingTimer();
      return () => {
        mountedRef.current = false;
        clearExistingTimer();
      };
    }

    const scheduleNext = (delay: number) => {
      clearExistingTimer();
      timerRef.current = setTimeout(async () => {
        if (!mountedRef.current) return;
        if (pauseWhenHidden && typeof document !== 'undefined' && document.hidden) {
          return;
        }
        await executeOnce();
        if (mountedRef.current) {
          scheduleNext(intervalMs);
        }
      }, delay);
    };

    if (fireOnMount) {
      void executeOnce().then(() => {
        if (mountedRef.current) {
          scheduleNext(intervalMs);
        }
      });
    } else {
      scheduleNext(intervalMs);
    }

    const handleVisibilityChange = () => {
      if (typeof document === 'undefined') return;
      if (document.hidden) {
        if (pauseWhenHidden) {
          clearExistingTimer();
        }
      } else {
        if (fireOnVisible) {
          // Fire immediately on tab restoration and reset the next schedule
          // to prevent back-to-back burst executions.
          void executeOnce().then(() => {
            if (mountedRef.current) {
              scheduleNext(intervalMs);
            }
          });
        } else {
          scheduleNext(intervalMs);
        }
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      mountedRef.current = false;
      clearExistingTimer();
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [intervalMs, fireOnMount, fireOnVisible, pauseWhenHidden, executeOnce, clearExistingTimer]);

  const refresh = useCallback(async () => {
    await executeOnce();
  }, [executeOnce]);

  return { refresh, active };
}
