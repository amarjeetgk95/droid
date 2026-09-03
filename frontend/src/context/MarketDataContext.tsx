'use client';

import { createContext, useContext, useState, useEffect, useMemo, useCallback, ReactNode, useRef } from 'react';
import { api } from '@/lib/api';
import type { IndexCard, MarketBreadthData, MarketHealthStatus, MarketStatusResponse, DataStatus } from '@/lib/types';
import { useMarketStream, StreamConnectionState, TimestampedTick } from '@/hooks/useMarketStream';

type SectionErrors = {
  cards: string | null;
  breadth: string | null;
  health: string | null;
  marketStatus: string | null;
};

type MarketDataContextType = {
  cards: IndexCard[];
  breadth: MarketBreadthData | null;
  health: MarketHealthStatus | null;
  marketStatus: MarketStatusResponse | null;
  loading: boolean;
  /** First non-null section error — back-compat convenience. */
  error: string | null;
  /** Per-section errors — a failing endpoint no longer blanks the whole page. */
  errors: SectionErrors;
  lastFetch: Date | null;
  streamState: StreamConnectionState;
  refreshInterval: number;
  setRefreshInterval: (ms: number) => void;
  refetch: () => Promise<void>;
};

const MarketDataContext = createContext<MarketDataContextType | null>(null);

const DEFAULT_REFRESH_MS = 1000;

const EMPTY_ERRORS: SectionErrors = { cards: null, breadth: null, health: null, marketStatus: null };

const errMessage = (err: unknown) => (err instanceof Error ? err.message : 'Failed to fetch market data');

export function MarketDataProvider({ children, refreshInterval = DEFAULT_REFRESH_MS, useSummaryEndpoint = false }: { children: ReactNode; refreshInterval?: number; useSummaryEndpoint?: boolean }) {
  const [cards, setCards] = useState<IndexCard[]>([]);
  const [breadth, setBreadth] = useState<MarketBreadthData | null>(null);
  const [health, setHealth] = useState<MarketHealthStatus | null>(null);
  const [marketStatus, setMarketStatus] = useState<MarketStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState<SectionErrors>(EMPTY_ERRORS);
  const [lastFetch, setLastFetch] = useState<Date | null>(null);
  const [activeInterval, setActiveInterval] = useState<number>(refreshInterval);

  const { latestTicks, streamState, ticksFresh } = useMarketStream();
  const inFlightRef = useRef(false);
  const mountedRef = useRef(true);

  // Single implementation shared by polling, visibility refresh and refetch().
  const fetchData = useCallback(async () => {
    if (inFlightRef.current) return;
    if (typeof document !== 'undefined' && document.hidden) return;
    inFlightRef.current = true;
    try {
      if (useSummaryEndpoint) {
        let summaryData: any = null;
        try {
          const summaryRes = await api.getDashboardSummary();
          summaryData = summaryRes.data;
        } catch (err) {
          // summaryData stays null, errors populated below
        }
        if (!mountedRef.current) return;

        const errors: SectionErrors = {
          cards: summaryData?.errors?.cards ?? null,
          breadth: summaryData?.errors?.breadth ?? null,
          health: summaryData?.errors?.health ?? null,
          marketStatus: summaryData?.errors?.status ?? null,
        };

        if (summaryData) {
          if (summaryData.cards && mountedRef.current) {
            setCards((prevCards) => {
              const newCards = summaryData.cards as IndexCard[];
              if (!prevCards || prevCards.length === 0) return newCards;
              return newCards.map((nc) => {
                const old = prevCards.find((o) => o.symbol === nc.symbol);
                if (old && Number(nc.ltp) <= 0 && Number(old.ltp) > 0) {
                  return {
                    ...nc,
                    ltp: old.ltp,
                    open: old.open || nc.open,
                    high: old.high || nc.high,
                    low: old.low || nc.low,
                    previous_close: old.previous_close || nc.previous_close,
                    change: old.change || nc.change,
                    change_percent: old.change_percent || nc.change_percent,
                    volume: old.volume || nc.volume,
                    open_interest: old.open_interest || nc.open_interest,
                    sparkline: old.sparkline && old.sparkline.length > 0 ? old.sparkline : nc.sparkline,
                    status: nc.status === 'OFFLINE' ? old.status : nc.status,
                  };
                }
                return nc;
              });
            });
          }
          if (summaryData.breadth && mountedRef.current) setBreadth(summaryData.breadth as MarketBreadthData);
          if (summaryData.health && mountedRef.current) setHealth(summaryData.health as MarketHealthStatus);
          if (summaryData.market_status && mountedRef.current) setMarketStatus(summaryData.market_status as MarketStatusResponse);
        }
        setErrors(errors);
        setLastFetch(new Date());
      } else {
        const [cardsRes, breadthRes, healthRes, statusRes] = await Promise.allSettled([
          api.getIndexCards(),
          api.getMarketBreadth(),
          api.getMarketHealth(),
          api.getMarketStatus(),
        ]);
        if (!mountedRef.current) return;

        const nextErrors: SectionErrors = {
          cards: cardsRes.status === 'rejected' ? errMessage(cardsRes.reason) : null,
          breadth: breadthRes.status === 'rejected' ? errMessage(breadthRes.reason) : null,
          health: healthRes.status === 'rejected' ? errMessage(healthRes.reason) : null,
          marketStatus: statusRes.status === 'rejected' ? errMessage(statusRes.reason) : null,
        };

        if (cardsRes.status === 'fulfilled') {
          setCards((prevCards) => {
            const newCards = cardsRes.value.data;
            if (!prevCards || prevCards.length === 0) return newCards;
            return newCards.map((nc) => {
              const old = prevCards.find((o) => o.symbol === nc.symbol);
              if (old && Number(nc.ltp) <= 0 && Number(old.ltp) > 0) {
                return {
                  ...nc,
                  ltp: old.ltp,
                  open: old.open || nc.open,
                  high: old.high || nc.high,
                  low: old.low || nc.low,
                  previous_close: old.previous_close || nc.previous_close,
                  change: old.change || nc.change,
                  change_percent: old.change_percent || nc.change_percent,
                  volume: old.volume || nc.volume,
                  open_interest: old.open_interest || nc.open_interest,
                  sparkline: old.sparkline && old.sparkline.length > 0 ? old.sparkline : nc.sparkline,
                  status: nc.status === 'OFFLINE' ? old.status : nc.status,
                };
              }
              return nc;
            });
          });
        }
        if (breadthRes.status === 'fulfilled') setBreadth(breadthRes.value.data);
        if (healthRes.status === 'fulfilled') setHealth(healthRes.value);
        if (statusRes.status === 'fulfilled') setMarketStatus(statusRes.value.data);
        setErrors(nextErrors);
        setLastFetch(new Date());
      }
    } finally {
      inFlightRef.current = false;
      if (mountedRef.current) setLoading(false);
    }
  }, [useSummaryEndpoint]);

  useEffect(() => {
    mountedRef.current = true;
    let timeout: ReturnType<typeof setTimeout> | null = null;

    // Chained timeout with ±20% jitter — otherwise all clients hit the backend
    // in lockstep every 15s (thundering herd on the free Render instance).
    const schedule = () => {
      const interval = Math.max(500, activeInterval);
      timeout = setTimeout(() => {
        void fetchData();
        schedule();
      }, interval);
    };

    void fetchData();
    schedule();

    const onVisibility = () => {
      if (!document.hidden) void fetchData(); // refetch immediately when tab becomes visible
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      mountedRef.current = false;
      if (timeout) clearTimeout(timeout);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [activeInterval, fetchData]);

  // Merge live ticks into cards — per-symbol memoized to avoid re-rendering unchanged cards.
  // latestTicks keeps the last-ever tick batch; `ticksFresh` flips false after FEED_STALE_MS without a message.
  // Each unchanged card keeps its original reference so React.memo(MarketCard) skips re-render.
  const prevDisplayedRef = useRef<Map<string, IndexCard>>(new Map());
  const displayedCards = useMemo(() => {
    if (!latestTicks || Object.keys(latestTicks).length === 0) {
      prevDisplayedRef.current.clear();
      cards.forEach((c) => prevDisplayedRef.current.set(c.symbol, c));
      return cards;
    }
    if (streamState !== 'CONNECTED' || !ticksFresh) {
      prevDisplayedRef.current.clear();
      cards.forEach((c) => prevDisplayedRef.current.set(c.symbol, c));
      return cards;
    }

    const next: IndexCard[] = [];
    for (const card of cards) {
      const tick: TimestampedTick | undefined = latestTicks[card.symbol];
      if (!tick) {
        // Keep previous reference if symbol unchanged to preserve memo equality
        const prev = prevDisplayedRef.current.get(card.symbol);
        if (prev && prev === card) {
          next.push(card);
        } else if (prev && deepCardsEqual(prev, card)) {
          // If card object is new but deep equal and no tick, reuse prev reference
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
      // Fast path: if tick ltp same as previous displayed ltp and volume unchanged, reuse prev
      if (prev && prev.ltp === newLtp && prev.volume === (tick.volume ?? card.volume) && prev.status === 'LIVE') {
        next.push(prev);
        continue;
      }
      const change = newLtp - card.previous_close;
      const changePercent = card.previous_close > 0 ? (change / card.previous_close) * 100 : 0;
      // Only clone sparkline when we actually update it — avoid spread on every tick for unchanged
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
  }, [cards, latestTicks, streamState, ticksFresh]);

  function deepCardsEqual(a: IndexCard, b: IndexCard): boolean {
    return a.ltp === b.ltp && a.change === b.change && a.change_percent === b.change_percent && a.volume === b.volume && a.status === b.status && a.sparkline === b.sparkline;
  }

  const value = useMemo<MarketDataContextType>(() => ({
    cards: displayedCards,
    breadth,
    health,
    marketStatus,
    loading,
    error: errors.cards ?? errors.breadth ?? errors.health ?? errors.marketStatus,
    errors,
    lastFetch,
    streamState,
    refreshInterval: activeInterval,
    setRefreshInterval: setActiveInterval,
    refetch: fetchData,
  }), [displayedCards, breadth, health, marketStatus, loading, errors, lastFetch, streamState, activeInterval, fetchData]);

  return <MarketDataContext.Provider value={value}>{children}</MarketDataContext.Provider>;
}

export function useMarketDataContext(options?: { useSummaryEndpoint?: boolean }) {
  const ctx = useContext(MarketDataContext);
  if (!ctx) throw new Error('useMarketDataContext must be used within MarketDataProvider');
  return ctx;
}
