'use client';

import { useMarketData } from '@/hooks/useMarketData';
import { MarketCard } from '@/components/dashboard/MarketCard';
import { MLPredictionCard } from '@/components/dashboard/MLPredictionCard';
import { FIIPositioningCard } from '@/components/dashboard/FIIPositioningCard';
import { MarketBreadth } from '@/components/dashboard/MarketBreadth';
import { MarketOverview } from '@/components/dashboard/MarketOverview';
import { QuickStats } from '@/components/dashboard/QuickStats';
import { MarketHealth } from '@/components/dashboard/MarketHealth';
import { MarketIntelligencePanel } from '@/components/institutional/MarketIntelligencePanel';
import { DataHealthPanel } from '@/components/institutional/DataHealthPanel';

export default function DashboardPage() {
  const { cards, breadth, health, marketStatus, loading, error, lastFetch } = useMarketData();

  if (error) {
    return (
      <div className="flex items-center justify-center h-64 text-destructive bg-card rounded border border-destructive/20">
        <div className="text-center">
          <p className="text-lg font-semibold">Failed to load market data</p>
          <p className="text-sm mt-1 opacity-80">{error}</p>
          <p className="text-xs mt-2 opacity-60">Make sure the backend is running on port 8000</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Market Cards Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-4">
        {loading ? (
          // Skeleton loaders
          Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="bg-card rounded-lg border border-border p-4 h-48 animate-pulse">
              <div className="h-4 bg-muted rounded w-24 mb-3" />
              <div className="h-8 bg-muted rounded w-32 mb-2" />
              <div className="h-4 bg-muted rounded w-20" />
            </div>
          ))
        ) : (
          cards.map(card => (
            <MarketCard key={card.symbol} card={card} />
          ))
        )}
      </div>

      {/* Predictive ML & Institutional Analytics Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <MLPredictionCard symbol="NIFTY" />
        <FIIPositioningCard />
      </div>

      {/* Institutional Trading Intelligence Row — §71 Market Intelligence (§72 Data Health) — 4-asset universe */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-3"><MarketIntelligencePanel instrument="NIFTY" /></div>
        <div className="lg:col-span-3"><MarketIntelligencePanel instrument="BANKNIFTY" /></div>
        <div className="lg:col-span-3"><MarketIntelligencePanel instrument="SENSEX" /></div>
        <div className="lg:col-span-3"><MarketIntelligencePanel instrument="BTCUSD" /></div>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-4"><DataHealthPanel /></div>
        <div className="lg:col-span-8 bg-card border rounded-lg p-4">
          <h3 className="font-bold text-sm tracking-widest uppercase mb-2">Signal & Execution</h3>
          <p className="text-xs text-muted-foreground">TTL ≤5s for fast breakout • Atomic FSM CAS • Fail-closed • Auditable — 4 pipelines isolated: NIFTY | BANKNIFTY | SENSEX | BTCUSD (24/7)</p>
          <p className="text-[11px] text-muted-foreground mt-2">Pipeline: POST /api/v1/institutional/pipeline/ingest — BTCUSD uses continuous CRYPTO pipeline, Indian indices use session-aware NSE pipeline</p>
        </div>
      </div>

      {/* Realtime-only view — charts removed (use TradingView), keep live tickers + market stats */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <MarketOverview marketStatus={marketStatus} health={health} loading={loading} />
        <MarketBreadth data={breadth} loading={loading} />
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <QuickStats health={health} marketStatus={marketStatus} lastFetch={lastFetch} loading={loading} />
        <MarketHealth health={health} loading={loading} />
      </div>
    </div>
  );
}
