'use client';

import dynamic from 'next/dynamic';
import { useMarketDataContext } from '@/context/MarketDataContext';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { MarketCard } from '@/components/dashboard/MarketCard';
import { MarketBreadth } from '@/components/dashboard/MarketBreadth';
import { MarketOverview } from '@/components/dashboard/MarketOverview';
import { QuickStats } from '@/components/dashboard/QuickStats';
import { MarketHealth } from '@/components/dashboard/MarketHealth';

// Lazy-load heavy below-fold panels — reduces initial JS + defers 6 extra API calls until visible
const MLPredictionCard = dynamic(() => import('@/components/dashboard/MLPredictionCard').then(m => m.MLPredictionCard), { ssr: false, loading: () => <div className="bg-card border rounded-xl p-4 h-64 animate-pulse" /> });
const FIIPositioningCard = dynamic(() => import('@/components/dashboard/FIIPositioningCard').then(m => m.FIIPositioningCard), { ssr: false, loading: () => <div className="bg-card border rounded-xl p-4 h-64 animate-pulse" /> });
const MarketIntelligencePanel = dynamic(() => import('@/components/institutional/MarketIntelligencePanel').then(m => m.MarketIntelligencePanel), { ssr: false, loading: () => <div className="bg-card border rounded p-4 h-80 animate-pulse">Loading Market Intelligence…</div> });
const DataHealthPanel = dynamic(() => import('@/components/institutional/DataHealthPanel').then(m => m.DataHealthPanel), { ssr: false, loading: () => <div className="bg-card border rounded p-4 h-40 animate-pulse" /> });

function SectionError({ message }: { message: string }) {
  return (
    <div className="bg-card rounded-lg border border-destructive/30 p-4 flex flex-col items-center justify-center gap-2 min-h-32">
      <p className="text-sm font-semibold text-destructive">Failed to load this section</p>
      <p className="text-xs opacity-70 text-center">{message}</p>
    </div>
  );
}

export default function DashboardPage() {
  const { cards, breadth, health, marketStatus, loading, error, errors, lastFetch, refetch } = useMarketDataContext();

  if (error && !cards.length && !breadth && !health && !marketStatus) {
    // Everything failed — provide a retry path.
    return (
      <div className="flex items-center justify-center h-64 text-destructive bg-card rounded border border-destructive/20">
        <div className="text-center">
          <p className="text-lg font-semibold">Failed to load market data</p>
          <p className="text-sm mt-1 opacity-80">{error}</p>
          <p className="text-xs mt-2 opacity-60">Make sure the backend is running on port 8000</p>
          <button
            onClick={() => void refetch()}
            className="mt-4 px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors cursor-pointer"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Market Cards Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-4">
        {loading && !cards.length ? (
          // Skeleton loaders
          Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="bg-card rounded-lg border border-border p-4 h-48 animate-pulse">
              <div className="h-4 bg-muted rounded w-24 mb-3" />
              <div className="h-8 bg-muted rounded w-32 mb-2" />
              <div className="h-4 bg-muted rounded w-20" />
            </div>
          ))
        ) : cards.length ? (
          cards.map(card => (
            <ErrorBoundary key={card.symbol} label={`MarketCard:${card.symbol}`}>
              <MarketCard card={card} />
            </ErrorBoundary>
          ))
        ) : (
          <SectionError message={errors.cards ?? 'Market cards unavailable'} />
        )}
      </div>

      {/* Predictive ML & Institutional Analytics Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ErrorBoundary label="MLPredictionCard">
          <MLPredictionCard symbol="NIFTY" />
        </ErrorBoundary>
        <ErrorBoundary label="FIIPositioningCard">
          <FIIPositioningCard />
        </ErrorBoundary>
      </div>

      {/* Institutional Trading Intelligence Row — §71 Market Intelligence (§72 Data Health) — 4-asset universe */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-3"><ErrorBoundary label="MI:NIFTY"><MarketIntelligencePanel instrument="NIFTY" /></ErrorBoundary></div>
        <div className="lg:col-span-3"><ErrorBoundary label="MI:BANKNIFTY"><MarketIntelligencePanel instrument="BANKNIFTY" /></ErrorBoundary></div>
        <div className="lg:col-span-3"><ErrorBoundary label="MI:SENSEX"><MarketIntelligencePanel instrument="SENSEX" /></ErrorBoundary></div>
        <div className="lg:col-span-3"><ErrorBoundary label="MI:BTCUSD"><MarketIntelligencePanel instrument="BTCUSD" /></ErrorBoundary></div>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-4"><ErrorBoundary label="DataHealthPanel"><DataHealthPanel /></ErrorBoundary></div>
        <div className="lg:col-span-8 bg-card border rounded-lg p-4">
          <h3 className="font-bold text-sm tracking-widest uppercase mb-2">Signal & Execution</h3>
          <p className="text-xs text-muted-foreground">TTL ≤5s for fast breakout • Atomic FSM CAS • Fail-closed • Auditable — 4 pipelines isolated: NIFTY | BANKNIFTY | SENSEX | BTCUSD (24/7)</p>
          <p className="text-[11px] text-muted-foreground mt-2">Pipeline: POST /api/v1/institutional/pipeline/ingest — BTCUSD uses continuous CRYPTO pipeline, Indian indices use session-aware NSE pipeline</p>
        </div>
      </div>

      {/* Realtime-only view — charts removed (use TradingView), keep live tickers + market stats */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <ErrorBoundary label="MarketOverview">
          <MarketOverview marketStatus={marketStatus} health={health} loading={loading} />
        </ErrorBoundary>
        <ErrorBoundary label="MarketBreadth">
          <MarketBreadth data={breadth} loading={loading} />
        </ErrorBoundary>
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <ErrorBoundary label="QuickStats">
          <QuickStats health={health} marketStatus={marketStatus} lastFetch={lastFetch} loading={loading} />
        </ErrorBoundary>
        <ErrorBoundary label="MarketHealth">
          <MarketHealth health={health} loading={loading} />
        </ErrorBoundary>
      </div>
    </div>
  );
}
