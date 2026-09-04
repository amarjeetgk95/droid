'use client';

import { createContext, useContext, useState, useEffect, useMemo, useCallback, ReactNode, useRef } from 'react';
import { api } from '@/lib/api';
import type { IndexCard, MarketBreadthData, MarketHealthStatus, MarketStatusResponse, MarketRegimeOverview } from '@/lib/types';
import { useMarketStream, type StreamConnectionState, type TimestampedTick } from '@/hooks/useMarketStream';

type SectionErrors = {
  cards: string | null;
  breadth: string | null;
  health: string | null;
  marketStatus: string | null;
};

type MarketDataContextType = {
  /**
   * REST snapshot cards (Tier A snapshot, updates on quiet sync cadence).
   * Live tick-merged prices live in LiveMarketContext — prefer
   * useLiveMarketContext().cards for ticker / price displays to avoid
   * re-rendering analytical panels on every tick.
   * @deprecated Use useLiveMarketContext().cards for live prices.
   */
  cards: IndexCard[];
  breadth: MarketBreadthData | null;
  health: MarketHealthStatus | null;
  marketStatus: MarketStatusResponse | null;
  regimeOverview: MarketRegimeOverview | null;
  mlPrediction: any | null;
  fiiDii: any | null;
  loading: boolean;
  /** First non-null section error — back-compat convenience. */
  error: string | null;
  /** Per-section errors — a failing endpoint no longer blanks the whole page. */
  errors: SectionErrors;
  lastFetch: Date | null;
  streamState: StreamConnectionState;
  /** True when real MARKET_TICKS (not just heartbeats) arrived within staleness window. */
  ticksFresh: boolean;
  refreshInterval: number;
  setRefreshInterval: (ms: number) => void;
  refetch: () => Promise<void>;
};

/**
 * Raw WS tick snapshot — separate context so per-tick updates do NOT
 * re-render MarketData consumers (analytical panels, layout). Only the
 * LiveMarketProvider consumes this (and batches it to ≤10 renders/sec).
 */
type MarketTicksSnapshot = {
  ticks: Record<string, TimestampedTick>;
  lastTickAt: Date | null;
};

const MarketTicksContext = createContext<MarketTicksSnapshot>({ ticks: {}, lastTickAt: null });

export function useMarketTicks(): MarketTicksSnapshot {
  return useContext(MarketTicksContext);
}

const MarketDataContext = createContext<MarketDataContextType | null>(null);

const DEFAULT_REFRESH_MS = 5000;

const EMPTY_ERRORS: SectionErrors = { cards: null, breadth: null, health: null, marketStatus: null };

const errMessage = (err: unknown) => (err instanceof Error ? err.message : 'Failed to fetch market data');

export function MarketDataProvider({ children, refreshInterval = DEFAULT_REFRESH_MS, useSummaryEndpoint = true }: { children: ReactNode; refreshInterval?: number; useSummaryEndpoint?: boolean }) {
  const [cards, setCards] = useState<IndexCard[]>([]);
  const [breadth, setBreadth] = useState<MarketBreadthData | null>(null);
  const [health, setHealth] = useState<MarketHealthStatus | null>(null);
  const [marketStatus, setMarketStatus] = useState<MarketStatusResponse | null>(null);
  const [regimeOverview, setRegimeOverview] = useState<MarketRegimeOverview | null>(null);
  const [mlPrediction, setMlPrediction] = useState<any | null>(null);
  const [fiiDii, setFiiDii] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState<SectionErrors>(EMPTY_ERRORS);
  const [lastFetch, setLastFetch] = useState<Date | null>(null);
  const [activeInterval, setActiveInterval] = useState<number>(refreshInterval);

  // Authoritative WS owner: this is the SINGLE market-feed WebSocket in the
  // app. LiveMarketProvider consumes this state (no second socket) and the
  // adaptive REST scheduler below reads its health directly.
  const { latestTicks, streamState, ticksFresh, lastTickAt } = useMarketStream();
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

        const nextErrors: SectionErrors = {
          cards: summaryData?.errors?.cards ?? (summaryData ? null : 'Dashboard summary unavailable'),
          breadth: summaryData?.errors?.breadth ?? (summaryData ? null : 'Dashboard summary unavailable'),
          health: summaryData?.errors?.health ?? (summaryData ? null : 'Dashboard summary unavailable'),
          marketStatus: summaryData?.errors?.status ?? (summaryData ? null : 'Dashboard summary unavailable'),
        };

        if (summaryData) {
          // REST snapshot only — no WS tick merge here. Live prices come from
          // LiveMarketContext so analytical panels stay referentially stable.
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
          if (summaryData.regime_overview && mountedRef.current) setRegimeOverview(summaryData.regime_overview as MarketRegimeOverview);
          if (summaryData.ml_prediction && mountedRef.current) setMlPrediction(summaryData.ml_prediction);
          if (summaryData.fii_dii && mountedRef.current) setFiiDii(summaryData.fii_dii);
        }
        setErrors(nextErrors);
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

    // Adaptive scheduler:
    // When WebSocket is CONNECTED and ticks are fresh, REST only needs a quiet sync (25s).
    // When WebSocket is disconnected or connecting, REST polls at 5s fallback.
    // When document.hidden, completely pause polling.
    const schedule = () => {
      if (typeof document !== 'undefined' && document.hidden) return;
      const isLiveWs = streamState === 'CONNECTED' && ticksFresh;
      const baseInterval = isLiveWs ? 25000 : Math.max(4000, activeInterval);
      const jitter = baseInterval * (0.85 + Math.random() * 0.3); // ±15% jitter
      timeout = setTimeout(() => {
        void fetchData();
        schedule();
      }, jitter);
    };

    void fetchData();
    schedule();

    const onVisibility = () => {
      if (!document.hidden) {
        void fetchData(); // refetch immediately when tab becomes visible
        if (timeout) clearTimeout(timeout);
        schedule();
      } else {
        if (timeout) clearTimeout(timeout);
      }
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      mountedRef.current = false;
      if (timeout) clearTimeout(timeout);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [activeInterval, fetchData, streamState, ticksFresh]);

  const value = useMemo<MarketDataContextType>(() => ({
    cards,
    breadth,
    health,
    marketStatus,
    regimeOverview,
    mlPrediction,
    fiiDii,
    loading,
    error: errors.cards ?? errors.breadth ?? errors.health ?? errors.marketStatus,
    errors,
    lastFetch,
    streamState,
    ticksFresh,
    refreshInterval: activeInterval,
    setRefreshInterval: setActiveInterval,
    refetch: fetchData,
  }), [cards, breadth, health, marketStatus, regimeOverview, mlPrediction, fiiDii, loading, errors, lastFetch, streamState, ticksFresh, activeInterval, fetchData]);

  // NOTE: ticks snapshot is memoised separately and provided via
  // MarketTicksContext so per-tick updates never invalidate `value` above.
  const ticksSnapshot = useMemo<MarketTicksSnapshot>(
    () => ({ ticks: latestTicks, lastTickAt }),
    [latestTicks, lastTickAt],
  );

  return (
    <MarketTicksContext.Provider value={ticksSnapshot}>
      <MarketDataContext.Provider value={value}>{children}</MarketDataContext.Provider>
    </MarketTicksContext.Provider>
  );
}

export function useMarketDataContext(options?: { useSummaryEndpoint?: boolean }) {
  const ctx = useContext(MarketDataContext);
  if (!ctx) throw new Error('useMarketDataContext must be used within MarketDataProvider');
  return ctx;
}

export function useOptionalMarketDataContext() {
  return useContext(MarketDataContext);
}

/** Semantic aliases for Phase 4 architecture clarity. */
export const DashboardDataContext = MarketDataContext;
export const DashboardDataProvider = MarketDataProvider;
export const useDashboardDataContext = useMarketDataContext;
export const useOptionalDashboardDataContext = useOptionalMarketDataContext;

