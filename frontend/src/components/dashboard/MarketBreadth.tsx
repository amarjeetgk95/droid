import { MarketBreadthData } from '@/lib/types';
import { DataStatus } from '../common/DataStatus';

export function MarketBreadth({ data, loading }: { data: MarketBreadthData | null; loading: boolean }) {
  if (loading || !data) {
    return <div className="bg-card rounded-lg border border-border p-4 h-64 animate-pulse" />;
  }

  const total = data.advancing + data.declining + data.unchanged;
  const advPct = total > 0 ? (data.advancing / total) * 100 : 0;
  const decPct = total > 0 ? (data.declining / total) * 100 : 0;
  
  return (
    <div className="bg-card rounded-lg border border-border p-4">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-lg font-bold">Market Breadth</h2>
        <DataStatus status={data.status} />
      </div>
      
      <div className="flex justify-between mb-2 text-sm font-medium">
        <span className="text-success">Advances: {data.advancing}</span>
        <span className="text-muted-foreground">Unchanged: {data.unchanged}</span>
        <span className="text-danger">Declines: {data.declining}</span>
      </div>
      
      <div className="w-full h-3 rounded-full bg-muted flex overflow-hidden mb-6">
        <div className="bg-success h-full" style={{ width: `${advPct}%` }} />
        <div className="bg-danger h-full ml-auto" style={{ width: `${decPct}%` }} />
      </div>

      <div className="flex justify-between items-center mb-6 border-b border-border pb-4">
        <div>
          <p className="text-sm text-muted-foreground">A/D Ratio</p>
          <p className="text-xl font-bold tabular-nums">{data.advance_decline_ratio.toFixed(2)}</p>
        </div>
        <div className="text-right">
          <p className="text-sm text-muted-foreground">Sentiment</p>
          <p className="text-xl font-bold capitalize">{data.sentiment.replace('_', ' ')}</p>
        </div>
      </div>

      <div>
        <h3 className="text-sm font-semibold mb-2 text-muted-foreground">Sector Performance</h3>
        <div className="space-y-2">
          {data.sectors.map(sector => (
            <div key={sector.name} className="flex justify-between items-center text-sm">
              <span className="w-1/3 truncate">{sector.name}</span>
              <span className={`w-1/4 text-right tabular-nums ${sector.change_percent >= 0 ? 'text-success' : 'text-danger'}`}>
                {sector.change_percent > 0 ? '+' : ''}{sector.change_percent.toFixed(2)}%
              </span>
              <span className="w-1/3 text-right text-xs text-muted-foreground tabular-nums">
                <span className="text-success">{sector.advancing}</span> / <span className="text-danger">{sector.declining}</span>
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
