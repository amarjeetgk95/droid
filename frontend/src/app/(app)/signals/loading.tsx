import { Skeleton } from '@/components/ui/skeleton';

/**
 * Route-level loading boundary for Signal Center (/signals).
 * Matches the filter strip and 4-column alpha opportunity cards grid.
 */
export default function SignalsLoading() {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Loading Signal Center">
      {/* Top Controls & Filter Strip */}
      <div className="bg-card border border-border rounded-xl p-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {['ALL', 'NIFTY', 'BANKNIFTY', 'STOCKS', 'CRYPTO'].map((f) => (
            <Skeleton key={f} className="h-8 w-18 rounded-lg" />
          ))}
        </div>
        <div className="flex items-center gap-2">
          <Skeleton className="h-8 w-28 rounded-lg" />
          <Skeleton className="h-8 w-24 rounded-lg" />
        </div>
      </div>

      {/* 4-Column Signal Cards Grid Skeleton */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3.5">
        {Array.from({ length: 8 }).map((_, i) => (
          <div
            key={i}
            className="bg-card border border-border rounded-xl p-4 space-y-3 shadow-xs animate-pulse"
          >
            {/* Header: Symbol + Side Badge */}
            <div className="flex items-center justify-between">
              <Skeleton className="h-5 w-24 rounded" />
              <Skeleton className="h-5 w-14 rounded-full" />
            </div>

            {/* Strategy & Confidence */}
            <div className="space-y-1.5">
              <Skeleton className="h-3 w-32 rounded" />
              <Skeleton className="h-2 w-full rounded-full" />
            </div>

            {/* Entry, Target, Stop Loss Strip */}
            <div className="grid grid-cols-3 gap-2 pt-2 border-t border-border/50">
              <div>
                <Skeleton className="h-2.5 w-10 mb-1" />
                <Skeleton className="h-4 w-14" />
              </div>
              <div>
                <Skeleton className="h-2.5 w-10 mb-1" />
                <Skeleton className="h-4 w-14" />
              </div>
              <div>
                <Skeleton className="h-2.5 w-10 mb-1" />
                <Skeleton className="h-4 w-14" />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
