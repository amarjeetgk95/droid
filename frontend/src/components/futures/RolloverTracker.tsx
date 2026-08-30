'use client';

import { RolloverMetrics } from '@/lib/types';
import { RefreshCw, CheckCircle2, AlertCircle, Clock } from 'lucide-react';

export function RolloverTracker({
  rollover,
}: {
  rollover: RolloverMetrics | null;
}) {
  if (!rollover) {
    return (
      <div className="bg-card border border-border rounded-xl p-6 text-center text-muted-foreground">
        No rollover metrics available for this instrument.
      </div>
    );
  }

  const rollPct = rollover.rollover_percent;
  const benchmark = rollover.three_month_avg_rollover;
  const pace = rollover.rollover_pace;

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-4 shadow-xs">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <RefreshCw className="w-4 h-4 text-success" />
          <h3 className="font-bold text-sm text-foreground">Monthly Rollover Pace & Spread Tracker</h3>
        </div>
        <span className={`text-xs px-2.5 py-0.5 rounded-full font-bold flex items-center gap-1 ${
          pace === 'AHEAD' ? 'bg-emerald-500/20 text-emerald-400' :
          pace === 'BEHIND' ? 'bg-amber-500/20 text-amber-400' : 'bg-primary/20 text-primary'
        }`}>
          {pace === 'AHEAD' ? <CheckCircle2 className="w-3 h-3" /> :
           pace === 'BEHIND' ? <AlertCircle className="w-3 h-3" /> : <Clock className="w-3 h-3" />}
          Rollover Pace: {pace}
        </span>
      </div>

      {/* Progress Bars */}
      <div className="space-y-3 bg-secondary/40 p-4 rounded-lg border border-border">
        {/* Current Rollover Progress */}
        <div className="space-y-1">
          <div className="flex justify-between text-xs font-semibold">
            <span className="text-foreground">Current Expiry Rollover:</span>
            <span className="font-mono text-primary font-bold">{rollPct}%</span>
          </div>
          <div className="w-full bg-secondary h-2.5 rounded-full overflow-hidden">
            <div
              style={{ width: `${Math.min(100, rollPct)}%` }}
              className="bg-primary h-full transition-all duration-500 rounded-full"
            />
          </div>
        </div>

        {/* 3-Month Benchmark Progress */}
        <div className="space-y-1">
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>3-Month Historical Benchmark Pace:</span>
            <span className="font-mono">{benchmark}%</span>
          </div>
          <div className="w-full bg-secondary h-1.5 rounded-full overflow-hidden">
            <div
              style={{ width: `${Math.min(100, benchmark)}%` }}
              className="bg-muted-foreground/60 h-full rounded-full"
            />
          </div>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
        <div className="bg-secondary/60 p-3 rounded-lg border border-border">
          <span className="text-muted-foreground block text-[11px]">Rollover Spread Cost</span>
          <span className="font-bold text-foreground font-mono text-sm">
            {rollover.rollover_spread > 0 ? '+' : ''}₹{rollover.rollover_spread}
          </span>
          <span className="text-[10px] text-muted-foreground block">Next Month Premium</span>
        </div>

        <div className="bg-secondary/60 p-3 rounded-lg border border-border">
          <span className="text-muted-foreground block text-[11px]">Total Futures Open Interest</span>
          <span className="font-bold text-foreground font-mono text-sm">
            {rollover.total_futures_oi.toLocaleString('en-IN')}
          </span>
          <span className="text-[10px] text-muted-foreground block">Near + Next + Far Contracts</span>
        </div>

        <div className="bg-secondary/60 p-3 rounded-lg border border-border col-span-2 sm:col-span-1">
          <span className="text-muted-foreground block text-[11px]">Next Contract Expiry</span>
          <span className="font-bold text-foreground font-mono text-sm">
            {rollover.expiry}
          </span>
          <span className="text-[10px] text-muted-foreground block">Monthly Settlement</span>
        </div>
      </div>
    </div>
  );
}
