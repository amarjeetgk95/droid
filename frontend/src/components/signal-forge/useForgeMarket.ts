'use client';

import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { errorMessage, finiteNumber } from './forgeLogic';

/**
 * Live market context for the Forge panels, sourced from the published option
 * chain (spot + ATM IV + ATM strike + DTE). There are no fallback prices: a
 * failed or incomplete chain surfaces as `status: 'error'` and every dependent
 * panel renders an explicit unavailable state.
 *
 * Contract note: `analytics.atm_iv` is published in PERCENT by the options
 * service; the intelligence endpoints take a fraction, so `iv` is /100 and
 * `ivPct` keeps the published value.
 */
export interface ForgeMarketState {
  status: 'loading' | 'ready' | 'error';
  spot: number | null;
  iv: number | null;
  ivPct: number | null;
  atmStrike: number | null;
  dteDays: number | null;
  expiry: string | null;
  error: string | null;
}

const INITIAL: ForgeMarketState = {
  status: 'loading',
  spot: null,
  iv: null,
  ivPct: null,
  atmStrike: null,
  dteDays: null,
  expiry: null,
  error: null,
};

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

export function useForgeMarket(underlying: string): ForgeMarketState & { refresh: () => void } {
  const [state, setState] = useState<ForgeMarketState>(INITIAL);
  const [nonce, setNonce] = useState(0);
  const refresh = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    setState((prev) => ({ ...prev, status: 'loading', error: null }));
    void (async () => {
      try {
        const res = await api.getOptionChain(underlying);
        const data = asRecord(res?.data);
        const analytics = asRecord(data?.analytics);
        const spot = finiteNumber(data?.spot_price);
        if (spot === null || spot <= 0) {
          throw new Error(`Live spot price not published for ${underlying} — option panels unavailable.`);
        }
        const ivPctRaw = finiteNumber(analytics?.atm_iv);
        const ivPct = ivPctRaw !== null && ivPctRaw > 0 ? ivPctRaw : null;
        const atmStrikeRaw = finiteNumber(analytics?.atm_strike);
        const dteRaw = finiteNumber(analytics?.time_to_expiry_days);
        if (cancelled) return;
        setState({
          status: 'ready',
          spot,
          iv: ivPct !== null ? ivPct / 100 : null,
          ivPct,
          atmStrike: atmStrikeRaw !== null && atmStrikeRaw > 0 ? atmStrikeRaw : null,
          dteDays: dteRaw !== null && dteRaw > 0 ? dteRaw : null,
          expiry: typeof data?.expiry === 'string' && data.expiry ? data.expiry : null,
          error: null,
        });
      } catch (e) {
        if (cancelled) return;
        setState({
          ...INITIAL,
          status: 'error',
          error: errorMessage(e, `Option chain unavailable for ${underlying}.`),
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [underlying, nonce]);

  return { ...state, refresh };
}
