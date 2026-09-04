'use client';

import { useState, useEffect } from 'react';
import { Sidebar } from '@/components/layout/Sidebar';
import { TopHeader } from '@/components/layout/TopHeader';
import { MarketTicker } from '@/components/layout/MarketTicker';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { MarketDataProvider, useMarketDataContext } from '@/context/MarketDataContext';
import { LiveMarketProvider, useLiveMarketContext } from '@/context/LiveMarketContext';

const SIDEBAR_COLLAPSED_KEY = 'droid:sidebar:collapsed';

function AppLayoutInner({ children }: { children: React.ReactNode }) {
  // Subscribe only to stable low-frequency state here so tick updates
  // (LiveMarketContext.cards) don't re-render the whole layout.
  // MarketTicker consumes live cards directly via useLiveMarketContext.
  const { health, marketStatus } = useMarketDataContext();
  const { streamState } = useLiveMarketContext();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    try {
      setCollapsed(localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1');
    } catch {}
  }, []);

  const handleCollapsedChange = (v: boolean) => {
    setCollapsed(v);
    try {
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, v ? '1' : '0');
    } catch {}
  };

  return (
    <div className="flex h-screen bg-background text-foreground overflow-hidden">
      <Sidebar collapsed={collapsed} onCollapsedChange={handleCollapsedChange} mobileOpen={mobileOpen} onMobileOpenChange={setMobileOpen} />
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        <TopHeader
          health={health}
          marketStatus={marketStatus}
          streamState={streamState}
          onMenuClick={() => setMobileOpen(true)}
        />
        <MarketTicker />
        <main className="flex-1 overflow-auto p-4">
          {children}
        </main>
      </div>
    </div>
  );
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  // MarketData owns the dashboard/summary REST fetch + market-feed WebSocket
  // (single owner). LiveMarket consumes that shared state for tick-merged
  // cards — it opens no socket and issues no summary request of its own.
  return (
    <MarketDataProvider refreshInterval={5000} useSummaryEndpoint={true}>
      <LiveMarketProvider>
        <AuthGuard>
          <AppLayoutInner>{children}</AppLayoutInner>
        </AuthGuard>
      </LiveMarketProvider>
    </MarketDataProvider>
  );
}
