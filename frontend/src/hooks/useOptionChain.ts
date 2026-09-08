'use client';

import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { strikeStepFor, syntheticStrikes } from '@/lib/paperLots';

export interface ChainStrike {
  strike: number;
  isAtm: boolean;
  ceLtp: number | null;
  peLtp: number | null;
}

interface UseOptionChainResult {
  expiries: string[];
  expiry: string | null;
  setExpiry: (e: string | null) => void;
  spot: number | null;
  atm: number | null;
  strikes: ChainStrike[];
  loading: boolean;
  /** True when strikes carry live broker LTPs; false = synthetic offline ladder. */
  isLive: boolean;
  ltpFor: (strike: number, optionType: 'CE' | 'PE') => number | null;
}

function positiveOrNull(n: unknown): number | null {
  return typeof n === 'number' && Number.isFinite(n) && n > 0 ? n : null;
}

/**
 * Live option-chain ladder for the paper ticket with a synthetic offline
 * fallback, so the strike picker never degrades to free-typed input —
 * even when the backend is unreachable (offline demo mode).
 */
export function useOptionChain(underlying: string, fallbackCenter: number): UseOptionChainResult {
  const [expiries, setExpiries] = useState<string[]>([]);
  const [expiry, setExpiry] = useState<string | null>(null);
  const [spot, setSpot] = useState<number | null>(null);
  const [atm, setAtm] = useState<number | null>(null);
  const [strikes, setStrikes] = useState<ChainStrike[]>([]);
  const [loading, setLoading] = useState(false);
  const [isLive, setIsLive] = useState(false);

  // Expiry catalog per underlying.
  useEffect(() => {
    let cancelled = false;
    setExpiry(null);
    setExpiries([]);
    (async () => {
      try {
        const res = await api.getContractExpiries(underlying);
        if (cancelled) return;
        const d = res.data;
        const list =
          d?.all_expiries?.length > 0
            ? d.all_expiries
            : [...(d?.weekly_expiries ?? []), ...(d?.monthly_expiries ?? [])];
        if (list.length > 0) {
          setExpiries(list);
          setExpiry(d?.current_expiry ?? list[0]);
        }
      } catch {
        // Offline — expiry dropdown simply hides; synthetic ladder still works.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [underlying]);

  // Chain ladder per underlying + expiry.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const res = await api.getOptionChain(underlying, expiry ?? undefined);
        if (cancelled) return;
        const d = res.data;
        const rows = d?.strikes ?? [];
        if (d && rows.length > 0) {
          setSpot(d.spot_price > 0 ? d.spot_price : null);
          setAtm(d.analytics?.atm_strike ?? null);
          if (d.expiries?.length > 0) setExpiries(d.expiries);
          if (d.expiry) setExpiry((prev) => prev ?? d.expiry);
          setStrikes(
            rows.map((r) => ({
              strike: r.strike,
              isAtm: r.is_atm,
              ceLtp: positiveOrNull(r.call?.ltp),
              peLtp: positiveOrNull(r.put?.ltp),
            })),
          );
          setIsLive(true);
          return;
        }
        // Live call succeeded but chain is empty (market closed / no spot):
        // fall through to quote + synthetic ladder.
        try {
          const q = await api.getQuote(underlying);
          if (cancelled) return;
          applySynthetic(q?.data?.ltp, fallbackCenter, underlying, setSpot, setAtm, setStrikes);
        } catch {
          if (cancelled) return;
          applySynthetic(null, fallbackCenter, underlying, setSpot, setAtm, setStrikes);
        }
        setIsLive(false);
      } catch {
        if (cancelled) return;
        // Fully offline — keep any last spot if we can, else synthetic only.
        try {
          const q = await api.getQuote(underlying);
          if (cancelled) return;
          applySynthetic(q?.data?.ltp, fallbackCenter, underlying, setSpot, setAtm, setStrikes);
        } catch {
          if (cancelled) return;
          applySynthetic(null, fallbackCenter, underlying, setSpot, setAtm, setStrikes);
        }
        setIsLive(false);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // fallbackCenter intentionally excluded: it only seeds the very first
    // synthetic ladder; re-running on every strike move would yank the list.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [underlying, expiry]);

  const ltpFor = useCallback(
    (strike: number, optionType: 'CE' | 'PE'): number | null => {
      const row = strikes.find((s) => s.strike === strike);
      if (!row) return null;
      return optionType === 'CE' ? row.ceLtp : row.peLtp;
    },
    [strikes],
  );

  return { expiries, expiry, setExpiry, spot, atm, strikes, loading, isLive, ltpFor };
}

function applySynthetic(
  quoteLtp: unknown,
  fallbackCenter: number,
  underlying: string,
  setSpot: (n: number | null) => void,
  setAtm: (n: number | null) => void,
  setStrikes: (s: ChainStrike[]) => void,
): void {
  const step = strikeStepFor(underlying);
  const quote = typeof quoteLtp === 'number' && Number.isFinite(quoteLtp) && quoteLtp > 0 ? quoteLtp : null;
  const center = quote ?? (Number.isFinite(fallbackCenter) && fallbackCenter > 0 ? fallbackCenter : 0);
  if (quote !== null) setSpot(quote);
  if (center <= 0) {
    setStrikes([]);
    return;
  }
  const atmStrike = Math.round(center / step) * step;
  setAtm(atmStrike);
  setStrikes(
    syntheticStrikes(center, step).map((s) => ({ strike: s, isAtm: s === atmStrike, ceLtp: null, peLtp: null })),
  );
}
