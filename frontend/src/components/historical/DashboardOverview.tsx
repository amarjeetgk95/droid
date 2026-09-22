'use client';

import { Database, HardDrive, ShieldCheck, AlertTriangle, Layers, Activity } from 'lucide-react';
import type { HistoricalDataset, HistoricalDownloadJob } from '@/lib/api/historical';
import { AutoSyncCard } from './AutoSyncCard';

interface DashboardOverviewProps {
  datasets: HistoricalDataset[];
  jobs: HistoricalDownloadJob[];
  onNavigateTab: (tab: string) => void;
  onRefreshData?: () => void;
}

export function DashboardOverview({ datasets, jobs, onNavigateTab, onRefreshData }: DashboardOverviewProps) {
  const totalCandles = datasets.reduce((sum, d) => sum + (d.total_candles || 0), 0);
  const totalStorage = datasets.reduce((sum, d) => sum + (d.storage_bytes || 0), 0);
  const storageMb = (totalStorage / (1024 * 1024)).toFixed(1);

  const avgQuality = datasets.length > 0
    ? (datasets.reduce((sum, d) => sum + (d.latest_quality_score || 0), 0) / datasets.length).toFixed(1)
    : '100.0';

  const totalOpenGaps = datasets.reduce((sum, d) => sum + (d.open_gaps || 0), 0);
  const activeJobs = jobs.filter((j) => j.status === 'RUNNING' || j.status === 'QUEUED').length;

  const statCards = [
    {
      title: 'Managed Datasets',
      value: datasets.length,
      icon: Database,
      desc: 'Active index and asset series',
      color: 'text-primary',
    },
    {
      title: 'Total Candles',
      value: totalCandles.toLocaleString(),
      icon: Layers,
      desc: 'Validated normalized records',
      color: 'text-bull',
    },
    {
      title: 'Parquet Storage',
      value: `${storageMb} MB`,
      icon: HardDrive,
      desc: 'Snappy-compressed columnar disk',
      color: 'text-foreground',
    },
    {
      title: 'Average Quality Score',
      value: `${avgQuality}%`,
      icon: ShieldCheck,
      desc: 'Two-tier gating & completeness',
      color: Number(avgQuality) >= 95 ? 'text-bull' : 'text-bear',
    },
    {
      title: 'Open Session Gaps',
      value: totalOpenGaps,
      icon: AlertTriangle,
      desc: 'Targeted repairable omissions',
      color: totalOpenGaps === 0 ? 'text-bull' : 'text-bear',
    },
    {
      title: 'Active Ingestion Jobs',
      value: activeJobs,
      icon: Activity,
      desc: 'Live download background tasks',
      color: activeJobs > 0 ? 'text-primary' : 'text-muted-foreground',
    },
  ];

  return (
    <div className="space-y-6">
      {/* Auto-Sync Ingestion Service Banner */}
      <AutoSyncCard onSyncComplete={onRefreshData} />

      {/* Stat Cards Grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {statCards.map((card, idx) => {
          const Icon = card.icon;
          return (
            <div
              key={idx}
              className="relative overflow-hidden rounded-xl border border-border bg-card p-5 shadow-sm transition-all hover:border-primary/50"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-muted-foreground">{card.title}</span>
                <Icon className={`h-4 w-4 ${card.color}`} />
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className={`text-2xl font-bold tracking-tight ${card.color}`}>
                  {card.value}
                </span>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">{card.desc}</p>
            </div>
          );
        })}
      </div>

      {/* Quick Action Panels */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="rounded-xl border border-border bg-card p-5">
          <h3 className="text-sm font-semibold text-foreground">Priority Dataset: SENSEX 1-Minute</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            Acquire previous 12 months of high-fidelity 1-minute historical candles from FYERS API v3. Enforces 09:15–15:29 session boundary and zero-volume index spot rules.
          </p>
          <div className="mt-4 flex gap-2">
            <button
              onClick={() => onNavigateTab('download')}
              className="rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"
            >
              Configure Download
            </button>
            <button
              onClick={() => onNavigateTab('datasets')}
              className="rounded-lg border border-border bg-muted px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent"
            >
              View Catalog
            </button>
          </div>
        </div>

        <div className="rounded-xl border border-border bg-card p-5">
          <h3 className="text-sm font-semibold text-foreground">Integrity & Reproducibility</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            Every completed download generates an immutable dataset version tagged with a cryptographic SHA-256 checksum and deep pipeline lineage for backtesting safety.
          </p>
          <div className="mt-4 flex gap-2">
            <button
              onClick={() => onNavigateTab('gaps')}
              className="rounded-lg border border-border bg-muted px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent"
            >
              Inspect Session Gaps
            </button>
            <button
              onClick={() => onNavigateTab('jobs')}
              className="rounded-lg border border-border bg-muted px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent"
            >
              Monitor Jobs
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
