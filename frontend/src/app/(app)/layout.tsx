'use client';

import { Sidebar } from '@/components/layout/Sidebar';
import { TopHeader } from '@/components/layout/TopHeader';
import { MarketTicker } from '@/components/layout/MarketTicker';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { useMarketData } from '@/hooks/useMarketData';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { cards, health, marketStatus, loading: dataLoading } = useMarketData();

  return (
    <AuthGuard>
      <div className="flex h-screen bg-background text-foreground overflow-hidden">
        <Sidebar />
        <div className="flex-1 flex flex-col overflow-hidden">
          <TopHeader
            health={health}
            marketStatus={marketStatus}
          />
          <MarketTicker cards={cards} loading={dataLoading} />
          <main className="flex-1 overflow-auto p-4">
            {children}
          </main>
        </div>
      </div>
    </AuthGuard>
  );
}
