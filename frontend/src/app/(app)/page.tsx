'use client';

import { useMarketData } from '@/hooks/useMarketData';
import { MarketCard } from '@/components/dashboard/MarketCard';
import DashboardTradingChart from '@/components/dashboard/DashboardTradingChart';
import { MLPredictionCard } from '@/components/dashboard/MLPredictionCard';
import { FIIPositioningCard } from '@/components/dashboard/FIIPositioningCard';
import { MarketBreadth } from '@/components/dashboard/MarketBreadth';
import { MarketOverview } from '@/components/dashboard/MarketOverview';
import { QuickStats } from '@/components/dashboard/QuickStats';
import { MarketHealth } from '@/components/dashboard/MarketHealth';

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

      {/* Main Chart + Right Sidebar (compact) */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4">
        {/* Left: TradingView Chart — smaller height as requested */}
        <div className="xl:col-span-8 bg-card rounded-lg border border-border overflow-hidden h-[420px] xl:h-[520px] flex flex-col shadow-sm">
          <DashboardTradingChart defaultSymbol="NIFTY 50" />
        </div>

        {/* Right: Market Overview / Breadth / Stats / Health — stacked, scrollable */}
        <div className="xl:col-span-4 flex flex-col gap-3 max-h-[520px] xl:overflow-y-auto xl:pr-1 custom-scrollbar">
          <MarketOverview marketStatus={marketStatus} health={health} loading={loading} />
          <MarketBreadth data={breadth} loading={loading} />
          <QuickStats health={health} marketStatus={marketStatus} lastFetch={lastFetch} loading={loading} />
          <MarketHealth health={health} loading={loading} />
        </div>
      </div>
    </div>
  );
}
