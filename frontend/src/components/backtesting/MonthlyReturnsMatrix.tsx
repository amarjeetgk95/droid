'use client';

import { MonthlyPnlModel } from '@/lib/types';
import { Calendar } from 'lucide-react';

export function MonthlyReturnsMatrix({
  monthlyPnl,
}: {
  monthlyPnl: MonthlyPnlModel[];
}) {
  if (!monthlyPnl || monthlyPnl.length === 0) return null;

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-3 shadow-xs">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Calendar className="w-4 h-4 text-primary" />
          <h3 className="font-bold text-sm text-foreground">Monthly P&L & Performance Breakdown</h3>
        </div>
        <span className="text-xs text-muted-foreground font-mono">
          {monthlyPnl.length} Active Periods
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
        {monthlyPnl.map((m) => {
          const isPos = m.net_pnl >= 0;
          return (
            <div
              key={m.month_year}
              className={`p-3 rounded-xl border transition-all ${
                isPos
                  ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                  : 'bg-rose-500/10 border-rose-500/30 text-rose-400'
              }`}
            >
              <span className="text-xs font-bold font-mono text-foreground block">{m.month_year}</span>
              <div className="text-sm font-mono font-black mt-1">
                {isPos ? '+' : ''}₹{m.net_pnl.toLocaleString('en-IN')}
              </div>
              <div className="text-[10px] text-muted-foreground font-mono mt-1 flex justify-between">
                <span>{m.trades_count} Trades</span>
                <span>{m.win_rate_pct}% WR</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
