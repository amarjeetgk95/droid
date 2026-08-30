'use client';

import type { HpiStorageReport } from '@/lib/types';

export function StorageBudgetBar({ report }: { report: HpiStorageReport | null }) {
  if (!report) return null;
  const pct = Math.min(100, (report.current_storage_mb / report.hard_ceiling_mb) * 100);
  const targetPct = (report.target_mb / report.hard_ceiling_mb) * 100;
  const warnPct = (report.warning_mb / report.hard_ceiling_mb) * 100;
  const color = report.status === 'EXCEEDS_HARD' ? 'bg-red-500' : report.status === 'WARNING' ? 'bg-amber-500' : 'bg-green-500';

  return (
    <div className="bg-card border border-border rounded-xl p-4">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-sm font-bold">Storage Budget</h2>
        <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
          report.status === 'EXCEEDS_HARD' ? 'bg-red-500/10 text-red-500'
          : report.status === 'WARNING' ? 'bg-amber-500/10 text-amber-600'
          : 'bg-green-500/10 text-green-600'}`}>
          {report.status.replace('_', ' ')}
        </span>
      </div>
      <div className="relative h-3 rounded-full bg-muted overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
        <div className="absolute top-0 bottom-0 w-px bg-amber-500" style={{ left: `${warnPct}%` }} title={`Warning ${report.warning_mb} MB`} />
        <div className="absolute top-0 bottom-0 w-px bg-red-500/70" style={{ left: `${targetPct}%` }} title={`Target ${report.target_mb} MB`} />
      </div>
      <div className="flex justify-between mt-1 text-[10px] text-muted-foreground">
        <span>{report.current_storage_mb.toFixed(1)} MB used</span>
        <span>Target ≤ {report.target_mb} MB · Warning {report.warning_mb} MB · Ceiling {report.hard_ceiling_mb} MB</span>
      </div>
    </div>
  );
}
