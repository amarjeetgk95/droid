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

const EMPTY_CARDS: IndexCard[] = [];

function isCryptoCard(c: Pick<IndexCard, 'symbol' | 'provider'>): boolean {
  const sym = (c.symbol || '').toUpperCase();
  const prov = (c.provider || '').toLowerCase();
  return prov.includes('binance') || sym.endsWith('USDT') || sym.endsWith('BTC');
}

function applyClosedStatus(list: IndexCard[], isMarketClosed: boolean): IndexCard[] {
  if (!isMarketClosed) return list;
  let changed = false;
  const next = list.map((c) => {
    if (isCryptoCard(c)) return c.status === 'LIVE' ? c : { ...c, status: 'LIVE' as DataStatus };
    return c.status === 'CLOSED' ? c : { ...c, status: 'CLOSED' as DataStatus };
  });
  // Preserve referential stability when nothing changed.
  for (let i = 0; i < next.length; i++) if (next[i] !== list[i]) { changed = true; break; }
  return changed ? next : list;
}

function mergeTickIntoCard(card: IndexCard, tick: TimestampedTick | undefined, targetStatus: DataStatus): IndexCard {
  if (!tick) return card.status !== targetStatus ? { ...card, status: targetStatus } : card;
  const newLtp = Number(tick.ltp);
  if (!Number.isFinite(newLtp) || newLtp <= 0) {
    return card.status !== targetStatus ? { ...card, status: targetStatus } : card;
  }
  const change = newLtp - card.previous_close;
  const changePercent = card.previous_close > 0 ? (change / card.previous_close) * 100 : 0;
  // Cap sparkline growth — tick batches arrive at 10/sec, never let the array drift.
  let sparkline = card.sparkline;
  if (sparkline.length > 0 && sparkline[sparkline.length - 1] !== newLtp) {
    sparkline = sparkline.length >= 120 ? [...sparkline.slice(1), newLtp] : [...sparkline.slice(0, -1), newLtp];
  }
  return {
    ...card,
    ltp: newLtp,
    change: Number(change.toFixed(2)),
    change_percent: Number(changePercent.toFixed(2)),
    sparkline,
    volume: tick.volume ?? card.volume,
    open_interest: tick.open_interest !== undefined ? tick.open_interest : card.open_interest,
    status: targetStatus,
    provider: tick.provider || card.provider,
  };
}

export function LiveMarketProvider({ children }: { children: ReactNode }) {
  // SINGLE-OWNER MODEL: MarketDataProvider (outer) owns the dashboard/summary
  // REST fetch + the market-feed WebSocket. This provider only merges shared
  // REST snapshot cards with shared WS ticks (batched) — no fetch, no socket.
  const market = useOptionalMarketDataContext();
  const { ticks: rawTicks, lastTickAt } = useMarketTicks();
  const baseCards = market?.cards ?? EMPTY_CARDS;
  const loading = market?.loading ?? true;
  const streamState: StreamConnectionState = market?.streamState ?? 'CONNECTING';
  const ticksFresh = market?.ticksFresh ?? false;
  const isMarketClosed = market?.marketStatus?.session === 'CLOSED' || market?.marketStatus?.is_trading_day === false;
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
      if (Object.keys(pending).length === 0) return;
      // requestAnimationFrame-aligned commit when available.
      const commit = () => setBatchedTicks((prev) => ({ ...prev, ...pending }));
      if (typeof requestAnimationFrame !== 'undefined') {
        requestAnimationFrame(commit);
      } else {
        commit();
      }
    }, TICK_BATCH_MS);
  }, [rawTicks]);

  useEffect(() => {
    return () => {
      if (batchTimerRef.current) clearTimeout(batchTimerRef.current);
    };
  }, []);

  // External sync: WS health → local batch. Clearing stale ticks when the feed
  // drops is intentional (not derived render state), so the set-state-in-effect
  // warning does not apply here.
  useEffect(() => {
    if (!ticksFresh) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setBatchedTicks((prev) => (Object.keys(prev).length === 0 ? prev : {}));
    }
  }, [ticksFresh]);

  // Pure derivation — no refs, no side effects. 5 cards at ≤10 renders/sec is
  // cheap; referential stability comes from memo deps, not a manual cache.
  const displayedCards = useMemo(() => {
    const hasTicks = batchedTicks && Object.keys(batchedTicks).length > 0;
    const live = streamState === 'CONNECTED' && ticksFresh && hasTicks;
    if (!live) return applyClosedStatus(baseCards, isMarketClosed);
    return baseCards.map((card) => {
      const crypto = isCryptoCard(card);
      const targetStatus: DataStatus = crypto ? 'LIVE' : card.status === 'CLOSED' || isMarketClosed ? 'CLOSED' : 'LIVE';
      return mergeTickIntoCard(card, batchedTicks[card.symbol], targetStatus);
    });
  }, [baseCards, batchedTicks, streamState, ticksFresh, isMarketClosed]);

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
