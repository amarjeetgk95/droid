'use client';

import { useState, useEffect, useRef } from 'react';
import type { TickEvent } from '@/lib/types';
import { API_BASE, api } from '@/lib/api';


export type StreamConnectionState = 'CONNECTING' | 'CONNECTED' | 'DISCONNECTED' | 'RECONNECTING';

/** A tick plus the local time it was received — used for freshness checks. */
export type TimestampedTick = TickEvent & { received_at: number };

const IDLE_TIMEOUT_MS = 30_000;   // force reconnect if no message for 30s
const IDLE_CHECK_MS = 5_000;      // idle watchdog interval
const MIN_BACKOFF_MS = 1_000;
const MAX_BACKOFF_MS = 30_000;
/** No ticks for this long => feed marked stale so UI stops claiming LIVE. */
const FEED_STALE_MS = 20_000;

export function useMarketStream() {
  const [streamState, setStreamState] = useState<StreamConnectionState>('CONNECTING');
  const [latestTicks, setLatestTicks] = useState<Record<string, TimestampedTick>>({});
  const [reconnectCount, setReconnectCount] = useState<number>(0);
  const [lastTickAt, setLastTickAt] = useState<Date | null>(null);
  const [ticksFresh, setTicksFresh] = useState<boolean>(false);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const backoffRef = useRef<number>(MIN_BACKOFF_MS);
  const lastMessageAtRef = useRef<number>(0);
    const staleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    // Guards async ticket minting against unmount / newer connections: only
    // the latest connection sequence may open a socket.
    const connectionSeqRef = useRef(0);

    /**
     * Mint a single-use WS ticket for header-less transports.
     * Returns null when tickets are unavailable (auth disabled backend answers
     * 401/404, or the fetch fails) — the caller then falls back to the
     * pre-ticket ticketless URL, which the backend still accepts when
     * AUTH_REQUIRED=false.
     */
    const mintStreamTicket = async (): Promise<string | null> => {
      try {
        const base = API_BASE.replace(/\/+$/, '');
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        const token = api.getToken();
        if (token) headers.Authorization = `Bearer ${token}`;
        const res = await fetch(`${base}/api/v1/stream/ticket`, {
          method: 'POST',
          headers,
        });
        if (!res.ok) return null;
        const body = (await res.json().catch(() => null)) as { ticket?: unknown } | null;
        return typeof body?.ticket === 'string' && body.ticket ? body.ticket : null;
      } catch {
        return null;
      }
    };

  useEffect(() => {
    if (typeof window === 'undefined') return;

    let isUnmounted = false;
    // Exactly one visibility listener for the lifetime of the effect — never
    // overwritten, never added twice.
    let visibilityHandler: (() => void) | null = null;

    const clearReconnectTimeout = () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
    };

    const removeVisibilityHandler = () => {
      if (visibilityHandler) {
        document.removeEventListener('visibilitychange', visibilityHandler);
        visibilityHandler = null;
      }
    };

    const addVisibilityHandler = () => {
      if (visibilityHandler || isUnmounted) return;
      visibilityHandler = () => {
        if (isUnmounted || document.hidden) return;
        removeVisibilityHandler();
        setStreamState('RECONNECTING');
        createConnection();
      };
      document.addEventListener('visibilitychange', visibilityHandler);
    };

    const closeCurrentSocket = () => {
      const ws = wsRef.current;
      wsRef.current = null;
      if (!ws) return;
      // Detach handlers first so the intentional close cannot re-trigger a
      // reconnect or clobber a newer socket's state.
      ws.onopen = null;
      ws.onmessage = null;
      ws.onerror = null;
      ws.onclose = null;
      try {
        if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
          ws.close();
        }
      } catch {
        // ignore
      }
    };

    const nextBackoffDelay = () => {
      const base = Math.min(MAX_BACKOFF_MS, backoffRef.current);
      // ±20% jitter so many clients do not reconnect in lockstep.
      const jitter = base * 0.2 * (Math.random() * 2 - 1);
      backoffRef.current = Math.min(MAX_BACKOFF_MS, base * 2);
      return Math.max(MIN_BACKOFF_MS, Math.min(MAX_BACKOFF_MS, base + jitter));
    };

    const scheduleReconnect = () => {
      if (isUnmounted) return;
      // A pending timer or parked visibility handler already owns the retry.
      if (reconnectTimeoutRef.current || visibilityHandler) return;
      // Pause reconnect churn while the tab is hidden — the single visibility
      // handler resumes the connection when the tab becomes visible again.
      if (document.hidden) {
        addVisibilityHandler();
        setStreamState('DISCONNECTED');
        return;
      }
      setStreamState('RECONNECTING');
      setReconnectCount((prev) => prev + 1);
      const delay = nextBackoffDelay();
      reconnectTimeoutRef.current = setTimeout(() => {
        reconnectTimeoutRef.current = null;
        createConnection();
      }, delay);
    };

    const createConnection = () => {
      if (isUnmounted) return;
      clearReconnectTimeout();
      // Background tabs do not need a live socket — park behind visibility.
      if (document.hidden) {
        setStreamState('DISCONNECTED');
        addVisibilityHandler();
        return;
      }
      removeVisibilityHandler();
      // Never leak the previous socket: close it *before* opening a new one.
      closeCurrentSocket();

      const seq = ++connectionSeqRef.current;
      void (async () => {
        if (isUnmounted || connectionSeqRef.current !== seq) return;
        // Single-use ticket per connection: browsers cannot set an
        // Authorization header on a WS upgrade, so the backend mints a
        // 60s ticket via POST /api/v1/stream/ticket. Null keeps the
        // pre-ticket behavior (accepted when AUTH_REQUIRED=false).
        const ticket = await mintStreamTicket();
        if (isUnmounted || connectionSeqRef.current !== seq) return;

        const apiUrl = API_BASE.replace(/\/+$/, '');
        const wsProtocol = apiUrl.startsWith('https') ? 'wss' : 'ws';
        const wsHost = apiUrl.replace(/^https?:\/\//, '');
        const wsUrl = ticket
          ? `${wsProtocol}://${wsHost}/api/v1/ws/market-feed?ticket=${encodeURIComponent(ticket)}`
          : `${wsProtocol}://${wsHost}/api/v1/ws/market-feed`;

        try {
          const ws = new WebSocket(wsUrl);
          wsRef.current = ws;

        ws.onopen = () => {
          if (isUnmounted || wsRef.current !== ws) return;
          setStreamState('CONNECTED');
          backoffRef.current = MIN_BACKOFF_MS;
          lastMessageAtRef.current = Date.now();
        };

        ws.onmessage = (event) => {
          if (isUnmounted || wsRef.current !== ws) return;
          // Any message proves the socket is alive (idle watchdog), but only
          // real MARKET_TICKS prove market data is flowing — heartbeats must
          // NOT mark the feed fresh, otherwise the UI claims LIVE with 0.00 data.
          lastMessageAtRef.current = Date.now();
          try {
            const payload = JSON.parse(event.data);
            if (payload.type === 'BROKER_AUTHENTICATED') {
              window.dispatchEvent(
                new CustomEvent('broker:authenticated', {
                  detail: payload,
                }),
              );
            }

            if (payload.type === 'MARKET_TICKS' && Array.isArray(payload.ticks)) {
              if (payload.ticks.length > 0) {
                if (staleTimerRef.current) clearTimeout(staleTimerRef.current);
                staleTimerRef.current = setTimeout(() => {
                  staleTimerRef.current = null;
                  if (!isUnmounted) {
                    setTicksFresh(false);
                    setLatestTicks({});
                  }
                }, FEED_STALE_MS);
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
            }
            // HEARTBEAT / PONG / CONNECTION_ESTABLISHED: keep-alive only.
          } catch {
            // Ignore parse errors
          }
        };

        ws.onerror = () => {
          if (isUnmounted || wsRef.current !== ws) return;
          setStreamState('DISCONNECTED');
          // Some transports fire onerror without onclose — force the close so
          // the reconnect path is guaranteed to run exactly once.
          try {
            ws.close();
          } catch {
            // ignore
          }
        };

        ws.onclose = () => {
          if (wsRef.current === ws) wsRef.current = null;
          if (isUnmounted) return;
          // Close code 4401 = ticket rejected (expired/single-use consumed):
          // scheduleReconnect mints a fresh ticket, so retry is correct.
          scheduleReconnect();
        };
        } catch {
          if (!isUnmounted) scheduleReconnect();
        }
      })();
    };

    createConnection();

    // Keepalive ping interval — send PING every 10s to keep connection alive
    const pingInterval = setInterval(() => {
      const ws = wsRef.current;
      if (ws && ws.readyState === WebSocket.OPEN) {
        try {
          ws.send(JSON.stringify({ action: 'PING' }));
        } catch {
          // Ignore send errors
        }
      }
    }, 10_000);

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
      clearInterval(pingInterval);
      clearInterval(idleInterval);
      clearReconnectTimeout();
      if (staleTimerRef.current) {
        clearTimeout(staleTimerRef.current);
        staleTimerRef.current = null;
      }
      removeVisibilityHandler();
      closeCurrentSocket();
    };
  }, []);

  return { streamState, latestTicks, reconnectCount, lastTickAt, ticksFresh };
}
