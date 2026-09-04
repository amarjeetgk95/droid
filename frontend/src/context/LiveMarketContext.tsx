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
import type { StreamConnectionState, TimestampedTick } from '@/hooks/useMarketStream';
import { useOptionalMarketDataContext, useMarketTicks } from './MarketDataContext';
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
  // SINGLE-OWNER MODEL: MarketDataProvider (outer) owns the dashboard/summary
  // REST fetch + the market-feed WebSocket. This provider only merges shared
  // REST snapshot cards with shared WS ticks (batched) — no fetch, no socket.
  const market = useOptionalMarketDataContext();
  const { ticks: rawTicks, lastTickAt } = useMarketTicks();
  const baseCards = market?.cards ?? [];
  const loading = market?.loading ?? true;
  const streamState: StreamConnectionState = market?.streamState ?? 'CONNECTING';
  const ticksFresh = market?.ticksFresh ?? false;
  const marketRefetch = market?.refetch;
  const refetchCards = useCallback(() => {
    if (marketRefetch) return marketRefetch();
    return Promise.resolve();
  }, [marketRefetch]);
  const [batchedTicks, setBatchedTicks] = useState<Record<string, TimestampedTick>>({});
  const batchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingTicksRef = useRef<Record<string, TimestampedTick>>({});

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
      refetchCards,
    }),
    [displayedCards, batchedTicks, streamState, ticksFresh, loading, lastTickAt, refetchCards]
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
