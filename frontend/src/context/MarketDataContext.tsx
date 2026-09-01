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
  refetch: () => Promise<void>;
};

const MarketDataContext = createContext<MarketDataContextType | null>(null);

const DEFAULT_REFRESH_MS = 15000;

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
          if (summaryData.cards && mountedRef.current) setCards(summaryData.cards as IndexCard[]);
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

        if (cardsRes.status === 'fulfilled') setCards(cardsRes.value.data);
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
      const jittered = refreshInterval * (0.8 + Math.random() * 0.4);
      timeout = setTimeout(() => {
        void fetchData();
        schedule();
      }, jittered);
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
  }, [refreshInterval, fetchData]);

  // Merge live ticks into cards — but ONLY while the feed is actually fresh.
  // latestTicks keeps the last-ever tick batch; `ticksFresh` flips false after
  // FEED_STALE_MS without a message, so a card never claims LIVE after the stream dies.
  const displayedCards = useMemo(() => {
    if (!latestTicks || Object.keys(latestTicks).length === 0) return cards;
    if (streamState !== 'CONNECTED') return cards;
    if (!ticksFresh) return cards;

    return cards.map((card) => {
      const tick: TimestampedTick | undefined = latestTicks[card.symbol];
      if (!tick) return card;

      const newLtp = Number(tick.ltp);
      if (!Number.isFinite(newLtp)) return card;
      const change = newLtp - card.previous_close;
      const changePercent = card.previous_close > 0 ? (change / card.previous_close) * 100 : 0;
      const sparkline = [...card.sparkline];
      if (sparkline.length > 0) sparkline[sparkline.length - 1] = newLtp;

      return {
        ...card,
        ltp: newLtp,
        change: Number(change.toFixed(2)),
        change_percent: Number(changePercent.toFixed(2)),
        sparkline,
        // ?? not || — a legitimate 0 volume must not fall back to stale data
        volume: tick.volume ?? card.volume,
        open_interest: tick.open_interest !== undefined ? tick.open_interest : card.open_interest,
        status: 'LIVE' as DataStatus,
        provider: tick.provider || card.provider,
      };
    });
  }, [cards, latestTicks, streamState, ticksFresh]);

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
    refetch: fetchData,
  }), [displayedCards, breadth, health, marketStatus, loading, errors, lastFetch, streamState, fetchData]);

  return <MarketDataContext.Provider value={value}>{children}</MarketDataContext.Provider>;
}

export function useMarketDataContext(options?: { useSummaryEndpoint?: boolean }) {
  const ctx = useContext(MarketDataContext);
  if (!ctx) throw new Error('useMarketDataContext must be used within MarketDataProvider');
  return ctx;
}
