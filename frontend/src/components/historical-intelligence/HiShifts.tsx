'use client';

import * as React from 'react';
import { api } from '@/lib/api';
import type { HistoricalShiftsResponse } from '@/lib/types';
import { fmtDate, fmtNumber } from '@/lib/historical-intelligence/format';
import { Panel } from './Panel';
import { EmptyState } from './EmptyState';
import { Skeleton } from './Skeleton';

interface Props {
  symbol: string;
}

export function HiShifts({ symbol }: Props) {
  const [data, setData] = React.useState<HistoricalShiftsResponse | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const run = React.useCallback((sym: string) => {
    let cancelled = false;
    setLoading(true); setError(null); setData(null);
    api.getHistoricalShifts(sym, 10)
      .then((res) => { if (!cancelled) setData(res.data); })
      .catch((err) => { if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load shifts'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  React.useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    return run(symbol);
  }, [symbol, run]);

  if (loading && !data) return <Skeleton className="h-48 w-full" />;
  if (error) return <p className="text-xs text-red-500">{error}</p>;

  return (
    <Panel title={`Multi-session shifts — ${symbol}`} description="PCR, max pain, ATM IV, futures basis across recent sessions">
      {!data || data.shifts.length === 0 ? (
        <EmptyState title="No shift data" description="Collect a few sessions of data to see cross-day shifts." />
      ) : (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full text-xs">
            <thead className="bg-muted/50">
              <tr>
                <th className="text-left p-2 font-medium">Date</th>
                <th className="text-right p-2 font-medium">PCR (OI)</th>
                <th className="text-right p-2 font-medium">PCR (Vol)</th>
                <th className="text-right p-2 font-medium">Max pain</th>
                <th className="text-right p-2 font-medium">ATM IV</th>
                <th className="text-right p-2 font-medium">Basis</th>
                <th className="text-right p-2 font-medium">Spot</th>
              </tr>
            </thead>
            <tbody>
              {data.shifts.map((s, i) => (
                <tr key={i} className="border-t border-border/60">
                  <td className="p-2 text-muted-foreground">{fmtDate(s.date)}</td>
                  <td className="p-2 text-right tabular-nums">{s.pcr_oi.toFixed(2)}</td>
                  <td className="p-2 text-right tabular-nums">{s.pcr_volume.toFixed(2)}</td>
                  <td className="p-2 text-right tabular-nums">{fmtNumber(s.max_pain_strike)}</td>
                  <td className="p-2 text-right tabular-nums">{s.atm_iv.toFixed(2)}%</td>
                  <td className="p-2 text-right tabular-nums">{s.futures_basis.toFixed(2)}</td>
                  <td className="p-2 text-right tabular-nums">{s.spot_close.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}