import { Skeleton } from '@/components/ui/skeleton';

/**
 * OptionChainSkeleton
 *
 * High-fidelity structural skeleton that precisely matches the 13-column
 * layout of OptionChainTable (Calls CE | Strike Spine | Puts PE).
 * Eliminates Cumulative Layout Shift (CLS) when loading option chains.
 */
export function OptionChainSkeleton({ rows = 10 }: { rows?: number }) {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Loading option chain">
      {/* Top Header Controls Wireframe */}
      <div className="bg-card border border-border rounded-xl p-4 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Skeleton className="h-9 w-32 rounded-lg" />
          <Skeleton className="h-9 w-40 rounded-lg" />
        </div>
        <div className="flex items-center gap-2">
          <Skeleton className="h-8 w-24 rounded-lg" />
          <Skeleton className="h-8 w-24 rounded-lg" />
          <Skeleton className="h-8 w-28 rounded-lg" />
        </div>
      </div>

      {/* Main Table Matrix Skeleton */}
      <div className="bg-card border border-border rounded-xl shadow-xs overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left border-collapse">
            {/* Top Super-Header */}
            <thead>
              <tr className="border-b border-border/60 text-center font-bold">
                <th colSpan={6} className="py-2.5 px-3 bg-primary/5 text-primary">
                  CALLS (CE)
                </th>
                <th className="py-2.5 px-4 bg-secondary font-black border-x border-border">
                  STRIKE
                </th>
                <th colSpan={6} className="py-2.5 px-3 bg-amber-500/5 text-amber-500">
                  PUTS (PE)
                </th>
              </tr>
              {/* Column Headers */}
              <tr className="border-b border-border text-[11px] font-semibold text-muted-foreground bg-muted/40">
                <th className="py-2 px-2 text-right">OI</th>
                <th className="py-2 px-2 text-right">Vol</th>
                <th className="py-2 px-2 text-right">Bid</th>
                <th className="py-2 px-2 text-right">Ask</th>
                <th className="py-2 px-2 text-right">LTP</th>
                <th className="py-2 px-2 text-right">IV%</th>
                <th className="py-2 px-4 text-center font-bold bg-secondary/80 border-x border-border">Strike</th>
                <th className="py-2 px-2 text-right">IV%</th>
                <th className="py-2 px-2 text-right">LTP</th>
                <th className="py-2 px-2 text-right">Bid</th>
                <th className="py-2 px-2 text-right">Ask</th>
                <th className="py-2 px-2 text-right">Vol</th>
                <th className="py-2 px-2 text-right">OI</th>
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: rows }).map((_, i) => (
                <tr
                  key={i}
                  className={`border-b border-border/40 ${
                    i === Math.floor(rows / 2) ? 'bg-primary/5' : i % 2 === 0 ? 'bg-card' : 'bg-muted/10'
                  }`}
                >
                  {/* Calls CE Skeletons */}
                  <td className="py-2 px-2 text-right"><Skeleton className="h-3 w-12 ml-auto" /></td>
                  <td className="py-2 px-2 text-right"><Skeleton className="h-3 w-10 ml-auto" /></td>
                  <td className="py-2 px-2 text-right"><Skeleton className="h-3 w-10 ml-auto" /></td>
                  <td className="py-2 px-2 text-right"><Skeleton className="h-3 w-10 ml-auto" /></td>
                  <td className="py-2 px-2 text-right"><Skeleton className="h-3.5 w-14 ml-auto" /></td>
                  <td className="py-2 px-2 text-right"><Skeleton className="h-3 w-8 ml-auto" /></td>

                  {/* Strike Spine Skeleton */}
                  <td className="py-2 px-4 text-center font-bold bg-secondary/40 border-x border-border">
                    <Skeleton className="h-4 w-16 mx-auto" />
                  </td>

                  {/* Puts PE Skeletons */}
                  <td className="py-2 px-2 text-right"><Skeleton className="h-3 w-8 ml-auto" /></td>
                  <td className="py-2 px-2 text-right"><Skeleton className="h-3.5 w-14 ml-auto" /></td>
                  <td className="py-2 px-2 text-right"><Skeleton className="h-3 w-10 ml-auto" /></td>
                  <td className="py-2 px-2 text-right"><Skeleton className="h-3 w-10 ml-auto" /></td>
                  <td className="py-2 px-2 text-right"><Skeleton className="h-3 w-10 ml-auto" /></td>
                  <td className="py-2 px-2 text-right"><Skeleton className="h-3 w-12 ml-auto" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
