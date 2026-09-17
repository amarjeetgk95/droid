'use client';

import { useEffect, useRef, useSyncExternalStore } from 'react';
import { API_BASE } from '@/lib/api';

export type SignalsStreamEvent = {
  type: string;
  data: unknown;
  at: Date;
};

type UseSignalsStreamArgs = {
  onEvent?: (evt: string, data: unknown) => void;
};

type StreamSnapshot = {
  connected: boolean;
  lastEvent: SignalsStreamEvent | null;
};

type StreamListener = (evt: string, data: unknown) => void;

const MAX_BACKOFF_MS = 30_000;
const MIN_BACKOFF_MS = 1_000;
const IDLE_TIMEOUT_MS = 20_000;
const IDLE_CHECK_MS = 5_000;

const SERVER_SNAPSHOT: StreamSnapshot = { connected: false, lastEvent: null };

// ---------------------------------------------------------------------------
// Module-level shared connection.
//
// GET /api/v1/signals/stream is a process-wide backend resource: opening one
// EventSource per hook mount (provider + every consumer) multiplies load and
// duplicates every message. This store keeps exactly one EventSource for the
// whole tab, shared by all `useSignalsStream` mounts via refcount, and fans
// events out to each listener once.
// ---------------------------------------------------------------------------

let snapshot: StreamSnapshot = SERVER_SNAPSHOT;
let refCount = 0;
let started = false;
let es: EventSource | null = null;
let retryTimer: ReturnType<typeof setTimeout> | null = null;
let idleTimer: ReturnType<typeof setInterval> | null = null;
let backoffMs = MIN_BACKOFF_MS;
let lastMessageAt = 0;

const subscribers = new Set<() => void>();
const eventListeners = new Set<StreamListener>();

function parsePayload(raw: string): { event: string; data: unknown } | null {
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      const obj = parsed as Record<string, unknown>;
      // Backend wraps as { event, data, priority }.
      if (typeof obj.event === 'string') return { event: obj.event, data: obj.data };
      // Tolerate bare payloads that already look like an event body.
      if (typeof obj.type === 'string') return { event: obj.type, data: obj.data ?? parsed };
    }
    return null;
  } catch {
    return null;
  }
}

function publish(next: StreamSnapshot) {
  if (snapshot.connected === next.connected && snapshot.lastEvent === next.lastEvent) return;
  snapshot = next;
  for (const notify of [...subscribers]) {
    try {
      notify();
    } catch {
      // A subscriber throwing must not break the other subscribers.
    }
  }
}

function publishConnected(connected: boolean) {
  if (snapshot.connected === connected) return;
  publish({ connected, lastEvent: snapshot.lastEvent });
}

function clearRetry() {
  if (retryTimer) {
    clearTimeout(retryTimer);
    retryTimer = null;
  }
}

function closeSource() {
  const source = es;
  es = null;
  if (!source) return;
  source.onopen = null;
  source.onerror = null;
  source.onmessage = null;
  try {
    source.close();
  } catch {
    // ignore
  }
}

function scheduleReconnect() {
  if (!started || retryTimer) return;
  // Don't churn while the tab is hidden — visibilitychange reconnects.
  if (typeof document !== 'undefined' && document.hidden) {
    publishConnected(false);
    return;
  }
  const delay = Math.max(
    MIN_BACKOFF_MS,
    Math.min(MAX_BACKOFF_MS, backoffMs * (0.8 + Math.random() * 0.4)),
  );
  backoffMs = Math.min(MAX_BACKOFF_MS, backoffMs * 2);
  retryTimer = setTimeout(() => {
    retryTimer = null;
    connect();
  }, delay);
}

function handleRaw(raw: string) {
  lastMessageAt = Date.now();
  const parsed = parsePayload(raw);
  if (!parsed) return;
  backoffMs = MIN_BACKOFF_MS;
  publish({ connected: snapshot.connected, lastEvent: { type: parsed.event, data: parsed.data, at: new Date() } });
  for (const listener of [...eventListeners]) {
    try {
      listener(parsed.event, parsed.data);
    } catch {
      // Consumer errors must never kill the stream.
    }
  }
}

function connect() {
  if (!started || typeof EventSource === 'undefined') return;
  if (typeof document !== 'undefined' && document.hidden) {
    publishConnected(false);
    return;
  }
  closeSource();
  lastMessageAt = Date.now();

  let source: EventSource;
  try {
    source = new EventSource(`${API_BASE}/api/v1/signals/stream`);
  } catch {
    publishConnected(false);
    scheduleReconnect();
    return;
  }
  es = source;

  source.onopen = () => {
    if (es !== source) return;
    backoffMs = MIN_BACKOFF_MS;
    lastMessageAt = Date.now();
    publishConnected(true);
  };
  source.onerror = () => {
    if (es !== source) {
      // A newer source already replaced this one — ignore the stale failure.
      try {
        source.close();
      } catch {
        // ignore
      }
      return;
    }
    es = null;
    try {
      source.close();
    } catch {
      // ignore
    }
    publishConnected(false);
    scheduleReconnect();
  };
  const onSignalEvent = (e: MessageEvent) => {
    if (es === source && typeof e.data === 'string') handleRaw(e.data);
  };

  try {
    source.addEventListener('signal_event', onSignalEvent as EventListener);
  } catch {
    // Fall back to onmessage below.
  }
  source.onmessage = (e: MessageEvent) => {
    if (es === source && typeof e.data === 'string') handleRaw(e.data);
  };
}

function checkIdle() {
  if (!started || typeof EventSource === 'undefined') return;
  if (typeof document !== 'undefined' && document.hidden) return;
  if (es && es.readyState === EventSource.OPEN && Date.now() - lastMessageAt > IDLE_TIMEOUT_MS) {
    closeSource();
    publishConnected(false);
    scheduleReconnect();
  }
}

function handleVisibility() {
  if (!started) return;
  if (document.hidden) {
    closeSource();
    clearRetry();
    publishConnected(false);
    return;
  }
  backoffMs = MIN_BACKOFF_MS;
  clearRetry();
  connect();
}

function start() {
  if (started) return;
  if (typeof window === 'undefined' || typeof EventSource === 'undefined') return;
  started = true;
  backoffMs = MIN_BACKOFF_MS;
  connect();
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', handleVisibility);
  }
  if (idleTimer === null) {
    idleTimer = setInterval(checkIdle, IDLE_CHECK_MS);
  }
}

function stop() {
  if (!started) return;
  started = false;
  clearRetry();
  if (idleTimer !== null) {
    clearInterval(idleTimer);
    idleTimer = null;
  }
  if (typeof document !== 'undefined') {
    document.removeEventListener('visibilitychange', handleVisibility);
  }
  closeSource();
  publish({ connected: false, lastEvent: null });
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

function getSnapshot(): StreamSnapshot {
  return snapshot;
}

function getServerSnapshot(): StreamSnapshot {
  return SERVER_SNAPSHOT;
}

/**
 * Subscribe to GET /api/v1/signals/stream (`event: signal_event` SSE).
 * Never throws — backend-down just yields connected=false with backoff retries.
 *
 * Safe to mount any number of times: all mounts share one module-level
 * EventSource (refcounted), and each callback fires once per event.
 */
export function useSignalsStream({ onEvent }: UseSignalsStreamArgs = {}) {
  const { connected, lastEvent } = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  const onEventRef = useRef<UseSignalsStreamArgs['onEvent']>(onEvent);

  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    const listener: StreamListener = (evt, data) => onEventRef.current?.(evt, data);
    eventListeners.add(listener);
    return () => {
      eventListeners.delete(listener);
    };
  }, []);

  return { connected, lastEvent };
}

export default useSignalsStream;
