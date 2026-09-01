'use client';

import { useState, useEffect, useRef } from 'react';
import type { TickEvent } from '@/lib/types';

export type StreamConnectionState = 'CONNECTING' | 'CONNECTED' | 'DISCONNECTED' | 'RECONNECTING';

/** A tick plus the local time it was received — used for freshness checks. */
export type TimestampedTick = TickEvent & { received_at: number };

const IDLE_TIMEOUT_MS = 30_000;   // force reconnect if no message for 30s
const IDLE_CHECK_MS = 5_000;      // idle watchdog interval
const MAX_BACKOFF_MS = 30_000;
/** No ticks for this long => feed marked stale so UI stops claiming LIVE. */
const FEED_STALE_MS = 30_000;

export function useMarketStream() {
  const [streamState, setStreamState] = useState<StreamConnectionState>('CONNECTING');
  const [latestTicks, setLatestTicks] = useState<Record<string, TimestampedTick>>({});
  const [reconnectCount, setReconnectCount] = useState<number>(0);
  const [lastTickAt, setLastTickAt] = useState<Date | null>(null);
  const [ticksFresh, setTicksFresh] = useState<boolean>(false);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const backoffRef = useRef<number>(1000);
  const lastMessageAtRef = useRef<number>(0);
  const staleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    let isUnmounted = false;
    let visibilityHandler: (() => void) | null = null;

    const clearReconnectTimeout = () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
    };

    const scheduleReconnect = () => {
      if (isUnmounted || reconnectTimeoutRef.current) return;
      // Pause reconnect churn while the tab is hidden — resume on visible.
      if (document.hidden) {
        visibilityHandler = () => {
          if (!document.hidden && !isUnmounted) {
            document.removeEventListener('visibilitychange', visibilityHandler!);
            visibilityHandler = null;
            setStreamState('RECONNECTING');
            createConnection();
          }
        };
        document.addEventListener('visibilitychange', visibilityHandler);
        setStreamState('DISCONNECTED');
        return;
      }
      setStreamState('RECONNECTING');
      setReconnectCount((prev) => prev + 1);
      const delay = Math.min(MAX_BACKOFF_MS, backoffRef.current * 1.5 + Math.random() * 500);
      backoffRef.current = delay;
      reconnectTimeoutRef.current = setTimeout(() => {
        reconnectTimeoutRef.current = null;
        createConnection();
      }, delay);
    };

    const createConnection = () => {
      if (isUnmounted) return;
      clearReconnectTimeout();

      const DEFAULT_API_URL =
        typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
          ? 'http://localhost:8000'
          : 'https://droid-backend-emeq.onrender.com';
      const rawApiUrl = process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_URL;
      const apiUrl = rawApiUrl.replace(/\/+$/, '');
      const wsProtocol = apiUrl.startsWith('https') ? 'wss' : 'ws';
      const wsHost = apiUrl.replace(/^https?:\/\//, '');
      const wsUrl = `${wsProtocol}://${wsHost}/api/v1/ws/market-feed`;

      try {
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          if (isUnmounted) return;
          setStreamState('CONNECTED');
          backoffRef.current = 1000;
          lastMessageAtRef.current = Date.now();
        };

        ws.onmessage = (event) => {
          if (isUnmounted) return;
          lastMessageAtRef.current = Date.now();
          // Any message (incl. non-tick heartbeats) keeps the feed fresh.
          if (staleTimerRef.current) clearTimeout(staleTimerRef.current);
          staleTimerRef.current = setTimeout(() => {
            if (!isUnmounted) {
              setTicksFresh(false);
              setLatestTicks({});
            }
          }, FEED_STALE_MS);
          try {
            const payload = JSON.parse(event.data);
            if (payload.type === 'MARKET_TICKS' && Array.isArray(payload.ticks)) {
              const receivedAt = Date.now();
              setLatestTicks((prev) => {
                const updated = { ...prev };
                payload.ticks.forEach((tick: TickEvent) => {
                  if (tick && tick.symbol) updated[tick.symbol] = { ...tick, received_at: receivedAt };
                });
                return updated;
              });
              setLastTickAt(new Date());
              setTicksFresh(true);
            }
          } catch {
            // Ignore parse errors
          }
        };

        ws.onerror = () => {
          if (isUnmounted) return;
          setStreamState('DISCONNECTED');
        };

        ws.onclose = () => {
          if (isUnmounted) return;
          scheduleReconnect();
        };
      } catch {
        if (!isUnmounted) {
          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectTimeoutRef.current = null;
            scheduleReconnect();
          }, 0);
        }
      }
    };

    createConnection();

    // Idle watchdog — half-open TCP (sleep/resume, proxy timeout) never fires
    // onclose, so force-close dead connections to trigger reconnect.
    const idleInterval = setInterval(() => {
      const ws = wsRef.current;
      if (
        ws &&
        ws.readyState === WebSocket.OPEN &&
        Date.now() - lastMessageAtRef.current > IDLE_TIMEOUT_MS
      ) {
        try { ws.close(); } catch { /* noop */ }
      }
    }, IDLE_CHECK_MS);

    return () => {
      isUnmounted = true;
      clearInterval(idleInterval);
      clearReconnectTimeout();
      if (staleTimerRef.current) clearTimeout(staleTimerRef.current);
      if (visibilityHandler) document.removeEventListener('visibilitychange', visibilityHandler);
      if (wsRef.current) {
        wsRef.current.onclose = null; // prevent reconnect after intentional close
        wsRef.current.close();
      }
    };
  }, []);

  return { streamState, latestTicks, reconnectCount, lastTickAt, ticksFresh };
}
