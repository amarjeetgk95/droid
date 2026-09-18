'use client';

import { useContext, useEffect, useMemo, useSyncExternalStore } from 'react';
import { api } from '@/lib/api';
import { toNumber } from '@/lib/coerce';
import { SignalStreamContext } from '@/context/SignalStreamContext';
import { shouldRefreshSignalsOnEvent } from '@/hooks/useActiveSignals';

/**
 * Single app-wide owner of `GET /api/v1/signals/status`.
 *
 * Sidebar, HeaderNotifications and the Signals desk used to run three separate
 * polls (60s / 30s / 15s). This module-level store keeps exactly one interval
 * for the whole tab, fans the snapshot out to every consumer, and refreshes
 * on signal lifecycle SSE events so the count never waits for a full period.
 */

export interface SignalsStatusSnapshot {
  active: number | null;
  confirmed: number | null;
  armed: number | null;
  error: string | null;
  at: number | null;
}

const POLL_MS = 30_000;
/** Collapse a burst of lifecycle SSE events into one status refresh. */
const EVENT_REFRESH_THROTTLE_MS = 1_500;

const SERVER_SNAPSHOT: SignalsStatusSnapshot = {
  active: null,
  confirmed: null,
  armed: null,
  error: null,
  at: null,
};

let snapshot: SignalsStatusSnapshot = SERVER_SNAPSHOT;
let refCount = 0;
let timer: ReturnType<typeof setInterval> | null = null;
let inFlight = false;
let lastEventRefreshAt = 0;

const subscribers = new Set<() => void>();

function publish(next: SignalsStatusSnapshot) {
  snapshot = next;
  for (const notify of [...subscribers]) {
    try {
      notify();
    } catch {
      // A subscriber throwing must not break the others.
    }
  }
}

/** Fetch the shared snapshot. Safe to call from anywhere; in-flight calls collapse. */
export async function refreshSignalsStatus(): Promise<void> {
  if (inFlight) return;
  if (typeof document !== 'undefined' && document.hidden) return;
  inFlight = true;
  try {
    const res = await api.getSignalsStatus();
    publish({
      active: toNumber(res?.active_count),
      confirmed: toNumber(res?.confirmed_count),
      armed: toNumber(res?.armed_count),
      error: null,
      at: Date.now(),
    });
  } catch (err) {
    // Keep the last known counts; expose the failure instead of claiming zero.
    publish({
      ...snapshot,
      error: err instanceof Error ? err.message : 'status unavailable',
    });
  } finally {
    inFlight = false;
  }
}

function handleVisibility() {
  if (!document.hidden) void refreshSignalsStatus();
}

function start() {
  void refreshSignalsStatus();
  if (timer === null) {
    timer = setInterval(() => void refreshSignalsStatus(), POLL_MS);
  }
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', handleVisibility);
  }
}

function stop() {
  if (timer !== null) {
    clearInterval(timer);
    timer = null;
  }
  if (typeof document !== 'undefined') {
    document.removeEventListener('visibilitychange', handleVisibility);
  }
}

function subscribe(notify: () => void): () => void {
  subscribers.add(notify);
  refCount += 1;
  if (refCount === 1) start();
  return () => {
    subscribers.delete(notify);
    refCount = Math.max(0, refCount - 1);
    if (refCount === 0) stop();
  };
}

function getSnapshot(): SignalsStatusSnapshot {
  return snapshot;
}

function getServerSnapshot(): SignalsStatusSnapshot {
  return SERVER_SNAPSHOT;
}

export function useSignalsStatus() {
  const current = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const streamCtx = useContext(SignalStreamContext);
  const lastEvent = streamCtx?.lastEvent ?? null;

  useEffect(() => {
    if (!lastEvent || !shouldRefreshSignalsOnEvent(lastEvent.type)) return;
    const now = Date.now();
    if (now - lastEventRefreshAt < EVENT_REFRESH_THROTTLE_MS) return;
    lastEventRefreshAt = now;
    void refreshSignalsStatus();
  }, [lastEvent]);

  return useMemo(
    () => ({
      active: current.active,
      confirmed: current.confirmed,
      armed: current.armed,
      error: current.error,
      at: current.at,
      refresh: refreshSignalsStatus,
    }),
    [current],
  );
}
