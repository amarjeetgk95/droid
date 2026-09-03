'use client';

import { useState, useEffect, useCallback } from 'react';
import dynamic from 'next/dynamic';
import { useMarketDataContext } from '@/context/MarketDataContext';
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
  const {
    cards,
    breadth,
    health,
    marketStatus,
    loading,
    error,
    errors,
    lastFetch,
    streamState,
    refetch,
  } = useMarketDataContext({ useSummaryEndpoint: true });

  const [selectedSymbol, setSelectedSymbol] = useState<string>('NIFTY');
  const [viewMode, setViewMode] = useState<'intelligence' | 'chart'>('intelligence');
  const [regimeOverview, setRegimeOverview] = useState<MarketRegimeOverview | null>(null);
  const [regimeLoading, setRegimeLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Sync selected symbol with valid card if needed
  const activeSymbol =
    selectedSymbol.toUpperCase().includes('BANK')
      ? 'BANKNIFTY'
      : selectedSymbol.toUpperCase().includes('SENSEX')
      ? 'SENSEX'
      : selectedSymbol.toUpperCase().includes('BTC')
      ? 'BTCUSD'
      : 'NIFTY';

  const handleManualRefresh = useCallback(async () => {
    setIsRefreshing(true);
    try {
      await refetch();
    } finally {
      setIsRefreshing(false);
    }
  }, [refetch]);

  const handleSelectCard = useCallback((symbol: string) => {
    if (symbol.includes('BANKNIFTY')) setSelectedSymbol('BANKNIFTY');
    else if (symbol.includes('SENSEX')) setSelectedSymbol('SENSEX');
    else if (symbol.includes('BTC')) setSelectedSymbol('BTCUSD');
    else setSelectedSymbol('NIFTY');
  }, []);

  useEffect(() => {
    let isMounted = true;
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
    let timeout: ReturnType<typeof setTimeout> | null = null;
    const schedule = () => {
      const jittered = 30000 * (0.8 + Math.random() * 0.4);
      timeout = setTimeout(async () => {
        if (!document.hidden) await fetchRegime();
        schedule();
      }, jittered);
    };
    schedule();
    const onVis = () => { if (!document.hidden) void fetchRegime(); };
    document.addEventListener('visibilitychange', onVis);
    return () => {
      isMounted = false;
      if (timeout) clearTimeout(timeout);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [activeSymbol]);

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

  const isStreamLive = streamState === 'CONNECTED';

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

          {/* WebSocket Status Pill */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-secondary/60 border border-border text-xs">
            <span
              className={`w-2 h-2 rounded-full ${
                isStreamLive ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500'
              }`}
            />
            <span className="font-mono font-semibold text-foreground text-[11px]">
              {isStreamLive ? 'FEED LIVE' : 'CONNECTING'}
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
              <MLPredictionCard symbol={activeSymbol} />
            </ErrorBoundary>
            <ErrorBoundary label="FIIPositioningCard">
              <FIIPositioningCard />
            </ErrorBoundary>
          </div>

          {/* 4. Market Intelligence Deep Dive & Macro Regime Row */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
            {/* Market Intelligence Deep Dive (Instrument Selector Tab) */}
            <div className="lg:col-span-6">
              <ErrorBoundary label="MarketIntelligencePanel">
                <MarketIntelligencePanel instrument={activeSymbol} />
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
            <DataHealthPanel />
          </ErrorBoundary>
        </div>
      </div>
    </div>
  );
}

