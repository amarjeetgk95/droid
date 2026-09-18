'use client';

import { useCallback, useRef, useState } from 'react';
import { usePolling } from '@/hooks/usePolling';
import { api } from '@/lib/api';
import { toNumber } from '@/lib/coerce';
import { errorMessage } from '@/lib/errors';
import type { PortfolioSummary, VirtualPosition } from '@/lib/types';

export interface PaperPortfolioView extends PortfolioSummary {
  virtualCapital: number | null;
  availableMargin: number | null;
  usedMargin: number | null;
  marginUtilizationPct: number | null;
  marginUtilPct: number | null;
  realizedPnl: number | null;
  unrealizedPnl: number | null;
  totalPnl: number | null;
  openPositionsCount: number | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function parsePortfolio(payload: unknown): PaperPortfolioView | null {
  if (!payload || typeof payload !== 'object') return null;
  const o = (isRecord(payload) && 'data' in payload && isRecord(payload.data)
    ? payload.data
    : payload) as Record<string, unknown>;

  const virtualCapital = toNumber(o.virtual_capital);
  const availableMargin = toNumber(o.available_margin);
  const usedMarginRaw = toNumber(o.used_margin);
  const usedMargin =
    usedMarginRaw !== null
      ? usedMarginRaw
      : virtualCapital !== null && availableMargin !== null
        ? virtualCapital - availableMargin
        : null;

  const realizedPnl = toNumber(o.total_realized_pnl);
  const unrealizedPnl = toNumber(o.total_unrealized_pnl);
  const totalPnlRaw = toNumber(o.total_portfolio_pnl);
  const totalPnl =
    totalPnlRaw !== null
      ? totalPnlRaw
      : realizedPnl !== null && unrealizedPnl !== null
        ? realizedPnl + unrealizedPnl
        : null;

  let marginUtilizationPct = toNumber(o.margin_utilization_pct);
  if (
    marginUtilizationPct === null &&
    usedMargin !== null &&
    virtualCapital !== null &&
    virtualCapital > 0
  ) {
    marginUtilizationPct = (usedMargin / virtualCapital) * 100;
  }

  const openPositionsCount = toNumber(o.open_positions_count);

  return {
    virtual_capital: virtualCapital ?? 0,
    available_margin: availableMargin ?? 0,
    used_margin: usedMargin ?? 0,
    margin_utilization_pct: marginUtilizationPct ?? 0,
    total_realized_pnl: realizedPnl ?? 0,
    total_unrealized_pnl: unrealizedPnl ?? 0,
    total_portfolio_pnl: totalPnl ?? 0,
    open_positions_count: openPositionsCount ?? 0,

    virtualCapital,
    availableMargin,
    usedMargin,
    marginUtilizationPct,
    marginUtilPct: marginUtilizationPct,
    realizedPnl,
    unrealizedPnl,
    totalPnl,
    openPositionsCount,
  };
}

export interface UsePaperTradingOptions {
  pollIntervalMs?: number;
  enabled?: boolean;
}

export function usePaperTrading(options?: UsePaperTradingOptions) {
  const pollIntervalMs = options?.pollIntervalMs ?? 4000;
  const enabled = options?.enabled ?? true;

  const [portfolio, setPortfolio] = useState<PaperPortfolioView | null>(null);
  const [positions, setPositions] = useState<VirtualPosition[]>([]);
  const [rawPositions, setRawPositions] = useState<VirtualPosition[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [portfolioError, setPortfolioError] = useState<string | null>(null);
  const [positionsError, setPositionsError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const loadedRef = useRef(false);
  const inFlightRef = useRef(false);

  const load = useCallback(async () => {
    if (typeof document !== 'undefined' && document.hidden) return;
    if (inFlightRef.current) return;
    inFlightRef.current = true;

    const initial = !loadedRef.current;
    if (initial) setLoading(true);
    else setRefreshing(true);

    try {
      const [portfolioRes, positionsRes] = await Promise.allSettled([
        api.getPaperPortfolio(),
        api.getPaperPositions(),
      ]);

      const failures: string[] = [];

      if (portfolioRes.status === 'fulfilled') {
        const value = portfolioRes.value;
        if (value && typeof value === 'object' && 'error' in value && value.error) {
          failures.push(String(value.error));
          setPortfolioError(String(value.error));
        } else {
          const parsed = parsePortfolio(value?.data ?? value);
          if (parsed !== null) {
            setPortfolio(parsed);
            setPortfolioError(null);
          } else {
            failures.push('portfolio payload unusable');
            setPortfolioError('portfolio payload unusable');
          }
        }
      } else {
        const msg = errorMessage(portfolioRes.reason, 'portfolio unavailable');
        failures.push(msg);
        setPortfolioError(msg);
      }

      if (positionsRes.status === 'fulfilled') {
        const value = positionsRes.value;
        if (value && typeof value === 'object' && 'error' in value && value.error) {
          failures.push(String(value.error));
          setPositionsError(String(value.error));
        } else {
          const raw = Array.isArray(value?.data)
            ? value.data
            : Array.isArray(value)
              ? (value as VirtualPosition[])
              : null;
          if (raw !== null) {
            setRawPositions(raw);
            setPositions(raw.filter((p) => p && p.is_open !== false));
            setPositionsError(null);
          } else {
            failures.push('positions unavailable');
            setPositionsError('positions unavailable');
          }
        }
      } else {
        const msg = errorMessage(positionsRes.reason, 'positions unavailable');
        failures.push(msg);
        setPositionsError(msg);
      }

      setError(failures.length > 0 ? failures.join(' · ') : null);
      if (failures.length < 2) {
        setLastUpdated(new Date());
      }
      loadedRef.current = true;
    } finally {
      inFlightRef.current = false;
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  usePolling(load, pollIntervalMs, enabled);

  const squareOffPosition = useCallback(async (positionId: string) => {
    const fn = api.closePaperPosition ?? api.squareOffPosition;
    if (typeof fn !== 'function') {
      throw new Error('Square-off function is not available on api client.');
    }
    return fn(positionId);
  }, []);

  const squareOffAll = useCallback(async () => {
    const fn = api.closeAllPaperPositions ?? api.squareOffAllPositions;
    if (typeof fn !== 'function') {
      throw new Error('Square-off-all function is not available on api client.');
    }
    return fn();
  }, []);

  const openPositionsCount = portfolio?.openPositionsCount ?? positions.length;

  return {
    portfolio,
    positions,
    rawPositions,
    virtualCapital: portfolio?.virtualCapital ?? null,
    availableMargin: portfolio?.availableMargin ?? null,
    usedMargin: portfolio?.usedMargin ?? null,
    marginUtilizationPct: portfolio?.marginUtilizationPct ?? null,
    marginUtilPct: portfolio?.marginUtilPct ?? null,
    realizedPnl: portfolio?.realizedPnl ?? null,
    unrealizedPnl: portfolio?.unrealizedPnl ?? null,
    totalPnl: portfolio?.totalPnl ?? null,
    openPositionsCount,
    loading,
    refreshing,
    error,
    portfolioError,
    positionsError,
    lastUpdated,
    refresh: load,
    squareOffPosition,
    squareOffAll,
  };
}

export type UsePaperTradingReturn = ReturnType<typeof usePaperTrading>;
