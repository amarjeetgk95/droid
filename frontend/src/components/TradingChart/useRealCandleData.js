'use client';

import { useState, useEffect, useRef } from 'react';
import { api } from '@/lib/api';

// Map Inc timeframe number (minutes) to backend timeframe string
const TF_TO_BACKEND = {
  1: '1m',
  5: '5m',
  15: '15m',
  60: '1h',
  240: '4h',
  1440: '1D',
};

// Map Indian display symbols to backend API symbols (same, but ensure encoding)
function toBackendSymbol(symbol) {
  // Dashboard uses "NIFTY 50", "BANKNIFTY", etc. — backend expects same
  return symbol;
}

/**
 * Real hook with symbol param — use this from DashboardTradingChart wrapper.
 */
export function useRealCandleDataWithSymbol(symbol, tf, live) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const tfRef = useRef(tf);
  const symbolRef = useRef(symbol);
  const loadingRef = useRef(true);
  const pollInFlightRef = useRef(false);

  useEffect(() => {
    tfRef.current = tf;
    symbolRef.current = symbol;
  }, [tf, symbol]);

  useEffect(() => {
    let cancelled = false;
    const backendTf = TF_TO_BACKEND[tf] || '5m';
    const backendSymbol = toBackendSymbol(symbol);

    async function fetchCandles() {
      try {
        loadingRef.current = true;
        setLoading(true);
        setError(null);
        const res = await api.getCandles(backendSymbol, backendTf);
        if (cancelled) return;
        const raw = res.data || [];
        const mapped = raw.map((c) => ({
          t: new Date(c.timestamp).getTime(),
          o: c.open,
          h: c.high,
          l: c.low,
          c: c.close,
          v: c.volume || 0,
        }))
        // Ensure sorted by time ascending and deduped
        mapped.sort((a, b) => a.t - b.t);
        const seen = new Set();
        const deduped = mapped.filter((d) => {
          if (seen.has(d.t)) return false;
          seen.add(d.t);
          return true;
        });
        setData(deduped);
      } catch (e) {
        if (!cancelled) setError(e.message || 'Failed to load candles');
      } finally {
        if (!cancelled) setLoading(false);
        loadingRef.current = false;
      }
    }

    fetchCandles();
    return () => { cancelled = true; };
  }, [symbol, tf]);

  // Live polling: 5s refresh (throttled from 2s) with jitter + hidden-tab pause + single-flight.
  useEffect(() => {
    if (!live) return undefined;
    let timeout = null;
    let cancelled = false;
    const poll = async () => {
      if (typeof document !== 'undefined' && document.hidden) return;
      if (loadingRef.current) return;
      if (pollInFlightRef.current) return;
      const backendTf = TF_TO_BACKEND[tfRef.current] || '5m';
      const backendSymbol = toBackendSymbol(symbolRef.current);
      pollInFlightRef.current = true;
      try {
        const res = await api.getCandles(backendSymbol, backendTf, 2);
        if (cancelled) return;
        const raw = res.data || [];
        if (!raw.length) return;
        const mapped = raw.map((c) => ({
          t: new Date(c.timestamp).getTime(),
          o: c.open,
          h: c.high,
          l: c.low,
          c: c.close,
          v: c.volume || 0,
        }));
        mapped.sort((a, b) => a.t - b.t);
        setData((prev) => {
          if (!prev.length) return mapped;
          const lastPrev = prev[prev.length - 1]?.t;
          const lastNew = mapped[mapped.length - 1]?.t;
          if (lastNew && lastPrev && lastNew > lastPrev) {
            const toAppend = mapped.filter((d) => d.t > lastPrev);
            if (toAppend.length) {
              const next = [...prev, ...toAppend];
              if (next.length > 1500) next.splice(0, next.length - 1500);
              return next;
            }
          }
          if (mapped.length && lastPrev && lastNew && lastNew >= lastPrev) {
            const latest = mapped[mapped.length - 1];
            const next = prev.slice();
            const last = { ...next[next.length - 1] };
            last.c = latest.c;
            last.h = Math.max(last.h, latest.h);
            last.l = Math.min(last.l, latest.l);
            last.v = latest.v;
            next[next.length - 1] = last;
            return next;
          }
          return prev;
        });
      } catch {} finally {
        pollInFlightRef.current = false;
      }
    };
    const schedule = () => {
      const jittered = 5000 * (0.8 + Math.random() * 0.4);
      timeout = setTimeout(async () => {
        await poll();
        if (!cancelled) schedule();
      }, jittered);
    };
    schedule();
    const onVis = () => { if (!document.hidden) void poll(); };
    document.addEventListener('visibilitychange', onVis);
    return () => {
      cancelled = true;
      if (timeout) clearTimeout(timeout);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [symbol, tf, live]);

  return { data, loading, error };
}

export default useRealCandleDataWithSymbol;
