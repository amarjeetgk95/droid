'use client';

import { useSmartInterval } from './useSmartInterval';

/**
 * Executes a callback at specified interval with immediate first run,
 * window visibility awareness, and automatic cleanup.
 *
 * Delegates to `useSmartInterval`, which adds:
 * - overlap prevention (a tick is skipped while the previous run is unresolved)
 * - error capture (a rejected callback can never surface as an unhandled rejection)
 * - drift-corrected scheduling (callback duration is not added to each period)
 * - immediate-but-not-double-fire execution when the tab becomes visible
 */
export function usePolling(
  callback: () => void | Promise<void>,
  intervalMs: number,
  enabled = true
) {
  useSmartInterval(callback, enabled && intervalMs > 0 ? intervalMs : null, {
    fireOnMount: true,
    fireOnVisible: true,
    pauseWhenHidden: true,
  });
}
