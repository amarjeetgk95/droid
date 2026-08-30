'use client';

import { useState, useEffect, useRef } from 'react';
import type { TickEvent } from '@/lib/types';

export type StreamConnectionState = 'CONNECTING' | 'CONNECTED' | 'DISCONNECTED' | 'RECONNECTING';

export function useMarketStream() {
  const [streamState, setStreamState] = useState<StreamConnectionState>('CONNECTING');
  const [latestTicks, setLatestTicks] = useState<Record<string, TickEvent>>({});
  const [reconnectCount, setReconnectCount] = useState<number>(0);
  const [lastTickAt, setLastTickAt] = useState<Date | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const backoffRef = useRef<number>(1000);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    let isUnmounted = false;

    const createConnection = () => {
      if (isUnmounted) return;

      const rawApiUrl = process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com';
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
        };

        ws.onmessage = (event) => {
          if (isUnmounted) return;
          try {
            const payload = JSON.parse(event.data);
            if (payload.type === 'MARKET_TICKS' && Array.isArray(payload.ticks)) {
              setLatestTicks((prev) => {
                const updated = { ...prev };
                payload.ticks.forEach((tick: TickEvent) => {
                  updated[tick.symbol] = tick;
                });
                return updated;
              });
              setLastTickAt(new Date());
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
          setStreamState('RECONNECTING');
          setReconnectCount((prev) => prev + 1);

          const delay = Math.min(30000, backoffRef.current * 1.5 + Math.random() * 500);
          backoffRef.current = delay;

          reconnectTimeoutRef.current = setTimeout(() => {
            createConnection();
          }, delay);
        };
      } catch {
        if (!isUnmounted) {
          reconnectTimeoutRef.current = setTimeout(() => {
            setStreamState('DISCONNECTED');
          }, 0);
        }
      }
    };

    createConnection();

    return () => {
      isUnmounted = true;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  return { streamState, latestTicks, reconnectCount, lastTickAt };
}
