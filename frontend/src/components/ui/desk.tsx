'use client';

/* Shared forecast-desk primitives.
   Use these (plus the CSS classes in globals.css) in every feature panel
   instead of re-declaring inline CARD/TH/TD style objects. */

import type { CSSProperties, ReactNode } from 'react';
import { toNumber } from '@/lib/coerce';

export type Direction = 'BULLISH' | 'BEARISH' | 'NEUTRAL';

/* ---------------- formatting ---------------- */

export function fmtINR(v: unknown): string {
  const n = toNumber(v);
  if (n === null) return '—';
  return `₹${n.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
}

export function fmtNum(v: unknown, digits = 2): string {
  const n = toNumber(v);
  if (n === null) return '—';
  return n.toFixed(digits);
}

export function fmtSigned(v: unknown, digits = 1): string {
  const n = toNumber(v);
  if (n === null) return '—';
  const sign = n > 0 ? '+' : '';
  return `${sign}${n.toFixed(digits)}`;
}

export function fmtPct01(v: unknown): string {
  const n = toNumber(v);
  if (n === null) return '—';
  return `${Math.round(n * 100)}%`;
}

export function fmtClock(v: unknown): string {
  if (v === null || v === undefined || v === '') return '—';
  const d = v instanceof Date ? v : new Date(v as string);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
}

/* ---------------- direction ---------------- */

export function normalizeDirection(v: unknown): Direction {
  const d = String(v ?? '').toUpperCase();
  if (d === 'BULLISH' || d.includes('LONG') || d.includes('CALL')) return 'BULLISH';
  if (d === 'BEARISH' || d.includes('SHORT') || d.includes('PUT')) return 'BEARISH';
  return 'NEUTRAL';
}

export function toneFor(value: number | null | undefined): 'bull' | 'bear' | 'neut' {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'neut';
  if (value > 0) return 'bull';
  if (value < 0) return 'bear';
  return 'neut';
}

/* ---------------- building blocks ---------------- */

export function Card({
  title,
  meta,
  action,
  children,
  label,
}: {
  title: string;
  meta?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  label?: string;
}) {
  return (
    <section className="card" aria-label={label ?? title}>
      <div className="card-hd">
        <h2 className="card-title">{title}</h2>
        {meta ? <span className="card-meta num">{meta}</span> : null}
        {action ? <span style={{ marginLeft: meta ? 0 : 'auto' }}>{action}</span> : null}
      </div>
      <div className="card-bd">{children}</div>
    </section>
  );
}

export function DirectionBadge({ direction, big }: { direction: unknown; big?: boolean }) {
  const d = normalizeDirection(direction);
  const cls = d === 'BULLISH' ? 'b-bull' : d === 'BEARISH' ? 'b-bear' : 'b-neut';
  return (
    <span className={`badge ${cls}`} style={big ? { fontSize: 12, padding: '3px 8px' } : undefined}>
      {d}
    </span>
  );
}

/** Confidence / probability bar (0..1). */
export function Meter({ value, label = 'Meter' }: { value: unknown; label?: string }) {
  const n = toNumber(value);
  const pct = n !== null ? Math.max(0, Math.min(1, n)) * 100 : 0;
  return (
    <div
      className="meter"
      role="progressbar"
      aria-label={label}
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuetext={`${Math.round(pct)}%`}
    >
      <i style={{ width: `${pct}%` }} aria-hidden="true" />
    </div>
  );
}

/** Signed diverging bar centred at zero (value in -100..100). */
export function DivergingBar({
  value,
  label = 'Directional bias',
}: {
  value: unknown;
  label?: string;
}) {
  const n = toNumber(value);
  const v = n !== null ? Math.max(-100, Math.min(100, n)) : 0;
  const w = Math.abs(v) / 2; // half-track scale
  const style: CSSProperties =
    v >= 0 ? { left: '50%', width: `${w}%` } : { right: '50%', width: `${w}%` };
  // Colour alone is not an accessible signal: state the reading as text.
  const valueText = v > 0 ? `+${v} (bullish)` : v < 0 ? `${v} (bearish)` : '0 (neutral)';
  return (
    <div
      className="dbar"
      role="progressbar"
      aria-label={label}
      aria-valuemin={-100}
      aria-valuemax={100}
      aria-valuenow={v}
      aria-valuetext={valueText}
      title={valueText}
    >
      <i className={v >= 0 ? 'pos' : 'neg'} style={style} aria-hidden="true" />
    </div>
  );
}

export function Stat({
  label,
  value,
  sub,
  tone,
  compact = false,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: 'bull' | 'bear' | 'neut';
  compact?: boolean;
}) {
  const cls = tone === 'bull' ? 'v-bull' : tone === 'bear' ? 'v-bear' : undefined;
  return (
    <div className={`stat ${compact ? 'stat-compact' : ''}`}>
      <div className="stat-l">{label}</div>
      <div className={`stat-v ${cls ?? ''}`}>{value}</div>
      {sub ? <div className="stat-s num">{sub}</div> : null}
    </div>
  );
}

export function TelemetryStrip({
  children,
  className = '',
  style,
}: {
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <div className={`telemetry-strip ${className}`} style={style}>
      {children}
    </div>
  );
}

export function TelemetryItem({
  label,
  value,
  sub,
  tone,
  inline = false,
  title,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: 'bull' | 'bear' | 'neut';
  inline?: boolean;
  title?: string;
}) {
  const cls = tone === 'bull' ? 'v-bull' : tone === 'bear' ? 'v-bear' : undefined;
  return (
    <div className={`telemetry-item ${inline ? 'inline' : ''}`} title={title}>
      <span className="t-label">{label}</span>
      <span className={`t-val ${cls ?? ''}`}>{value}</span>
      {sub ? <span className="t-sub">{sub}</span> : null}
    </div>
  );
}

export function StackedProbabilityBar({
  bullPct,
  neutPct,
  bearPct,
  height = 8,
}: {
  bullPct: number;
  neutPct: number;
  bearPct: number;
  height?: number;
}) {
  const clamp = (v: number) => (Number.isFinite(v) ? Math.max(0, Math.min(100, v)) : 0);
  const bull = clamp(bullPct);
  const neut = clamp(neutPct);
  const bear = clamp(bearPct);
  const valueText = `Bullish ${bull}%, Neutral ${neut}%, Bearish ${bear}%`;
  return (
    <div
      className="prob-bar-stacked"
      style={{ height }}
      role="progressbar"
      aria-label="Outcome probabilities"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(bull)}
      aria-valuetext={valueText}
      title={valueText}
    >
      <div className="seg-bull" style={{ width: `${bull}%` }} title={`Bullish ${bull}%`} />
      <div className="seg-neut" style={{ width: `${neut}%` }} title={`Neutral ${neut}%`} />
      <div className="seg-bear" style={{ width: `${bear}%` }} title={`Bearish ${bear}%`} />
    </div>
  );
}

export function EmptyNote({ children }: { children: ReactNode }) {
  return <p className="muted" style={{ margin: 0 }}>{children}</p>;
}

export function RetryButton({ onRetry, children }: { onRetry: () => void; children?: ReactNode }) {
  return (
    <button type="button" className="btn" onClick={onRetry}>
      {children ?? 'Retry'}
    </button>
  );
}
