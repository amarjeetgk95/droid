'use client';

import * as React from 'react';
import { AlertTriangle, CheckCircle2, Info } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

/* ── Signal status badge — single mapping shared by MI page + panel ── */
const STATUS_VARIANT: Record<string, 'success' | 'default' | 'secondary' | 'outline' | 'destructive'> = {
  CONFIRMED: 'success',
  TRIGGERED: 'default',
  POSSIBLE_BREAKOUT: 'default',
  POSSIBLE_BREAKDOWN: 'default',
  POSSIBLE: 'default',
  WATCH: 'secondary',
  PREPARING: 'secondary',
  CONFLICTED: 'destructive',
  REJECTED: 'outline',
  NO_SETUP: 'outline',
  EXPIRED: 'outline',
  FAILED: 'outline',
  INVALIDATED: 'outline',
};

export function SignalStatusBadge({ status, className }: { status?: string | null; className?: string }) {
  const s = status || 'WATCH';
  return (
    <Badge variant={STATUS_VARIANT[s] ?? 'secondary'} className={cn('tracking-widest', className)}>
      {s}
    </Badge>
  );
}

/* ── Feed health — dot + label driven by backend feed/data-quality ── */
export function FeedHealthBadge({
  feed,
  quality,
  showLabel = true,
  className,
}: {
  feed?: string | null;
  quality?: string | null;
  showLabel?: boolean;
  className?: string;
}) {
  const degraded = feed === 'FEED_DEGRADED' || quality === 'FEED_DEGRADED';
  const live = !degraded && (feed === 'HEALTHY' || feed === 'LIVE') && (quality === 'LIVE' || quality === 'RECENT' || !quality);
  const label = degraded ? 'FEED DEGRADED' : quality === 'RECENT' ? 'RECENT' : feed === 'HEALTHY' ? 'HEALTHY' : (feed || quality || 'UNKNOWN');
  const dot = degraded ? 'bg-destructive' : live ? (quality === 'LIVE' || !quality ? 'bg-emerald-500 animate-pulse' : 'bg-emerald-500') : 'bg-amber-400';
  return (
    <span className={cn('inline-flex items-center gap-1.5', className)}>
      <span className={cn('w-2 h-2 rounded-full shrink-0', dot)} />
      {showLabel && <span className="text-xs font-mono font-bold text-foreground">{label}</span>}
    </span>
  );
}

/* ── Score meter — accessible Progress with tone + tabular numerals ── */
const TONE_BAR: Record<string, string> = {
  emerald: 'bg-emerald-500',
  sky: 'bg-sky-500',
  red: 'bg-red-500',
  primary: 'bg-primary',
  amber: 'bg-amber-400',
};

export function ScoreMeter({
  label,
  value,
  tone = 'primary',
  hint,
}: {
  label: string;
  value: number | null | undefined;
  tone?: keyof typeof TONE_BAR | string;
  hint?: string;
}) {
  const v = value ?? 0;
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-mono font-bold tabular-nums">{value ?? '—'}{value != null ? ' / 100' : ''}</span>
      </div>
      <Progress value={v} indicatorClassName={TONE_BAR[tone] ?? TONE_BAR.primary} aria-label={`${label} ${v} of 100`} />
      {hint ? <p className="text-[11px] text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

/* ── Metric tile — the one tile style for the whole workspace ── */
export function MetricTile({ label, value, sub }: { label: string; value: React.ReactNode; sub?: React.ReactNode }) {
  return (
    <div className="bg-secondary/40 border border-border/60 rounded-lg p-3">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="font-mono font-bold mt-1 tabular-nums break-words">{value}</div>
      {sub ? <div className="text-[11px] text-muted-foreground mt-0.5">{sub}</div> : null}
    </div>
  );
}

/* ── Section card — Card + icon title + optional action ── */
export function MiSection({
  icon: Icon,
  title,
  action,
  children,
  className,
  tone,
}: {
  icon?: React.ComponentType<{ className?: string }>;
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  tone?: 'default' | 'success' | 'warning' | 'muted' | 'destructive';
}) {
  const toneCls =
    tone === 'success'
      ? 'border-emerald-500/50 bg-emerald-500/5 dark:bg-emerald-500/10'
      : tone === 'warning'
        ? 'border-amber-500/40 bg-amber-500/5 dark:bg-amber-500/10'
        : tone === 'destructive'
          ? 'border-destructive/40 bg-destructive/5 dark:bg-destructive/10'
          : tone === 'muted'
            ? 'bg-muted/40 opacity-80'
            : '';
  return (
    <Card className={cn('gap-4 py-4', toneCls, className)}>
      <CardHeader className="px-4 flex-row items-center justify-between gap-2">
        <CardTitle className="text-xs tracking-widest uppercase flex items-center gap-2">
          {Icon && <Icon className="w-4 h-4 shrink-0" />}
          {title}
        </CardTitle>
        {action}
      </CardHeader>
      <CardContent className="px-4">{children}</CardContent>
    </Card>
  );
}

/* ── Evidence lists — icon-led, no emoji ── */
export function EvidenceList({
  items,
  tone,
  emptyText,
}: {
  items: { signal: string; detail?: string }[];
  tone: 'support' | 'conflict';
  emptyText: string;
}) {
  if (!items.length) return emptyText ? <p className="text-xs text-muted-foreground mt-2">{emptyText}</p> : null;
  const Icon = tone === 'support' ? CheckCircle2 : AlertTriangle;
  const iconCls = tone === 'support' ? 'text-emerald-500' : 'text-amber-500';
  return (
    <ul className="mt-2 space-y-1.5">
      {items.map((e, i) => (
        <li key={i} className="text-xs flex gap-2">
          <Icon className={cn('w-3.5 h-3.5 shrink-0 mt-0.5', iconCls)} />
          <span>
            <span className="font-medium">{e.signal}</span>
            {e.detail ? <span className="text-muted-foreground"> — {e.detail}</span> : null}
          </span>
        </li>
      ))}
    </ul>
  );
}

/* ── Unavailable notice — honest, token-safe ── */
export function MiUnavailable({ reason, className }: { reason?: string | null; className?: string }) {
  return (
    <p className={cn('text-[11px] text-muted-foreground mt-2 flex items-start gap-1.5', className)}>
      <Info className="w-3.5 h-3.5 shrink-0 mt-px" />
      <span>Unavailable this poll — {reason || 'no reading from broker feed'}. Retries automatically; no values are fabricated.</span>
    </p>
  );
}

/* ── Workspace skeleton — per-section shape, not a blank pulse ── */
export function MiWorkspaceSkeleton() {
  return (
    <div className="space-y-4" aria-label="Loading market intelligence">
      <Card className="gap-3 py-4">
        <CardContent className="px-4 space-y-2">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-3 w-64" />
        </CardContent>
      </Card>
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {[0, 1, 2].map((i) => (
          <Card key={i} className="lg:col-span-4 gap-3 py-4">
            <CardContent className="px-4 space-y-2">
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

/* ── Time helpers — relative age + compact clock, no ISO overflow ── */
export function timeAgo(ms: number | null | undefined, nowMs?: number): string {
  if (ms == null) return '—';
  const now = nowMs ?? Date.now();
  const s = Math.max(0, Math.round((now - ms) / 1000));
  if (s < 5) return 'just now';
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  return `${Math.floor(m / 60)}h ago`;
}

export function formatClock(ms: number | null | undefined): string {
  if (ms == null) return '—';
  try {
    return new Date(ms).toLocaleTimeString('en-GB', { hour12: false });
  } catch {
    return '—';
  }
}

export function formatPct01(v: number | null | undefined): string {
  if (v == null || !isFinite(v)) return '—';
  return `${(v * 100).toFixed(0)}%`;
}
