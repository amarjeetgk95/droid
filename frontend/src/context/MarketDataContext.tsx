'use client';

import { createContext, useContext, useState, useEffect, useMemo, useCallback, ReactNode } from 'react';
import { api } from '@/lib/api';
import type { IndexCard, MarketBreadthData, MarketHealthStatus, MarketStatusResponse } from '@/lib/types';
import { useMarketStream, StreamConnectionState } from '@/hooks/useMarketStream';

type MarketDataContextType = {
  cards: IndexCard[];
  breadth: MarketBreadthData | null;
  health: MarketHealthStatus | null;
  marketStatus: MarketStatusResponse | null;
  loading: boolean;
  error: string | null;
  lastFetch: Date | null;
  streamState: StreamConnectionState;
  refetch: () => Promise<void>;
};

const MarketDataContext = createContext<MarketDataContextType | null>(null);

const DEFAULT_REFRESH_MS = 15000; // was 5000 — throttle to reduce backend load (was duplicate 8 req/5s → now 4 req/15s shared)

export function MarketDataProvider({ children, refreshInterval = DEFAULT_REFRESH_MS }: { children: ReactNode; refreshInterval?: number }) {
  const [cards, setCards] = useState<IndexCard[]>([]);
  const [breadth, setBreadth] = useState<MarketBreadthData | null>(null);
  const [health, setHealth] = useState<MarketHealthStatus | null>(null);
  const [marketStatus, setMarketStatus] = useState<MarketStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastFetch, setLastFetch] = useState<Date | null>(null);

  const { latestTicks, streamState } = useMarketStream();

  const fetchData = useCallback(async () => {
    // Pause when tab hidden — saves Render quota + battery
    if (typeof document !== 'undefined' && document.hidden) return;
    try {
      const [cardsRes, breadthRes, healthRes, statusRes] = await Promise.all([
        api.getIndexCards(),
        api.getMarketBreadth(),
        api.getMarketHealth(),
        api.getMarketStatus(),
      ]);
      setCards(cardsRes.data);
      setBreadth(breadthRes.data);
      setHealth(healthRes);
      setMarketStatus(statusRes.data);
      setError(null);
      setLastFetch(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch market data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let isMounted = true;
    let interval: ReturnType<typeof setInterval> | null = null;

    const run = async () => {
      if (!isMounted) return;
      if (typeof document !== 'undefined' && document.hidden) return;
      try {
        const [cardsRes, breadthRes, healthRes, statusRes] = await Promise.all([
          api.getIndexCards(),
          api.getMarketBreadth(),
          api.getMarketHealth(),
          api.getMarketStatus(),
        ]);
        if (!isMounted) return;
        setCards(cardsRes.data);
        setBreadth(breadthRes.data);
        setHealth(healthRes);
        setMarketStatus(statusRes.data);
        setError(null);
        setLastFetch(new Date());
      } catch (err) {
        if (!isMounted) return;
        setError(err instanceof Error ? err.message : 'Failed to fetch market data');
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    run();
    interval = setInterval(run, refreshInterval);

    const onVisibility = () => {
      if (!document.hidden) run(); // refetch immediately when tab becomes visible
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      isMounted = false;
      if (interval) clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [refreshInterval, fetchData]);

  const displayedCards = useMemo(() => {
    if (!latestTicks || Object.keys(latestTicks).length === 0) return cards;
    return cards.map((card) => {
      const tick = latestTicks[card.symbol];
      if (!tick) return card;
      const newLtp = tick.ltp;
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
        volume: tick.volume || card.volume,
        open_interest: tick.open_interest !== undefined ? tick.open_interest : card.open_interest,
        status: 'LIVE' as const,
        provider: tick.provider || card.provider,
      };
    });
  }, [cards, latestTicks]);

  const value = useMemo<MarketDataContextType>(() => ({
    cards: displayedCards,
    breadth,
    health,
    marketStatus,
    loading,
    error,
    lastFetch,
    streamState,
    refetch: fetchData,
  }), [displayedCards, breadth, health, marketStatus, loading, error, lastFetch, streamState, fetchData]);

  return <MarketDataContext.Provider value={value}>{children}</MarketDataContext.Provider>;
}

export function useMarketDataContext() {
  const ctx = useContext(MarketDataContext);
  if (!ctx) throw new Error('useMarketDataContext must be used within MarketDataProvider');
  return ctx;
}

// Back-compat: keeps old import working but now shares singleton via context if available, else falls back to isolated fetch
// This ensures no duplicate polling even if some components still import from hooks/useMarketData
