'use client';

import { Info, Play, Trash2 } from 'lucide-react';
import {
  confPct,
  executionEligibility,
  fmtDist,
  fmtTtl,
  isTerminalSignalState,
  shortId,
} from '@/lib/signalsNormalize';
import type { ActiveRow } from '@/lib/signalsNormalize';
import type { VirtualPosition } from '@/lib/types';
import { fmtInr, pnlClass, positionUnrealized } from '@/lib/ledger';
import { safeNum } from '@/lib/utils';
import {
  ageSeconds,
  buildStageChecklist,
  closedOutcome,
  executionInfo,
  formatAge,
  stageOf,
  type ChecklistStep,
  type ChecklistStepStatus,
} from '@/lib/signalStages';

function directionText(direction: unknown): string {
  const value = typeof direction === 'string' ? direction.toUpperCase() : '';
  if (value.includes('CALL') || value.includes('BULL') || value === 'LONG') return 'LONG';
  if (value.includes('PUT') || value.includes('BEAR') || value === 'SHORT') return 'SHORT';
  return value || '—';
}

function formatStamp(ms: number | null): string {
  if (ms === null) return '—';
  return new Date(ms).toLocaleTimeString('en-IN', {
    timeZone: 'Asia/Kolkata',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function stepTone(step: ChecklistStep, outcome: 'WIN' | 'LOSS' | 'FLAT' | null): { box: string; glyph: string } {
  const status: ChecklistStepStatus = step.status;
  if (status === 'done') return { box: 'border-up-line bg-up-wash text-up-strong', glyph: '✓' };
  if (status === 'current') return { box: 'border-accent-line bg-accent-wash text-accent', glyph: '●' };
  if (status === 'skipped') return { box: 'border-warn-line bg-warn-wash text-warn-strong', glyph: '–' };
  if (status === 'terminal') {
    if (outcome === 'WIN') return { box: 'border-up-line bg-up-wash text-up-strong', glyph: '✓' };
    if (outcome === 'LOSS') return { box: 'border-down-line bg-down-wash text-down-strong', glyph: '✕' };
    return { box: 'border-warn-line bg-warn-wash text-warn-strong', glyph: '■' };
  }
  return { box: 'border-border bg-surface-subtle text-ink-3', glyph: '○' };
}

export function SignalChecklistCard({
  row,
  now,
  position,
  marketClosed,
  busy,
  onOpen,
  onExecute,
  onDelete,
}: {
  row: ActiveRow;
  now: number;
  position?: VirtualPosition;
  marketClosed: boolean;
  busy: boolean;
  onOpen: (row: ActiveRow) => void;
  onExecute: (row: ActiveRow) => void;
  onDelete: (row: ActiveRow) => void;
}) {
  const stage = stageOf(row.state);
  const terminal = stage === 'CLOSED';
  const outcome = terminal ? closedOutcome(row.state) : null;
  const steps = buildStageChecklist(row);
  const eligibility = executionEligibility(row.state, marketClosed);
  const ttl = now > 0 ? fmtTtl(row.expiresMs, now) : ({ label: '—', tone: 'ok' } as const);
  const age = formatAge(ageSeconds(row, now));
  const dir = directionText(row.direction);
  const fill = executionInfo(row);
  const pnl = position ? positionUnrealized(position) : null;
  const showExecution = stage === 'EXECUTED' || fill.fillPrice !== null;

  return (
    <article
      className="card cursor-pointer transition-colors hover:border-border-strong"
      role="button"
      tabIndex={0}
      onClick={() => onOpen(row)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onOpen(row);
        }
      }}
      title="Open stage timeline and dossier"
    >
      <div className="flex flex-wrap items-start justify-between gap-2 border-b border-border-subtle px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="sg-sym">{row.symbol}</span>
          <span className={`sg-dir ${dir === 'LONG' ? 'long' : dir === 'SHORT' ? 'short' : 'neut'}`}>
            {dir}
          </span>
          <span className="sg-tag neut">{row.state}</span>
          {row.isScalp !== null ? (
            <span className={`sg-tag ${row.isScalp ? 'info' : 'neut'}`}>
              {row.isScalp ? 'SCALP' : 'INTRADAY'}
            </span>
          ) : null}
          {row.quarantined ? <span className="sg-tag warn">QUARANTINED</span> : null}
          <span className="sg-rownote truncate">
            {row.strategy} · {shortId(row.id)}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="sg-meta">
            <i className={row.incomplete ? '' : 'on'} />
            conf {confPct(row.confidence01)} · {age}
          </span>
          <span className={`sg-ttl ${ttl.tone === 'expired' ? 'expired' : ttl.tone === 'warn' ? 'warn' : ''}`}>
            {terminal ? 'settled' : ttl.label}
          </span>
        </div>
      </div>

      <div className="flex items-start px-3 py-2.5">
        {steps.map((step, index) => {
          const tone = stepTone(step, outcome);
          const connector =
            index === 0
              ? 'bg-transparent'
              : step.status === 'pending'
                ? 'bg-border'
                : step.status === 'current'
                  ? 'bg-accent-line'
                  : 'bg-up-line';
          return (
            <div key={step.stage} className="relative min-w-0 flex-1">
              {index > 0 ? (
                <span className={`absolute left-[-50%] right-[50%] top-[8px] h-px ${connector}`} aria-hidden="true" />
              ) : null}
              <div className="relative flex flex-col items-center gap-0.5 text-center">
                <span
                  className={`z-10 flex h-[17px] w-[17px] items-center justify-center rounded-xs border text-[11px] font-bold ${tone.box}`}
                  title={step.reason ?? undefined}
                >
                  {tone.glyph}
                </span>
                <span className="w-full truncate text-[11px] font-semibold tracking-wide text-ink-2">
                  {step.label}
                </span>
                <span className="mono text-[11px] text-ink-3">{formatStamp(step.timestampMs)}</span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex flex-wrap items-end gap-x-5 gap-y-2 border-t border-border-subtle px-3 py-2">
        <div className="grid grid-cols-2 gap-x-4 gap-y-1">
          <div>
            <span className="stat-l">Trigger</span>
            <div className="mono text-xs font-semibold">{safeNum(row.triggerLevel)}</div>
          </div>
          <div>
            <span className="stat-l">Distance</span>
            <div className="mono text-xs font-semibold">{fmtDist(row.triggerLevel, row.spot)}</div>
          </div>
          <div>
            <span className="stat-l">Stop</span>
            <div className="mono text-xs font-semibold">{safeNum(row.sl)}</div>
          </div>
          <div>
            <span className="stat-l">T1</span>
            <div className="mono text-xs font-semibold">{safeNum(row.t1)}</div>
          </div>
        </div>

        {showExecution ? (
          <div className="grid grid-cols-2 gap-x-4 gap-y-1">
            <div>
              <span className="stat-l">Fill</span>
              <div className="mono text-xs font-semibold">{safeNum(fill.fillPrice)}</div>
            </div>
            <div>
              <span className="stat-l">Qty</span>
              <div className="mono text-xs font-semibold">{fill.quantity ?? '—'}</div>
            </div>
            {position ? (
              <div className="col-span-2">
                <span className="stat-l">Live P&amp;L</span>
                <div className={`mono text-[13px] font-bold ${pnlClass(pnl)}`}>{fmtInr(pnl, true)}</div>
              </div>
            ) : null}
          </div>
        ) : null}

        {terminal ? (
          <div>
            <span className="stat-l">Outcome</span>
            <div
              className={`sg-tag ${outcome === 'WIN' ? 'bull' : outcome === 'LOSS' ? 'bear' : 'neut'}`}
            >
              {outcome}
            </div>
          </div>
        ) : null}

        <div className="ml-auto flex items-center gap-1">
          <button
            type="button"
            className="sg-ibtn"
            title="Stage timeline and dossier"
            onClick={(event) => {
              event.stopPropagation();
              onOpen(row);
            }}
          >
            <Info size={12} />
          </button>
          <button
            type="button"
            className="sg-ibtn"
            title={eligibility.eligible ? 'Execute as paper order' : eligibility.reason ?? 'Not executable'}
            disabled={!eligibility.eligible || busy}
            onClick={(event) => {
              event.stopPropagation();
              onExecute(row);
            }}
          >
            <Play size={12} />
          </button>
          <button
            type="button"
            className="sg-ibtn danger"
            title={isTerminalSignalState(row.state) ? 'Delete signal record' : 'Delete and square off'}
            disabled={busy}
            onClick={(event) => {
              event.stopPropagation();
              onDelete(row);
            }}
          >
            <Trash2 size={12} />
          </button>
        </div>
      </div>
    </article>
  );
}
