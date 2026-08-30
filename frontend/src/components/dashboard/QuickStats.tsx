import { MarketHealthStatus, MarketStatusResponse } from '@/lib/types';
import { formatDistanceToNow } from 'date-fns';

export function QuickStats({ health, marketStatus, lastFetch, loading }: { health: MarketHealthStatus | null; marketStatus: MarketStatusResponse | null; lastFetch: Date | null; loading: boolean }) {
  if (loading || !health || !marketStatus) {
    return <div className="bg-card rounded-lg border border-border p-4 h-32 animate-pulse" />;
  }

  return (
    <div className="bg-card rounded-lg border border-border p-4">
      <h2 className="text-lg font-bold mb-4">Quick Stats</h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div>
          <p className="text-sm text-muted-foreground">Active Instruments</p>
          <p className="text-xl font-bold tabular-nums mt-1">{health.active_instruments}</p>
        </div>
        <div>
          <p className="text-sm text-muted-foreground">Data Age</p>
          <p className="text-xl font-bold tabular-nums mt-1">{health.data_age_seconds !== null ? `${health.data_age_seconds}s` : 'N/A'}</p>
        </div>
        <div>
          <p className="text-sm text-muted-foreground">Provider</p>
          <p className="text-xl font-bold mt-1">{health.provider}</p>
        </div>
        <div>
          <p className="text-sm text-muted-foreground">Last Updated</p>
          <p className="text-xl font-bold mt-1 text-sm">{lastFetch ? formatDistanceToNow(lastFetch, { addSuffix: true }) : 'Never'}</p>
        </div>
      </div>
    </div>
  );
}
