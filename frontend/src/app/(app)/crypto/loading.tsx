import { Skeleton } from '@/components/ui/skeleton';

/**
 * Route-level loading boundary for Crypto Derivatives Desk (/crypto).
 * Matches the dual-hero BTC/ETH cards and split orderbook/derivatives panels.
 */
export default function CryptoLoading() {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Loading Crypto Derivatives">
      {/* Top Header & Market Toggle */}
      <div className="bg-card border border-border rounded-xl p-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Skeleton className="h-8 w-16 rounded-md" />
          <Skeleton className="h-8 w-32 rounded-md" />
        </div>
        <div className="flex items-center gap-2">
          <Skeleton className="h-7 w-20 rounded-lg" />
          <Skeleton className="h-8 w-24 rounded-lg" />
        </div>
      </div>

      {/* Global Macro Overview Strip */}
      <div className="bg-card border border-border rounded-xl p-3 flex items-center justify-between gap-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="flex-1 space-y-1">
            <Skeleton className="h-3 w-16" />
            <Skeleton className="h-5 w-24" />
          </div>
        ))}
      </div>

      {/* Hero Asset Cards Grid (Bitcoin & Ethereum) */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {[0, 1].map((i) => (
          <div key={i} className="h-40 bg-card border border-border rounded-2xl p-5 flex flex-col justify-between animate-pulse">
            <div className="flex items-center justify-between">
              <Skeleton className="h-5 w-28 rounded" />
              <Skeleton className="h-5 w-20 rounded" />
            </div>
            <div className="space-y-2">
              <Skeleton className="h-8 w-44 rounded" />
              <Skeleton className="h-3 w-32 rounded" />
            </div>
          </div>
        ))}
      </div>

      {/* Deep Analysis Split Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-7 bg-card border border-border rounded-xl p-5 h-80 animate-pulse" />
        <div className="lg:col-span-5 bg-card border border-border rounded-xl p-5 h-80 animate-pulse" />
      </div>
    </div>
  );
}
