'use client';

import Link from 'next/link';
import { RefreshCw } from 'lucide-react';
import {
  DIRECTION_THRESHOLD,
  SOURCE_WEIGHTS,
  type DirectionalConsensus,
  type DirectionalSourceRead,
  type DirectionalTone,
} from '@/lib/directionalConsensus';

function toneBadge(tone: DirectionalTone): string {
  if (tone === 'bull') return 'b-bull';
  if (tone === 'bear') return 'b-bear';
  return 'b-neut';
}

function toneText(tone: DirectionalTone): string {
  if (tone === 'bull') return 'v-bull';
  if (tone === 'bear') return 'v-bear';
  return 'text-ink-2';
}

function toneFill(tone: DirectionalTone): string {
  if (tone === 'bull') return 'bg-up';
  if (tone === 'bear') return 'bg-down';
  return 'bg-border-strong';
}

function signed(score: number): string {
  return `${score > 0 ? '+' : ''}${score}`;
}

function SourceCard({ read }: { read: DirectionalSourceRead }) {
  const width = read.score !== null ? Math.min(100, Math.abs(read.score)) : 0;
  return (
    <div className="flex flex-col gap-2 rounded-md border border-border-subtle bg-surface-subtle p-2.5">
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-[12px] font-semibold text-ink-2">{read.label}</span>
        <span className={`badge ${toneBadge(read.tone)}`}>{read.headline}</span>
      </div>
      <div className="flex items-baseline justify-between gap-2">
        <span className={`mono text-[20px] font-bold leading-none ${toneText(read.tone)}`}>
          {read.score !== null ? signed(read.score) : '—'}
        </span>
        <span className="stat-l">lean</span>
      </div>
      <span className="meter" aria-hidden="true">
        <i className={toneFill(read.tone)} style={{ width: `${width}%` }} />
      </span>
      <p className="m-0 text-[11px] leading-snug text-ink-2">{read.detail}</p>
      <Link
        href={read.href}
        className="mt-auto text-[11px] font-semibold text-accent hover:underline"
      >
        Open {read.label} →
      </Link>
    </div>
  );
}

/**
 * One screen for the bull/bear call: the tactical forecast board, the live
 * signal book and the PAP shadow model are fused into a single verdict with a
 * per-source breakdown, so the operator no longer has to open three modules to
 * find out which way the market is leaning.
 */
export function DirectionalConsensusBoard({
  consensus,
  instrument,
  asOfLabel,
  refreshing,
  onRefresh,
}: {
  consensus: DirectionalConsensus;
  instrument: string;
  asOfLabel?: string;
  refreshing?: boolean;
  onRefresh?: () => void;
}) {
  const { available, tone, label, score, confidence, alignment, bull, bear, neut, sources } =
    consensus;
  const reporting = sources.filter((read) => read.available).length;
  const voteTotal = bull + bear + neut;
  const pct = (count: number) => (voteTotal > 0 ? (count / voteTotal) * 100 : 0);

  return (
    <section className="forecast-hero" data-tone={tone} aria-label="Unified market direction">
      <div className="card-pad flex flex-col gap-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="micro-label">Unified direction · {instrument}</div>
            <div className="mt-1 flex items-baseline gap-2">
              <span className={`text-[24px] font-bold leading-none ${toneText(tone)}`}>
                {label}
              </span>
              {available ? (
                <span className={`mono text-[15px] font-semibold ${toneText(tone)}`}>
                  {signed(score)}
                </span>
              ) : null}
            </div>
            <p className="m-0 mt-1.5 text-[12px] text-ink-2">
              {available
                ? `${alignment} · ${reporting} of ${sources.length} sources reporting (${bull} bull / ${bear} bear / ${neut} neutral)`
                : 'No directional source is reporting right now. Forecast, signals and PAP all failed to answer.'}
            </p>
          </div>

          <div className="flex items-center gap-3">
            <div className="text-right">
              <div className="mono text-[18px] font-bold leading-none">
                {available ? `${confidence}%` : '—'}
              </div>
              <div className="stat-l">conviction</div>
            </div>
            {onRefresh ? (
              <button
                type="button"
                className="btn btn-ic"
                disabled={refreshing}
                onClick={onRefresh}
                title="Refresh the forecast board, live signals and PAP shadow model"
              >
                <RefreshCw size={13} className={refreshing ? 'animate-spin' : undefined} />
                {refreshing ? 'Refreshing…' : 'Refresh all'}
              </button>
            ) : null}
          </div>
        </div>

        {available ? (
          <div
            className="prob-bar-stacked"
            role="img"
            aria-label={`${bull} bullish, ${bear} bearish, ${neut} neutral sources`}
          >
            <i className="seg-bull" style={{ width: `${pct(bull)}%` }} />
            <i className="seg-neut" style={{ width: `${pct(neut)}%` }} />
            <i className="seg-bear" style={{ width: `${pct(bear)}%` }} />
          </div>
        ) : null}

        <div className="grid gap-2 md:grid-cols-3">
          {sources.map((read) => (
            <SourceCard key={read.id} read={read} />
          ))}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-border-subtle px-2.5 py-1.5 text-[11px] text-ink-3">
        <span>
          Weighted blend · {DIRECTION_THRESHOLD}% threshold · forecast{' '}
          {SOURCE_WEIGHTS.forecast} / signals {SOURCE_WEIGHTS.signals} / pap {SOURCE_WEIGHTS.pap}
        </span>
        <span className="ml-auto font-mono">
          {asOfLabel ? `as of ${asOfLabel}` : ''}
        </span>
      </div>
    </section>
  );
}
