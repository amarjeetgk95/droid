'use client';

import { useState, useEffect } from 'react';
import { Sidebar } from '@/components/layout/Sidebar';
import { TopHeader } from '@/components/layout/TopHeader';
import { MarketTicker } from '@/components/layout/MarketTicker';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { MarketDataProvider, useMarketDataContext } from '@/context/MarketDataContext';

const SIDEBAR_COLLAPSED_KEY = 'droid:sidebar:collapsed';

function AppLayoutInner({ children }: { children: React.ReactNode }) {
  const { cards, health, marketStatus, loading: dataLoading, streamState } = useMarketDataContext();
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
          <MarketTicker cards={cards} loading={dataLoading} />
          <main className="flex-1 overflow-auto p-4">
            {children}
          </main>
        </div>
      </div>
  );
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <MarketDataProvider>
      <AuthGuard>
        <AppLayoutInner>{children}</AppLayoutInner>
      </AuthGuard>
    </MarketDataProvider>
  );
}
