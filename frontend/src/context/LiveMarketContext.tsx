'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  ReactNode,
} from 'react';
import { api } from '@/lib/api';
import { useMarketStream, StreamConnectionState, TimestampedTick } from '@/hooks/useMarketStream';
import type { IndexCard, DataStatus } from '@/lib/types';

type LiveMarketContextType = {
  /** Tier A live cards (REST snapshot + WS tick merge, throttled). */
  cards: IndexCard[];
  /** Last tick batch per symbol (raw, unthrottled reference). */
  latestTicks: Record<string, TimestampedTick>;
  streamState: StreamConnectionState;
  ticksFresh: boolean;
  loading: boolean;
  lastTickAt: Date | null;
  refetchCards: () => Promise<void>;
};

type StreamHealth = {
  streamState: StreamConnectionState;
  ticksFresh: boolean;
};

const LiveMarketContext = createContext<LiveMarketContextType | null>(null);
/** Stable health-only context — changes only on connect/disconnect/freshness flips. */
const StreamHealthContext = createContext<StreamHealth>({ streamState: 'CONNECTING', ticksFresh: false });

/** Batch WS tick state updates to at most one React render per 100ms. */
const TICK_BATCH_MS = 100;

function deepCardsEqual(a: IndexCard, b: IndexCard): boolean {
  return (
    a.ltp === b.ltp &&
    a.change === b.change &&
    a.change_percent === b.change_percent &&
    a.volume === b.volume &&
    a.status === b.status &&
    a.sparkline === b.sparkline
  );
}

export function LiveMarketProvider({ children }: { children: ReactNode }) {
  const { latestTicks: rawTicks, streamState, ticksFresh, lastTickAt } = useMarketStream();
  const [baseCards, setBaseCards] = useState<IndexCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [batchedTicks, setBatchedTicks] = useState<Record<string, TimestampedTick>>({});
  const mountedRef = useRef(true);
  const batchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingTicksRef = useRef<Record<string, TimestampedTick>>({});

  const fetchCards = useCallback(async () => {
    try {
      // Prefer the batched summary endpoint (single REST call, coordinator-backed).
      // Fall back to the dedicated cards endpoint if the summary is unavailable.
      let cards: IndexCard[] | null = null;
      try {
        const summaryRes = await api.getDashboardSummary();
        if (Array.isArray(summaryRes?.data?.cards) && summaryRes.data.cards.length > 0) {
          cards = summaryRes.data.cards as IndexCard[];
        }
      } catch {
        // fall through to dedicated endpoint
      }
      if (!cards) {
        const res = await api.getIndexCards();
        cards = res.data;
      }
      if (mountedRef.current && cards) setBaseCards(cards);
    } catch {
      // Keep last-known cards; WS ticks + summary polling in Dashboard context
      // will recover. Never blank the ticker on transient failure.
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    void fetchCards();
    // Quiet REST snapshot refresh — WS is the primary live source.
    // 30s cadence with jitter; paused while tab hidden.
    let timeout: ReturnType<typeof setTimeout> | null = null;
    let cancelled = false;
    const schedule = () => {
      timeout = setTimeout(() => {
        if (!cancelled && typeof document !== 'undefined' && !document.hidden) void fetchCards();
        if (!cancelled) schedule();
      }, 30000 * (0.85 + Math.random() * 0.3));
    };
    schedule();
    const onVis = () => {
      if (!document.hidden && !cancelled) void fetchCards();
    };
    document.addEventListener('visibilitychange', onVis);
    return () => {
      cancelled = true;
      mountedRef.current = false;
      if (timeout) clearTimeout(timeout);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [fetchCards]);

  // Throttle high-frequency WS ticks into ≤10 renders/sec.
  useEffect(() => {
    pendingTicksRef.current = { ...pendingTicksRef.current, ...rawTicks };
    if (batchTimerRef.current) return;
    batchTimerRef.current = setTimeout(() => {
      batchTimerRef.current = null;
      const pending = pendingTicksRef.current;
      pendingTicksRef.current = {};
      // requestAnimationFrame-aligned commit when available.
      const commit = () => setBatchedTicks((prev) => ({ ...prev, ...pending }));
      if (typeof requestAnimationFrame !== 'undefined') {
        requestAnimationFrame(commit);
      } else {
        commit();
      }
    }, TICK_BATCH_MS);
    return () => {};
  }, [rawTicks]);

  useEffect(() => {
    // If the feed goes stale, drop batched ticks so cards fall back to REST snapshot.
    if (!ticksFresh) setBatchedTicks({});
  }, [ticksFresh]);

  const prevDisplayedRef = useRef<Map<string, IndexCard>>(new Map());
  const displayedCards = useMemo(() => {
    if (!batchedTicks || Object.keys(batchedTicks).length === 0) {
      prevDisplayedRef.current.clear();
      baseCards.forEach((c) => prevDisplayedRef.current.set(c.symbol, c));
      return baseCards;
    }
    if (streamState !== 'CONNECTED' || !ticksFresh) {
      prevDisplayedRef.current.clear();
      baseCards.forEach((c) => prevDisplayedRef.current.set(c.symbol, c));
      return baseCards;
    }
    const next: IndexCard[] = [];
    for (const card of baseCards) {
      const tick: TimestampedTick | undefined = batchedTicks[card.symbol];
      if (!tick) {
        const prev = prevDisplayedRef.current.get(card.symbol);
        if (prev && prev === card) {
          next.push(card);
        } else if (prev && deepCardsEqual(prev, card)) {
          next.push(prev);
        } else {
          prevDisplayedRef.current.set(card.symbol, card);
          next.push(card);
        }
        continue;
      }
      const newLtp = Number(tick.ltp);
      if (!Number.isFinite(newLtp) || newLtp <= 0) {
        const prev = prevDisplayedRef.current.get(card.symbol);
        if (prev && prev.ltp === card.ltp) next.push(prev);
        else {
          prevDisplayedRef.current.set(card.symbol, card);
          next.push(card);
        }
        continue;
      }
      const prev = prevDisplayedRef.current.get(card.symbol);
      if (prev && prev.ltp === newLtp && prev.volume === (tick.volume ?? card.volume) && prev.status === 'LIVE') {
        next.push(prev);
        continue;
      }
      const change = newLtp - card.previous_close;
      const changePercent = card.previous_close > 0 ? (change / card.previous_close) * 100 : 0;
      let sparkline = card.sparkline;
      if (card.sparkline.length > 0 && card.sparkline[card.sparkline.length - 1] !== newLtp) {
        sparkline = card.sparkline.slice();
        sparkline[sparkline.length - 1] = newLtp;
      }
      const merged: IndexCard = {
        ...card,
        ltp: newLtp,
        change: Number(change.toFixed(2)),
        change_percent: Number(changePercent.toFixed(2)),
        sparkline,
        volume: tick.volume ?? card.volume,
        open_interest: tick.open_interest !== undefined ? tick.open_interest : card.open_interest,
        status: 'LIVE' as DataStatus,
        provider: tick.provider || card.provider,
      };
      prevDisplayedRef.current.set(card.symbol, merged);
      next.push(merged);
    }
    return next;
  }, [baseCards, batchedTicks, streamState, ticksFresh]);

  const healthValue = useMemo<StreamHealth>(
    () => ({ streamState, ticksFresh }),
    [streamState, ticksFresh]
  );

  const value = useMemo<LiveMarketContextType>(
    () => ({
      cards: displayedCards,
      latestTicks: batchedTicks,
      streamState,
      ticksFresh,
      loading,
      lastTickAt,
      refetchCards: fetchCards,
    }),
    [displayedCards, batchedTicks, streamState, ticksFresh, loading, lastTickAt, fetchCards]
  );

  return (
    <StreamHealthContext.Provider value={healthValue}>
      <LiveMarketContext.Provider value={value}>{children}</LiveMarketContext.Provider>
    </StreamHealthContext.Provider>
  );
}

export function useLiveMarketContext() {
  const ctx = useContext(LiveMarketContext);
  if (!ctx) throw new Error('useLiveMarketContext must be used within LiveMarketProvider');
  return ctx;
}

export function useOptionalLiveMarketContext() {
  return useContext(LiveMarketContext);
}

/** Stable WS health for adaptive REST polling — does NOT re-render on ticks. */
export function useStreamHealth(): StreamHealth {
  return useContext(StreamHealthContext);
}
