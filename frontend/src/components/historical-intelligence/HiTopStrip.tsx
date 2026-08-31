'use client';

import * as React from 'react';
import type { HpiStorageReport } from '@/lib/types';
import { storageStatus } from '@/lib/historical-intelligence/labels';
import { fmtMb } from '@/lib/historical-intelligence/format';
import { StorageBar } from './StorageBar';
import { StatusPill } from './StatusPill';
import { Skeleton } from './Skeleton';

interface Props {
  report: HpiStorageReport | null;
  loading?: boolean;
}

export function HiTopStrip({ report, loading }: Props) {
  if (loading && !report) {
    return (
      <div className="flex items-center gap-4 rounded-xl border border-border bg-card px-4 py-3">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-2.5 flex-1" />
        <Skeleton className="h-4 w-24" />
      </div>
    );
  }
  if (!report) return null;

  const status = storageStatus(report.status);
  const totalRecords = report.datasets.reduce((acc, d) => acc + d.records_stored, 0);
  const enabledCount = report.datasets.filter((d) => d.enabled).length;

  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-xl border border-border bg-card px-4 py-3">
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-muted-foreground">Storage</span>
        <span className="text-sm font-bold tabular-nums">{fmtMb(report.current_storage_mb)}</span>
        <span className="text-[10px] text-muted-foreground">/ {report.hard_ceiling_mb} MB</span>
        <StatusPill tone={status.tone} label={status.label} />
      </div>

      <div className="flex-1 min-w-[160px] max-w-md">
        <StorageBar
          currentMb={report.current_storage_mb}
          targetMb={report.target_mb}
          warningMb={report.warning_mb}
          hardCeilingMb={report.hard_ceiling_mb}
          status={report.status}
        />
      </div>

      <div className="flex items-center gap-4 text-xs text-muted-foreground">
        <span><strong className="text-foreground font-semibold tabular-nums">{totalRecords.toLocaleString('en-IN')}</strong> records</span>
        <span><strong className="text-foreground font-semibold tabular-nums">{enabledCount}</strong> / {report.datasets.length} derivatives enabled</span>
      </div>
    </div>
  );
}