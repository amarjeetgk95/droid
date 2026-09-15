'use client';

import { useState, useCallback, useRef, useMemo, useEffect } from 'react';
import { api } from '@/lib/api';
import { useSmartInterval } from './useSmartInterval';
import type { ScalpUnderlying } from '@/components/scalp/ScalpContext';

export interface AtmQuotes {
  ceLtp: number | null;
  peLtp: number | null;
  ceBid: number | null;
  ceAsk: number | null;
  peBid: number | null;
  peAsk: number | null;
  ceIv: number | null;
  peIv: number | null;
  ceDelta: number | null;
  peDelta: number | null;
  ceOi: number | null;
  peOi: number | null;
  expiry: string | null;
  fetchedAt: number | null;
}

export const EMPTY_QUOTES: AtmQuotes = {
  ceLtp: null,
  peLtp: null,
  ceBid: null,
  ceAsk: null,
  peBid: null,
  peAsk: null,
  ceIv: null,
  peIv: null,
  ceDelta: null,
  peDelta: null,
  ceOi: null,
  peOi: null,
  expiry: null,
  fetchedAt: null,
};

export interface SpreadInfo {
  spread: number | null;
  wide: boolean;
  missing: boolean;
}

export function calculateSpread(bid: number | null, ask: number | null, ltp: number | null): SpreadInfo {
  if (bid === null || ask === null || ltp === null) {
    return { spread: null, wide: false, missing: true };
  }
  if (!(bid > 0) || !(ask > 0) || !(ltp > 0) || ask < bid) {
    return { spread: null, wide: true, missing: false };
  }
  const spread = ask - bid;
  const wide = spread > Math.max(1.5, ltp * 0.03);
  return { spread, wide, missing: false };
}

export function useOptionQuotes(
  underlying: ScalpUnderlying,
  ceStrike: number,
  peStrike: number
) {
  const [quotes, setQuotes] = useState<AtmQuotes>(EMPTY_QUOTES);
  const [quoteError, setQuoteError] = useState<string | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());

  const requestIdRef = useRef(0);

  useEffect(() => {
    const timer = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const fetchQuotes = useCallback(async () => {
    if (!ceStrike || !peStrike || ceStrike <= 0 || peStrike <= 0) return;

    const reqId = ++requestIdRef.current;
    try {
      const res = await api.getOptionChain(underlying);
      if (reqId !== requestIdRef.current) return;

      if (res.error) {
        setQuoteError(res.error);
        return;
      }

      const chain = res.data;
      const strikes = chain?.strikes || [];
      if (strikes.length === 0) {
        setQuoteError('Option chain unavailable');
        return;
      }

      let bestCe = strikes[0];
      let bestCeDist = Math.abs((bestCe?.strike ?? 0) - ceStrike);
      for (const row of strikes) {
        const d = Math.abs(row.strike - ceStrike);
        if (d < bestCeDist) {
          bestCe = row;
          bestCeDist = d;
        }
      }

      let bestPe = strikes[0];
      let bestPeDist = Math.abs((bestPe?.strike ?? 0) - peStrike);
      for (const row of strikes) {
        const d = Math.abs(row.strike - peStrike);
        if (d < bestPeDist) {
          bestPe = row;
          bestPeDist = d;
        }
      }

      setQuotes({
        ceLtp: bestCe?.call?.ltp ?? null,
        peLtp: bestPe?.put?.ltp ?? null,
        ceBid: bestCe?.call?.bid ?? null,
        ceAsk: bestCe?.call?.ask ?? null,
        peBid: bestPe?.put?.bid ?? null,
        peAsk: bestPe?.put?.ask ?? null,
        ceIv: bestCe?.call?.greeks?.iv ?? null,
        peIv: bestPe?.put?.greeks?.iv ?? null,
        ceDelta: bestCe?.call?.greeks?.delta ?? null,
        peDelta: bestPe?.put?.greeks?.delta ?? null,
        ceOi: bestCe?.call?.open_interest ?? null,
        peOi: bestPe?.put?.open_interest ?? null,
        expiry: chain?.expiry ?? null,
        fetchedAt: Date.now(),
      });
      setQuoteError(null);
    } catch (err: unknown) {
      if (reqId !== requestIdRef.current) return;
      setQuoteError((err as Error)?.message || 'Option chain unavailable');
    }
  }, [underlying, ceStrike, peStrike]);

  const { refresh } = useSmartInterval(fetchQuotes, 5000, {
    fireOnMount: true,
    fireOnVisible: true,
    pauseWhenHidden: true,
  });

  // Immediate refetch when the strike/underlying changes — the interval
  // keeps the callback in a ref and would otherwise wait a full cycle,
  // leaving BANKNIFTY/SENSEX showing stale NIFTY quotes.
  useEffect(() => {
    void refresh();
  }, [underlying, ceStrike, peStrike, refresh]);

  const quoteAgeSec = useMemo(() => {
    return quotes.fetchedAt != null ? Math.max(0, Math.floor((nowMs - quotes.fetchedAt) / 1000)) : null;
  }, [nowMs, quotes.fetchedAt]);

  const quotesStale = quoteAgeSec === null || quoteAgeSec > 15;

  const ceSpread = useMemo(
    () => calculateSpread(quotes.ceBid, quotes.ceAsk, quotes.ceLtp),
    [quotes.ceBid, quotes.ceAsk, quotes.ceLtp]
  );

  const peSpread = useMemo(
    () => calculateSpread(quotes.peBid, quotes.peAsk, quotes.peLtp),
    [quotes.peBid, quotes.peAsk, quotes.peLtp]
  );

  return {
    quotes,
    quoteError,
    quoteAgeSec,
    quotesStale,
    ceSpread,
    peSpread,
    refresh,
  };
}
