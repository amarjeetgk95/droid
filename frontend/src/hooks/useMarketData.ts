'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { api } from '@/lib/api';
import type { IndexCard, MarketBreadthData, MarketHealthStatus, MarketStatusResponse, NormalizedCandle } from '@/lib/types';

import { useMarketStream } from './useMarketStream';

export function useMarketData(refreshInterval = 5000) {
  const [cards, setCards] = useState<IndexCard[]>([]);
  const [breadth, setBreadth] = useState<MarketBreadthData | null>(null);
  const [health, setHealth] = useState<MarketHealthStatus | null>(null);
  const [marketStatus, setMarketStatus] = useState<MarketStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastFetch, setLastFetch] = useState<Date | null>(null);

  const { latestTicks, streamState } = useMarketStream();

  const fetchData = useCallback(async () => {
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

    const run = async () => {
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
    const interval = setInterval(run, refreshInterval);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [refreshInterval]);

  // Merge live ticks into cards using useMemo
  const displayedCards = useMemo(() => {
    if (!latestTicks || Object.keys(latestTicks).length === 0) return cards;

    return cards.map((card) => {
      const tick = latestTicks[card.symbol];
      if (!tick) return card;

      const newLtp = tick.ltp;
      const change = newLtp - card.previous_close;
      const changePercent = card.previous_close > 0 ? (change / card.previous_close) * 100 : 0;
      const sparkline = [...card.sparkline];
      if (sparkline.length > 0) {
        sparkline[sparkline.length - 1] = newLtp;
      }

      return {
        ...card,
        ltp: newLtp,
        change: Number(change.toFixed(2)),
        change_percent: Number(changePercent.toFixed(2)),
        sparkline,
        volume: tick.volume || card.volume,
        open_interest: tick.open_interest !== undefined ? tick.open_interest : card.open_interest,
      };
    });
  }, [cards, latestTicks]);

  return { cards: displayedCards, breadth, health, marketStatus, loading, error, lastFetch, streamState, refetch: fetchData };
}

export function useCandles(symbol: string, timeframe: string) {
  const [candles, setCandles] = useState<NormalizedCandle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    api.getCandles(symbol, timeframe)
      .then(res => {
        if (!isMounted) return;
        setCandles(res.data);
        setError(null);
      })
      .catch(err => {
        if (!isMounted) return;
        setError(err instanceof Error ? err.message : 'Failed to fetch candles');
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [symbol, timeframe]);

  return { candles, loading, error };
}
