'use client';

import { useCallback, useRef } from 'react';
import { errorMessage } from '@/lib/errors';
import {
  useExecutionGuard,
  type ExecutionRejectionReason,
  type UseExecutionGuardResult,
} from './useExecutionGuard';

export interface UseAsyncActionOptions {
  /** Message surfaced when a previous run is still in flight and this one is rejected. */
  busyMessage: string;
  /** Fallback when the action throws a value without a usable message. */
  errorFallback?: string;
  /** Share an existing guard (e.g. when the component also checks quote freshness). */
  guard?: UseExecutionGuardResult;
}

export interface UseAsyncActionRunOptions {
  /** Overrides the hook-level `busyMessage` for this run only. */
  busyMessage?: string;
}

export type AsyncActionOutcome<T> =
  | { ok: true; value: T }
  | { ok: false; reason: ExecutionRejectionReason; message: string };

export interface UseAsyncActionResult {
  isPending: boolean;
  lastRejectionReason: ExecutionRejectionReason | null;
  clearError: () => void;
  /**
   * Runs `action` under the re-entrancy guard and never throws for action
   * failures: it resolves `{ ok: false, reason, message }` so the caller can
   * set local error state, rethrow for a ConfirmDialog, or both. A busy
   * rejection carries `reason: 'busy'`; an action failure carries the exact
   * `errorMessage(err, errorFallback)` the cockpit components used to capture
   * in a local `failure` variable.
   *
   * As with the original `guard.execute` pattern, `action` must never resolve
   * to `null` (that value is reserved for the busy signal).
   */
  run: <T>(action: () => Promise<T>, options?: UseAsyncActionRunOptions) => Promise<AsyncActionOutcome<T>>;
}

export function useAsyncAction(options: UseAsyncActionOptions): UseAsyncActionResult {
  const { busyMessage, errorFallback = 'Unexpected error', guard: sharedGuard } = options;
  const internalGuard = useExecutionGuard();
  const guard = sharedGuard ?? internalGuard;
  const execute = guard.execute;
  const failureRef = useRef<string | null>(null);

  const run = useCallback(
    async <T>(action: () => Promise<T>, runOptions?: UseAsyncActionRunOptions): Promise<AsyncActionOutcome<T>> => {
      failureRef.current = null;
      const value = await execute(async () => {
        try {
          return await action();
        } catch (err) {
          failureRef.current = errorMessage(err, errorFallback);
          throw err;
        }
      });

      if (value === null) {
        return {
          ok: false,
          reason: failureRef.current === null ? 'busy' : 'error',
          message: failureRef.current ?? runOptions?.busyMessage ?? busyMessage,
        };
      }
      return { ok: true, value };
    },
    [execute, errorFallback, busyMessage],
  );

  return {
    isPending: guard.isPending,
    lastRejectionReason: guard.lastRejectionReason,
    clearError: guard.clearError,
    run,
  };
}
