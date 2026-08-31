'use client';

import * as React from 'react';
import { Lightbulb, Activity, ShieldCheck } from 'lucide-react';
import type { HpiDerivative, HpiStorageReport, HpiUniverse, HpiAuditEntry } from '@/lib/types';
import { fmtMb, fmtNumber, fmtRelative } from '@/lib/historical-intelligence/format';
import { categoryLabel } from '@/lib/historical-intelligence/labels';
import { Panel } from './Panel';
import { StatusPill } from './StatusPill';
import { EmptyState } from './EmptyState';
import { Skeleton } from './Skeleton';

interface Props {
  universe: HpiUniverse | null;
  report: HpiStorageReport | null;
  audit: HpiAuditEntry[];
  loading: boolean;
  onJumpToSection: (s: 'datasets' | 'patterns' | 'audit') => void;
  onOpenImport: (symbol: string) => void;
}

export function HiOverview({ universe, report, audit, loading, onJumpToSection, onOpenImport }: Props) {
  if (loading && !report) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="rounded-xl border border-border bg-card p-4 space-y-2">
              <Skeleton className="h-3 w-20" />
              <Skeleton className="h-6 w-28" />
            </div>
          ))}
        </div>
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  const totalRecords = report?.datasets.reduce((acc, d) => acc + d.records_stored, 0) ?? 0;
  const enabledCount = report?.datasets.filter((d) => d.enabled).length ?? 0;
  const totalCategories = universe?.derivatives.reduce((acc, d) => acc + d.data_categories.length, 0) ?? 0;
  const populatedCategories =
    report?.datasets.reduce(
      (acc, d) => acc + d.category_stats.filter((c) => c.records > 0).length,
      0
    ) ?? 0;

  const firstRunEnabled = enabledCount === 0;

  return (
    <div className="space-y-4">
      {firstRunEnabled && (
        <Panel tone="primary">
          <div className="flex items-start gap-3">
            <Lightbulb className="w-5 h-5 text-primary shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-semibold">Welcome to Historical Intelligence</p>
              <p className="text-xs text-muted-foreground mt-1">
                Pick the derivatives you want to track, choose which data categories to import, then load historical candles. The pattern engine activates once enough data is in.
              </p>
              <ol className="mt-3 grid gap-2 sm:grid-cols-3 text-xs">
                <li className="rounded-md border border-border bg-background p-2">
                  <span className="text-[10px] text-muted-foreground">Step 1</span>
                  <p className="font-medium mt-0.5">Enable derivatives</p>
                  <button onClick={() => onJumpToSection('datasets')} className="mt-1 text-primary hover:underline">Go to Datasets →</button>
                </li>
                <li className="rounded-md border border-border bg-background p-2">
                  <span className="text-[10px] text-muted-foreground">Step 2</span>
                  <p className="font-medium mt-0.5">Import historical data</p>
                  <p className="text-muted-foreground mt-0.5">Pick a period and sampling</p>
                </li>
                <li className="rounded-md border border-border bg-background p-2">
                  <span className="text-[10px] text-muted-foreground">Step 3</span>
                  <p className="font-medium mt-0.5">Analyse patterns</p>
                  <button onClick={() => onJumpToSection('patterns')} className="mt-1 text-primary hover:underline">Open Patterns →</button>
                </li>
              </ol>
            </div>
          </div>
        </Panel>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Kpi label="Storage used" value={fmtMb(report?.current_storage_mb ?? null)} sub={`of ${report?.hard_ceiling_mb ?? 200} MB ceiling`} />
        <Kpi label="Total records" value={fmtNumber(totalRecords)} sub={`${enabledCount}/${report?.datasets.length ?? 0} derivatives`} />
        <Kpi label="Categories tracked" value={`${populatedCategories} / ${totalCategories}`} sub="with stored records" />
        <Kpi label="Deletions logged" value={String(audit.length)} sub="audit entries" />
      </div>

      <Panel
        title="Coverage matrix"
        description="One row per derivative, one column per data category. Click a populated cell to import more or analyse."
        actions={
          <button onClick={() => onJumpToSection('datasets')} className="text-xs text-primary hover:underline">Manage datasets →</button>
        }
      >
        {report && universe ? (
          <CoverageMatrix universe={universe} report={report} onOpenImport={onOpenImport} />
        ) : (
          <EmptyState title="No coverage data" />
        )}
      </Panel>

      <Panel
        title="Recent activity"
        description="Last 10 deletion events from the audit log"
        actions={
          <button onClick={() => onJumpToSection('audit')} className="text-xs text-primary hover:underline">Full audit log →</button>
        }
      >
        {audit.length === 0 ? (
          <EmptyState
            icon={<Activity className="w-6 h-6" />}
            title="No activity yet"
            description="Deletions and labelling runs will appear here."
          />
        ) : (
          <ul className="space-y-1.5">
            {audit.slice(0, 10).map((a) => (
              <li key={a.deletion_id} className="flex items-center gap-2 text-xs bg-muted/40 rounded-md px-3 py-2">
                <ShieldCheck className="w-3.5 h-3.5 text-amber-600 shrink-0" />
                <span className="font-semibold">{a.derivative}</span>
                <span className="text-muted-foreground">{categoryLabel(a.dataset)}</span>
                <span className="ml-auto text-muted-foreground">{a.records_deleted.toLocaleString()} rec · {a.storage_released_mb} MB · {fmtRelative(a.timestamp)}</span>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}

function Kpi({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="text-xl font-bold mt-1 tabular-nums">{value}</p>
      {sub && <p className="text-[10px] text-muted-foreground mt-0.5">{sub}</p>}
    </div>
  );
}

function CoverageMatrix({ universe, report, onOpenImport }: { universe: HpiUniverse; report: HpiStorageReport; onOpenImport: (sym: string) => void }) {
  const categories = Array.from(new Set(universe.derivatives.flatMap((d) => d.data_categories)));
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr>
            <th className="text-left p-2 text-muted-foreground font-medium">Derivative</th>
            {categories.map((c) => (
              <th key={c} className="p-2 text-muted-foreground font-medium text-center" title={categoryLabel(c)}>
                <span className="hidden sm:inline">{categoryLabel(c)}</span>
                <span className="sm:hidden">{c.split('_')[0]}</span>
              </th>
            ))}
            <th className="p-2 text-muted-foreground font-medium text-right">Records</th>
          </tr>
        </thead>
        <tbody>
          {universe.derivatives.map((d: HpiDerivative) => {
            const card = report.datasets.find((ds) => ds.symbol === d.symbol);
            const recCount = card?.records_stored ?? 0;
            return (
              <tr key={d.symbol} className="border-t border-border/60">
                <td className="p-2 font-semibold">{d.display_name}</td>
                {categories.map((c) => {
                  const stat = card?.category_stats.find((s) => s.category === c);
                  const tone = card?.enabled === false
                    ? 'muted'
                    : !stat || stat.records === 0
                    ? 'muted'
                    : stat.protected
                    ? 'warn'
                    : 'ok';
                  const label = card?.enabled === false
                    ? 'Disabled'
                    : !stat || stat.records === 0
                    ? 'Empty'
                    : `${stat.records.toLocaleString()} rec`;
                  return (
                    <td key={c} className="p-1 text-center">
                      <button
                        onClick={() => onOpenImport(d.symbol)}
                        disabled={!card?.enabled}
                        className="w-full rounded-md p-1.5 disabled:cursor-not-allowed hover:bg-secondary/50 disabled:hover:bg-transparent"
                        aria-label={`${d.display_name} ${categoryLabel(c)} ${label}`}
                      >
                        <StatusPill tone={tone} label={label} />
                      </button>
                    </td>
                  );
                })}
                <td className="p-2 text-right tabular-nums">{recCount.toLocaleString()}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}