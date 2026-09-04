'use client';

import { useEffect, useRef, useState } from 'react';

export type StreamState = 'IDLE' | 'CONNECTING' | 'CONNECTED' | 'RETRYING' | 'DISABLED';

export interface StreamEvent {
  type: string;
  payload: unknown;
  at: number;
}

/**
 * SSE-first live feed for the Signal Centre (/api/v1/signals/stream).
 * - Hidden-tab aware (closes while hidden, resumes on visible)
 * - Bounded exponential backoff (1s → 30s cap) with reset after stable connection
 * - Idle watchdog: reconnects if no message for 45s (half-open TCP guard)
 */
export function useSignalStream(enabled: boolean, onEvent: (e: StreamEvent) => void) {
  const [streamState, setStreamState] = useState<StreamState>(() => (enabled ? 'IDLE' : 'DISABLED'));
  const onEventRef = useRef(onEvent);
  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);
  const backoffRef = useRef(1000);
  const lastMsgRef = useRef(0);
  const stableTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    let source: EventSource | null = null;
    let closed = false;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let watchdog: ReturnType<typeof setInterval> | null = null;

    const base = (process.env.NEXT_PUBLIC_API_URL || '').replace(/\/+$/, '');

    const connect = () => {
      if (closed || document.hidden) {
        setStreamState((s) => (s === 'CONNECTED' ? s : 'RETRYING'));
        retryTimer = setTimeout(connect, 3000);
        return;
      }
      setStreamState((s) => (s === 'CONNECTED' ? s : 'CONNECTING'));
      try {
        source = new EventSource(`${base}/api/v1/signals/stream`);
      } catch {
        scheduleRetry();
        return;
      }
      lastMsgRef.current = Date.now();

      source.addEventListener('connected', () => {
        setStreamState('CONNECTED');
        lastMsgRef.current = Date.now();
        backoffRef.current = 1000;
        // Reset backoff only after a stable window (avoids flapping reset)
        if (stableTimerRef.current) clearTimeout(stableTimerRef.current);
        stableTimerRef.current = setTimeout(() => {
          backoffRef.current = 1000;
        }, 30000);
      });

      const handle = (ev: MessageEvent) => {
        lastMsgRef.current = Date.now();
        try {
          const outer = JSON.parse((ev as MessageEvent).data);
          // Backend wraps: {event, data, priority, timestamp}
          const type = outer?.event || (ev as unknown as { type?: string }).type || 'signal_event';
          onEventRef.current({ type, payload: outer?.data ?? outer, at: Date.now() });
        } catch {
          onEventRef.current({ type: 'signal_event', payload: (ev as MessageEvent).data, at: Date.now() });
        }
      };

      (source as EventSource).addEventListener('signal_event', handle as EventListener);
      (source as EventSource).onmessage = handle as unknown as (ev: MessageEvent) => void;

      (source as EventSource).onerror = () => {
        try {
          source?.close();
        } catch {}
        source = null;
        if (!closed) scheduleRetry();
      };
    };

    const scheduleRetry = () => {
      if (closed) return;
      setStreamState('RETRYING');
      const wait = Math.min(backoffRef.current, 30000);
      backoffRef.current = Math.min(backoffRef.current * 2, 30000);
      retryTimer = setTimeout(connect, wait);
    };

    const onVis = () => {
      if (document.hidden) {
        try {
          source?.close();
        } catch {}
        source = null;
        setStreamState('RETRYING');
      } else if (!source && !closed) {
        connect();
      }
    };

    document.addEventListener('visibilitychange', onVis);
    connect();
    watchdog = setInterval(() => {
      if (closed || document.hidden || !source) return;
      if (Date.now() - lastMsgRef.current > 45000) {
        try {
          source.close();
        } catch {}
        source = null;
        scheduleRetry();
      }
    }, 10000);

    return () => {
      closed = true;
      document.removeEventListener('visibilitychange', onVis);
      if (retryTimer) clearTimeout(retryTimer);
      if (watchdog) clearInterval(watchdog);
      if (stableTimerRef.current) clearTimeout(stableTimerRef.current);
      try {
        source?.close();
      } catch {}
    };
  }, [enabled]);

  return { streamState };
}
