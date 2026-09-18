'use client';

import { useCallback, useState } from 'react';
import { usePolling } from '@/hooks/usePolling';
import { api } from '@/lib/api';
import { errorMessage } from '@/lib/errors';
import type { AlgoKillSwitchStatus } from '@/lib/api/algo';
import { executeEmergencyKill } from '@/lib/api/algo';

export interface UseKillSwitchOptions {
  pollIntervalMs?: number;
  enabled?: boolean;
}

export function useKillSwitch(options?: UseKillSwitchOptions) {
  const pollIntervalMs = options?.pollIntervalMs ?? 10000;
  const enabled = options?.enabled ?? true;

  const [status, setStatus] = useState<AlgoKillSwitchStatus | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const readStatus = useCallback(async () => {
    try {
      const res = await api.getAlgoKillSwitch();
      if (!res?.data) throw new Error('Kill-switch status payload missing.');
      setStatus({
        is_killed: res.data.is_killed === true,
        kill_level: res.data.kill_level ?? 'UNKNOWN',
        killed_at: res.data.killed_at,
        reason: res.data.reason,
      });
      setLoaded(true);
      setError(null);
    } catch (err) {
      setError(errorMessage(err, 'Unknown kill-switch error'));
    }
  }, []);

  usePolling(readStatus, pollIntervalMs, enabled);

  const triggerKill = useCallback(
    async (
      killLevel = 'FULL_EXECUTION_STOP',
      reason = 'Emergency Kill Switch Triggered'
    ): Promise<AlgoKillSwitchStatus> => {
      const res = await api.triggerAlgoKillSwitch(killLevel, reason);
      const data = res?.data;
      if (!data || data.is_killed !== true) {
        throw new Error(
          `Kill switch was not confirmed by the backend (is_killed: ${String(
            data?.is_killed,
          )}). Engines may still be live.`
        );
      }
      const newStatus: AlgoKillSwitchStatus = {
        is_killed: true,
        kill_level: data.kill_level ?? killLevel,
        killed_at: data.killed_at,
        reason: data.reason,
      };
      setStatus(newStatus);
      setLoaded(true);
      setError(null);
      return newStatus;
    },
    []
  );

  const triggerEmergencyKill = useCallback(
    async (maxRetries = 3, onAttempt?: (attempt: number) => void) => {
      const res = await executeEmergencyKill(maxRetries, onAttempt);
      if (res.success) {
        setStatus((prev) => ({
          is_killed: true,
          kill_level: prev?.kill_level ?? 'HARD_STOP',
          killed_at: new Date().toISOString(),
          reason: prev?.reason ?? 'Emergency Kill Switch Triggered',
        }));
        setLoaded(true);
        setError(null);
      }
      return res;
    },
    []
  );

  return {
    status,
    isKilled: status?.is_killed === true,
    killLevel: status?.kill_level ?? null,
    killedAt: status?.killed_at,
    reason: status?.reason,
    loaded,
    error,
    refresh: readStatus,
    triggerKill,
    executeEmergencyKill: triggerEmergencyKill,
    setStatus,
  };
}

export type UseKillSwitchReturn = ReturnType<typeof useKillSwitch>;
