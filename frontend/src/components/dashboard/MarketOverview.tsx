import { MarketStatusResponse, MarketHealthStatus } from '@/lib/types';
import { DataStatus } from '../common/DataStatus';
import { safeStr, safeTime } from '@/lib/utils';

export function MarketOverview({ marketStatus, health, loading }: { marketStatus: MarketStatusResponse | null; health: MarketHealthStatus | null; loading: boolean }) {
  if (loading || !marketStatus || !health) {
    return <div className="bg-card rounded-lg border border-border p-4 h-64 animate-pulse" />;
  }

  return (
    <div className="bg-card rounded-lg border border-border p-4 flex flex-col gap-4">
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-bold">Market Overview</h2>
        <DataStatus status={marketStatus.data_status} />
      </div>
      
      <div className="grid grid-cols-2 gap-4">
        <div className="p-3 bg-secondary rounded-lg">
          <p className="text-sm text-muted-foreground">Session</p>
          <p className="text-lg font-bold mt-1">{safeStr(marketStatus.session).replace('_', ' ')}</p>
        </div>
        <div className="p-3 bg-secondary rounded-lg">
          <p className="text-sm text-muted-foreground">Market Time</p>
          <p className="text-lg font-bold mt-1">{safeTime(marketStatus.market_time)}</p>
        </div>
      </div>

      <div className="p-3 border border-border rounded-lg mt-auto">
        <p className="text-sm text-muted-foreground mb-1">Market Regime</p>
        <p className="font-medium text-foreground">Coming in Phase 6</p>
      </div>
    </div>
  );
}
