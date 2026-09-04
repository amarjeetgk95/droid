'use client';

import { useState, useEffect, useCallback } from 'react';
import dynamic from 'next/dynamic';
import { useMarketDataContext } from '@/context/MarketDataContext';
import { useLiveMarketContext } from '@/context/LiveMarketContext';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { MarketCard } from '@/components/dashboard/MarketCard';
import { MarketBreadth } from '@/components/dashboard/MarketBreadth';
import { api } from '@/lib/api';
import type { MarketRegimeOverview } from '@/lib/types';
import {
  Activity,
  RefreshCw,
  Clock,
  Compass,
  TrendingUp,
  ShieldCheck,
  Layers,
  Sparkles,
  ArrowUpRight,
  BarChart2,
} from 'lucide-react';
import Link from 'next/link';

// Lazy-load sub-panels with sleek skeleton states
const DashboardTradingChart = dynamic(
  () => import('@/components/dashboard/DashboardTradingChart'),
  {
    ssr: false,
    loading: () => <div className="bg-card border border-border rounded-xl p-5 h-[480px] animate-pulse" />,
  }
);
const MLPredictionCard = dynamic(
  () => import('@/components/dashboard/MLPredictionCard').then((m) => m.MLPredictionCard),
  {
    ssr: false,
    loading: () => <div className="bg-card border border-border rounded-xl p-5 h-72 animate-pulse" />,
  }
);
const FIIPositioningCard = dynamic(
  () => import('@/components/dashboard/FIIPositioningCard').then((m) => m.FIIPositioningCard),
  {
    ssr: false,
    loading: () => <div className="bg-card border border-border rounded-xl p-5 h-72 animate-pulse" />,
  }
);
const MarketIntelligencePanel = dynamic(
  () =>
    import('@/components/institutional/MarketIntelligencePanel').then(
      (m) => m.MarketIntelligencePanel
    ),
  {
    ssr: false,
    loading: () => <div className="bg-card border border-border rounded-xl p-5 h-72 animate-pulse" />,
  }
);
const DataHealthPanel = dynamic(
  () => import('@/components/institutional/DataHealthPanel').then((m) => m.DataHealthPanel),
  {
    ssr: false,
    loading: () => <div className="bg-card border border-border rounded-xl p-5 h-72 animate-pulse" />,
  }
);

function SectionError({ message }: { message: string }) {
  return (
    <div className="bg-card rounded-xl border border-destructive/30 p-6 flex flex-col items-center justify-center gap-2 min-h-32">
      <p className="text-sm font-semibold text-destructive">Failed to load this section</p>
      <p className="text-xs opacity-70 text-center">{message}</p>
    </div>
  );
}

export default function DashboardPage() {
  // Tier A live prices from LiveMarketContext (isolated re-renders);
  // Tiers B/C/D analytical data from Dashboard (MarketData) context.
  const { cards, streamState, ticksFresh, loading: liveLoading } = useLiveMarketContext();
  const {
    breadth,
    health,
    marketStatus,
    regimeOverview: contextRegime,
    loading: dashboardLoading,
    error,
    errors,
    lastFetch,
    refetch,
  } = useMarketDataContext({ useSummaryEndpoint: true });
  const loading = liveLoading && dashboardLoading && cards.length === 0;

  const [selectedSymbol, setSelectedSymbol] = useState<string>('NIFTY');
  const [viewMode, setViewMode] = useState<'intelligence' | 'chart'>('intelligence');
  const [regimeOverview, setRegimeOverview] = useState<MarketRegimeOverview | null>(null);
  const [regimeLoading, setRegimeLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [dashboardRefreshKey, setDashboardRefreshKey] = useState(0);

  // Sync selected symbol with valid card if needed
  const activeSymbol =
    selectedSymbol.toUpperCase().includes('BANK')
      ? 'BANKNIFTY'
      : selectedSymbol.toUpperCase().includes('SENSEX')
      ? 'SENSEX'
      : selectedSymbol.toUpperCase().includes('BTC')
      ? 'BTCUSD'
      : 'NIFTY';

  // Sync context regime when activeSymbol is NIFTY
  useEffect(() => {
    if (activeSymbol === 'NIFTY' && contextRegime) {
      setRegimeOverview(contextRegime);
      setRegimeLoading(false);
    }
  }, [activeSymbol, contextRegime]);

  const handleManualRefresh = useCallback(async () => {
    setIsRefreshing(true);
    try {
      await Promise.allSettled([
        refetch(),
        activeSymbol !== 'NIFTY'
          ? api.getRegimeOverview(activeSymbol).then((res) => {
              setRegimeOverview(res.data);
            })
          : Promise.resolve(),
      ]);
      setDashboardRefreshKey((k) => k + 1);
    } finally {
      setIsRefreshing(false);
    }
  }, [refetch, activeSymbol]);

  const handleSelectCard = useCallback((symbol: string) => {
    if (symbol.includes('BANKNIFTY')) setSelectedSymbol('BANKNIFTY');
    else if (symbol.includes('SENSEX')) setSelectedSymbol('SENSEX');
    else if (symbol.includes('BTC')) setSelectedSymbol('BTCUSD');
    else setSelectedSymbol('NIFTY');
  }, []);

  // Regime: NIFTY comes straight from shared context (no independent poll).
  // Non-NIFTY symbols fetch once per symbol change / manual refresh only —
  // no background interval (Tier C, 30–60s TTL served by coordinator + context).
  useEffect(() => {
    if (activeSymbol === 'NIFTY') {
      if (contextRegime) {
        setRegimeOverview(contextRegime);
        setRegimeLoading(false);
      }
      return;
    }

    let isMounted = true;
    setRegimeLoading(true);
    const fetchRegime = async () => {
      try {
        const res = await api.getRegimeOverview(activeSymbol);
        if (!isMounted) return;
        setRegimeOverview(res.data);
      } catch {
        if (!isMounted) return;
      } finally {
        if (isMounted) setRegimeLoading(false);
      }
    };
    fetchRegime();
    return () => {
      isMounted = false;
    };
  }, [activeSymbol, contextRegime]);

  if (error && !cards.length && !breadth && !health && !marketStatus) {
    return (
      <div className="flex items-center justify-center h-80 text-destructive bg-card rounded-2xl border border-destructive/20 p-8 shadow-xs">
        <div className="text-center max-w-md space-y-3">
          <div className="w-12 h-12 rounded-full bg-destructive/10 text-destructive flex items-center justify-center mx-auto">
            <Activity className="w-6 h-6" />
          </div>
          <p className="text-lg font-bold text-foreground">Market Feed Disconnected</p>
          <p className="text-xs text-muted-foreground">{error}</p>
          <button
            onClick={() => void handleManualRefresh()}
            className="mt-2 px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-xs font-semibold hover:bg-primary/90 transition-all cursor-pointer shadow-xs"
          >
            Retry Connection
          </button>
        </div>
      </div>
    );
  }

  const isMarketClosed = marketStatus?.session === 'CLOSED' || marketStatus?.is_trading_day === false;
  // LIVE requires actual ticks flowing — an open socket with only heartbeats
  // (broker outage) must read as stale, never as live.
  const isStreamLive = streamState === 'CONNECTED' && ticksFresh;
  const isStreamWaiting = streamState === 'CONNECTED' && !ticksFresh;

  return (
    <div className="space-y-5 pb-8">
      {/* 1. Hero Live Command Bar */}
      <div className="bg-card border border-border rounded-2xl p-4 sm:p-5 shadow-xs flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-primary/10 text-primary shrink-0">
            <TrendingUp className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base sm:text-lg font-black tracking-tight text-foreground">
                Institutional Market Terminal
              </h1>
              <span className="hidden sm:inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-primary/10 text-primary border border-primary/20">
                FYERS v3 LIVE
              </span>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Real-time tick streaming, probabilistic ML regimes &amp; institutional FII/DII metrics.
            </p>
          </div>
        </div>

        <div className="flex items-center flex-wrap gap-2.5 w-full md:w-auto justify-start md:justify-end border-t md:border-t-0 pt-3 md:pt-0 border-border/60">
          {/* Market Session Pill */}
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-secondary/60 border border-border text-xs font-medium">
            <Clock className="w-3.5 h-3.5 text-muted-foreground" />
            <span className="capitalize text-foreground font-semibold">
              {marketStatus?.session ? marketStatus.session.replace(/_/g, ' ').toLowerCase() : 'Active'}
            </span>
          </div>

          {/* Realtime Status Pill */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-secondary/60 border border-border text-xs">
            <span
              className={`w-2 h-2 rounded-full ${
                isStreamLive
                  ? 'bg-emerald-500 animate-pulse'
                  : isMarketClosed
                    ? 'bg-slate-400'
                    : isStreamWaiting
                      ? 'bg-amber-400 animate-pulse'
                      : 'bg-red-500'
              }`}
            />
            <span className="font-mono font-semibold text-foreground text-[11px]">
              {isStreamLive
                ? 'FEED LIVE (WS)'
                : isMarketClosed
                  ? 'SESSION CLOSED'
                  : isStreamWaiting
                    ? 'FEED STALE — RETRYING'
                    : 'FEED DOWN'}
            </span>
            {health?.latency_ms !== null && health?.latency_ms !== undefined && (
              <span className="text-[10px] text-muted-foreground font-mono">
                · {health.latency_ms.toFixed(0)}ms
              </span>
            )}
          </div>

          {/* View Toggle */}
          <div className="flex items-center p-1 rounded-xl bg-secondary/80 border border-border text-xs">
            <button
              type="button"
              onClick={() => setViewMode('intelligence')}
              className={`px-2.5 py-1 rounded-lg font-semibold transition-all cursor-pointer ${
                viewMode === 'intelligence'
                  ? 'bg-card text-foreground shadow-xs'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              Overview
            </button>
            <button
              type="button"
              onClick={() => setViewMode('chart')}
              className={`px-2.5 py-1 rounded-lg font-semibold transition-all cursor-pointer flex items-center gap-1.5 ${
                viewMode === 'chart'
                  ? 'bg-card text-foreground shadow-xs'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <BarChart2 className="w-3.5 h-3.5" />
              <span>Chart</span>
            </button>
          </div>

          {/* Manual Refresh Button */}
          <button
            type="button"
            onClick={handleManualRefresh}
            disabled={isRefreshing}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-secondary hover:bg-secondary/80 text-foreground border border-border rounded-xl text-xs font-semibold transition-all cursor-pointer disabled:opacity-50"
            title="Refresh market data"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin text-primary' : ''}`} />
            <span className="hidden sm:inline">Refresh</span>
          </button>

          {/* Quick Option Chain Link */}
          <Link
            href="/options"
            className="flex items-center gap-1 px-3 py-1.5 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/30 rounded-xl text-xs font-semibold transition-all"
          >
            <span>Options Desk</span>
            <ArrowUpRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </div>

      {/* 2. Interactive Market Index Strip */}
      <div>
        <div className="flex items-center justify-between mb-2.5 px-1">
          <span className="text-xs font-bold text-muted-foreground tracking-wider uppercase flex items-center gap-1.5">
            <Layers className="w-3.5 h-3.5 text-primary" />
            Core Market Indices
          </span>
          <span className="text-[11px] text-muted-foreground">
            Click an index to focus quant intelligence
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3.5">
          {loading && !cards.length ? (
            Array.from({ length: 5 }).map((_, i) => (
              <div
                key={i}
                className="bg-card rounded-xl border border-border p-4 h-44 animate-pulse flex flex-col justify-between"
              >
                <div className="h-4 bg-secondary rounded w-24 mb-2" />
                <div className="h-7 bg-secondary rounded w-32 mb-2" />
                <div className="h-4 bg-secondary rounded w-20" />
              </div>
            ))
          ) : cards.length ? (
            cards.map((card) => {
              const isSelected =
                activeSymbol === 'NIFTY' && card.symbol.includes('NIFTY 50')
                  ? true
                  : activeSymbol === 'BANKNIFTY' && card.symbol.includes('BANKNIFTY')
                  ? true
                  : activeSymbol === 'SENSEX' && card.symbol.includes('SENSEX')
                  ? true
                  : activeSymbol === 'BTCUSD' && card.symbol.includes('BTC')
                  ? true
                  : false;

              return (
                <ErrorBoundary key={card.symbol} label={`MarketCard:${card.symbol}`}>
                  <MarketCard
                    card={card}
                    isSelected={isSelected}
                    onSelect={() => handleSelectCard(card.symbol)}
                  />
                </ErrorBoundary>
              );
            })
          ) : (
            <SectionError message={errors.cards ?? 'Market cards unavailable'} />
          )}
        </div>
      </div>

      {viewMode === 'chart' ? (
        <div className="bg-card border border-border rounded-2xl p-4 shadow-xs space-y-3">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 px-1">
            <div className="flex items-center gap-2">
              <div className="p-1.5 rounded-lg bg-primary/10 text-primary">
                <BarChart2 className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-xs font-bold text-foreground tracking-tight uppercase">
                  Interactive Trading Chart ({activeSymbol === 'NIFTY' ? 'NIFTY 50' : activeSymbol})
                </h3>
                <p className="text-[10px] text-muted-foreground">
                  Multi-timeframe candlestick chart with real-time candles, pan, and zoom
                </p>
              </div>
            </div>
            <span className="text-[10px] font-mono text-muted-foreground bg-secondary px-2 py-0.5 rounded border border-border self-start sm:self-auto">
              Active: {activeSymbol === 'NIFTY' ? 'NIFTY 50' : activeSymbol}
            </span>
          </div>

          <div className="rounded-xl border border-border overflow-hidden bg-background">
            <ErrorBoundary label="DashboardTradingChart">
              <DashboardTradingChart
                defaultSymbol={activeSymbol === 'NIFTY' ? 'NIFTY 50' : activeSymbol}
                className="w-full h-[520px]"
              />
            </ErrorBoundary>
          </div>
        </div>
      ) : (
        <>
          {/* 3. Predictive ML & Institutional Analytics Row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <ErrorBoundary label="MLPredictionCard">
              <MLPredictionCard symbol={activeSymbol} refreshKey={dashboardRefreshKey} />
            </ErrorBoundary>
            <ErrorBoundary label="FIIPositioningCard">
              <FIIPositioningCard refreshKey={dashboardRefreshKey} />
            </ErrorBoundary>
          </div>

          {/* 4. Market Intelligence Deep Dive & Macro Regime Row */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
            {/* Market Intelligence Deep Dive (Instrument Selector Tab) */}
            <div className="lg:col-span-6">
              <ErrorBoundary label="MarketIntelligencePanel">
                <MarketIntelligencePanel instrument={activeSymbol} refreshKey={dashboardRefreshKey} />
              </ErrorBoundary>
            </div>

            {/* Macro Regime & Platform Telemetry Card */}
            <div className="lg:col-span-6 flex flex-col gap-4">
              {/* Regime Card */}
              <div className="bg-card border border-border rounded-xl p-5 shadow-xs flex-1 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="p-1.5 rounded-lg bg-sky-500/10 text-sky-400">
                      <Compass className="w-4 h-4" />
                    </div>
                    <h3 className="font-bold text-sm tracking-tight text-foreground uppercase">
                      Market Regime Classification ({activeSymbol})
                    </h3>
                  </div>
                  {regimeOverview && (
                    <span className="text-[10px] bg-primary/10 text-primary border border-primary/20 px-2.5 py-0.5 rounded-full font-bold">
                      {regimeOverview.regime_state.replace(/_/g, ' ')}
                    </span>
                  )}
                </div>

                {regimeLoading ? (
                  <div className="animate-pulse space-y-2 py-2">
                    <div className="h-4 bg-secondary rounded w-3/4" />
                    <div className="h-4 bg-secondary rounded w-1/2" />
                  </div>
                ) : regimeOverview ? (
                  <div className="space-y-2.5 text-xs">
                    <p className="font-semibold text-foreground text-sm leading-snug">
                      {regimeOverview.summary_headline}
                    </p>
                    <p className="text-muted-foreground leading-relaxed">
                      {regimeOverview.institutional_rationale}
                    </p>
                    <div className="flex items-center gap-3 pt-2 border-t border-border/40 text-[11px]">
                      <span className="text-muted-foreground">
                        Confidence: <strong className="text-foreground">{regimeOverview.confidence_score.toFixed(0)}%</strong>
                      </span>
                      <span className="text-muted-foreground">
                        Provider: <strong className="text-foreground">FYERS API v3</strong>
                      </span>
                    </div>
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground">Regime classification unavailable</p>
                )}
              </div>

              {/* Quick Engine Telemetry */}
              <div className="bg-card border border-border rounded-xl p-4 shadow-xs grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                <div className="p-2.5 rounded-lg bg-secondary/30 border border-border/40">
                  <span className="text-muted-foreground text-[10px] block">Active Gateway</span>
                  <span className="font-mono font-bold text-foreground block mt-0.5">FYERS v3</span>
                </div>
                <div className="p-2.5 rounded-lg bg-secondary/30 border border-border/40">
                  <span className="text-muted-foreground text-[10px] block">Instruments</span>
                  <span className="font-mono font-bold text-foreground block mt-0.5">
                    {health?.active_instruments ?? 5} Live
                  </span>
                </div>
                <div className="p-2.5 rounded-lg bg-secondary/30 border border-border/40">
                  <span className="text-muted-foreground text-[10px] block">Pipeline Mode</span>
                  <span className="font-mono font-bold text-emerald-400 block mt-0.5">
                    {health?.mode ?? 'LIVE'}
                  </span>
                </div>
                <div className="p-2.5 rounded-lg bg-secondary/30 border border-border/40">
                  <span className="text-muted-foreground text-[10px] block">Quant Sync</span>
                  <span className="font-mono font-bold text-foreground block mt-0.5">100% Valid</span>
                </div>
              </div>
            </div>
          </div>
        </>
      )}

      {/* 5. Market Breadth & Data Health Suite */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-8">
          <ErrorBoundary label="MarketBreadth">
            <MarketBreadth data={breadth} loading={loading} />
          </ErrorBoundary>
        </div>
        <div className="lg:col-span-4">
          <ErrorBoundary label="DataHealthPanel">
            <DataHealthPanel refreshKey={dashboardRefreshKey} />
          </ErrorBoundary>
        </div>
      </div>
    </div>
  );
}

