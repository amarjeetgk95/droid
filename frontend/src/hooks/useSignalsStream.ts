'use client';

import { useEffect, useRef, useState } from 'react';
import { API_BASE } from '@/lib/api';

export type SignalsStreamEvent = {
  type: string;
  data: unknown;
  at: Date;
};

type UseSignalsStreamArgs = {
  onEvent?: (evt: string, data: unknown) => void;
};

const MAX_BACKOFF_MS = 30_000;

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

/**
 * Subscribe to GET /api/v1/signals/stream (`event: signal_event` SSE).
 * Never throws — backend-down just yields connected=false with backoff retries.
 */
export function useSignalsStream({ onEvent }: UseSignalsStreamArgs = {}) {
  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<SignalsStreamEvent | null>(null);

  const onEventRef = useRef<UseSignalsStreamArgs['onEvent']>(onEvent);
  onEventRef.current = onEvent;
  const backoffRef = useRef(1000);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof EventSource === 'undefined') return;

    let es: EventSource | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let closed = false;

    const clearRetry = () => {
      if (retryTimer) {
        clearTimeout(retryTimer);
        retryTimer = null;
      }
    };

    const scheduleReconnect = () => {
      if (closed || retryTimer) return;
      // Don't churn while the tab is hidden — visibility handler reconnects.
      if (typeof document !== 'undefined' && document.hidden) {
        setConnected(false);
        return;
      }
      const delay = Math.min(MAX_BACKOFF_MS, backoffRef.current);
      backoffRef.current = Math.min(MAX_BACKOFF_MS, backoffRef.current * 2);
      retryTimer = setTimeout(() => {
        retryTimer = null;
        if (!closed) connect();
      }, delay);
    };

    const handleRaw = (raw: string) => {
      const parsed = parsePayload(raw);
      if (!parsed) return;
      backoffRef.current = 1000;
      setLastEvent({ type: parsed.event, data: parsed.data, at: new Date() });
      try {
        onEventRef.current?.(parsed.event, parsed.data);
      } catch {
        // Consumer errors must never kill the stream.
      }
    };

    const connect = () => {
      if (closed) return;
      if (typeof document !== 'undefined' && document.hidden) {
        setConnected(false);
        return;
      }
      try {
        es?.close();
      } catch {
        // ignore
      }
      let source: EventSource;
      try {
        source = new EventSource(`${API_BASE}/api/v1/signals/stream`);
      } catch {
        setConnected(false);
        scheduleReconnect();
        return;
      }
      es = source;

      const onOpen = () => {
        backoffRef.current = 1000;
        setConnected(true);
      };
      const onError = () => {
        setConnected(false);
        try {
          source.close();
        } catch {
          // ignore
        }
        if (es === source) es = null;
        scheduleReconnect();
      };
      const onSignalEvent = (e: MessageEvent) => {
        if (typeof e.data === 'string') handleRaw(e.data);
      };

      source.onopen = onOpen;
      source.onerror = onError;
      try {
        source.addEventListener('signal_event', onSignalEvent as EventListener);
      } catch {
        // Fall back to onmessage below.
      }
      source.onmessage = (e: MessageEvent) => {
        if (typeof e.data === 'string') handleRaw(e.data);
      };
    };

    const onVisibility = () => {
      if (document.hidden) {
        try {
          es?.close();
        } catch {
          // ignore
        }
        es = null;
        clearRetry();
        setConnected(false);
      } else if (!closed && !es) {
        backoffRef.current = 1000;
        connect();
      }
    };

    connect();
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      closed = true;
      document.removeEventListener('visibilitychange', onVisibility);
      clearRetry();
      try {
        es?.close();
      } catch {
        // ignore
      }
      es = null;
    };
    // Reconnect-from-scratch is driven internally; onEvent flows via ref.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { connected, lastEvent };
}

export default useSignalsStream;
