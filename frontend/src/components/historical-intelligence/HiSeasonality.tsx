'use client';

import * as React from 'react';
import { TrendingUp, TrendingDown } from 'lucide-react';
import { api } from '@/lib/api';
import type { SeasonalityResponse } from '@/lib/types';
import { Panel } from './Panel';
import { EmptyState } from './EmptyState';
import { Skeleton } from './Skeleton';

interface Props {
  symbol: string;
}

export function HiSeasonality({ symbol }: Props) {
  const [data, setData] = React.useState<SeasonalityResponse | null>(null);
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    api.getSeasonality(symbol)
      .then((res) => { if (!cancelled) setData(res.data); })
      .catch(() => { if (!cancelled) setData(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [symbol]);

  if (loading && !data) return <Skeleton className="h-48 w-full" />;
  if (!data || data.days.length === 0) return <EmptyState title="No seasonality data" />;

  const maxAbs = Math.max(...data.days.map((d) => Math.abs(d.avg_return_pct)), 1);

  return (
    <Panel
      title={`Day-of-week seasonality — ${symbol}`}
      description={`Best day for buyers: ${data.best_day_for_buyers} · sellers: ${data.best_day_for_sellers}`}
    >
      <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
        {data.days.map((d) => {
          const positive = d.avg_return_pct >= 0;
          const widthPct = (Math.abs(d.avg_return_pct) / maxAbs) * 50;
          return (
            <li key={d.day_name} className="rounded-md border border-border bg-background p-3">
              <div className="flex items-center gap-2">
                {positive ? <TrendingUp className="w-3.5 h-3.5 text-green-600" /> : <TrendingDown className="w-3.5 h-3.5 text-red-500" />}
                <p className="font-semibold text-sm">{d.day_name}</p>
              </div>
              <div className="mt-2 flex h-2 rounded-full overflow-hidden bg-muted">
                <div className="flex-1 flex justify-end">
                  {!positive && <div className="bg-red-500 h-full" style={{ width: `${widthPct}%` }} />}
                </div>
                <div className="flex-1">
                  {positive && <div className="bg-green-500 h-full" style={{ width: `${widthPct}%` }} />}
                </div>
              </div>
              <p className={`mt-1 text-sm font-bold tabular-nums ${positive ? 'text-green-600' : 'text-red-500'}`}>
                {positive ? '+' : ''}{d.avg_return_pct.toFixed(2)}%
              </p>
              <p className="text-[10px] text-muted-foreground mt-0.5">
                Win {d.win_rate_pct.toFixed(0)}% · Range {d.avg_range_pts.toFixed(0)} pts · Vol {d.volatility_pct.toFixed(1)}%
              </p>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}