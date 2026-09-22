'use client';

import { Info, Play, Trash2 } from 'lucide-react';
import {
  confPct,
  executionEligibility,
  fmtDist,
  fmtTtl,
  isTerminalSignalState,
  shortId,
  signalAgeLabel,
  stateTone,
} from '@/lib/signalsNormalize';
import type { ActiveRow } from '@/lib/signalsNormalize';
import type { VirtualPosition } from '@/lib/types';
import { fmtInr, pnlClass, positionUnrealized } from '@/lib/ledger';
import { safeNum } from '@/lib/utils';
import {
  buildStageChecklist,
  closedOutcome,
  executionInfo,
  stageOf,
  type ChecklistStep,
  type ChecklistStepStatus,
} from '@/lib/signalStages';

/* ── Helpers ───────────────────────────────────────────────── */

function directionText(direction: unknown): 'LONG' | 'SHORT' | string {
  const value = typeof direction === 'string' ? direction.toUpperCase() : '';
  if (value.includes('CALL') || value.includes('BULL') || value === 'LONG') return 'LONG';
  if (value.includes('PUT') || value.includes('BEAR') || value === 'SHORT') return 'SHORT';
  return value || '—';
}

function formatStamp(ms: number | null): string | null {
  if (ms === null) return null;
  return new Date(ms).toLocaleTimeString('en-IN', {
    timeZone: 'Asia/Kolkata',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function optionContractLabel(raw: Record<string, unknown>): string | null {
  const contract = raw.option_contract;
  if (!contract || typeof contract !== 'object') return null;
  const c = contract as Record<string, unknown>;
  const sym =
    (typeof c.display_symbol === 'string' && c.display_symbol) ||
    (typeof c.symbol === 'string' && c.symbol) ||
    (typeof c.broker_symbol === 'string' && c.broker_symbol);
  if (sym) {
    return sym.replace(/^(NSE|BSE):/i, '').replace(/-EQ$/i, '');
  }
  const underlying = c.underlying ?? raw.underlying ?? '';
  const strike = c.strike ?? c.strike_price ?? '';
  const optType = c.option_type ?? '';
  const expiry = c.expiry_label ?? c.expiry_date ?? '';
  if (underlying && strike) {
    return `${underlying} ${expiry ? String(expiry).slice(0, 6) : ''} ${strike} ${optType}`.trim();
  }
  return null;
}

function liveStatusLabel(
  stage: string,
  state: string,
  pnl: number | null,
): { text: string; tone: 'live' | 'profit' | 'loss' | 'expired' | 'settled' } {
  const terminal = isTerminalSignalState(state);
  if (terminal) {
    const outcome = closedOutcome(state);
    if (outcome === 'WIN') return { text: 'CLOSED · WIN', tone: 'profit' };
    if (outcome === 'LOSS') return { text: 'CLOSED · LOSS', tone: 'loss' };
    if (state.toUpperCase().includes('EXPIRED')) return { text: 'EXPIRED', tone: 'expired' };
    return { text: 'SETTLED', tone: 'settled' };
  }
  if (stage === 'EXECUTED' && pnl !== null) {
    return pnl >= 0
      ? { text: 'EXECUTED · IN PROFIT', tone: 'profit' }
      : { text: 'EXECUTED · IN LOSS', tone: 'loss' };
  }
  if (stage === 'EXECUTED') return { text: 'EXECUTED', tone: 'live' };
  return { text: 'LIVE', tone: 'live' };
}

const STATUS_TONE_CLASSES: Record<string, string> = {
  live: 'text-accent border-accent-line bg-accent-wash',
  profit: 'text-up-strong border-up-line bg-up-wash',
  loss: 'text-down-strong border-down-line bg-down-wash',
  expired: 'text-warn-strong border-warn-line bg-warn-wash',
  settled: 'text-ink-2 border-border bg-surface-subtle',
};

/* ── Stepper step tone ──────────────────────────────────────── */

function stepTone(step: ChecklistStep, outcome: 'WIN' | 'LOSS' | 'FLAT' | null): { box: string; glyph: string } {
  const status: ChecklistStepStatus = step.status;
  if (status === 'done') return { box: 'border-up-line bg-up-wash text-up-strong', glyph: '✓' };
  if (status === 'current') return { box: 'border-accent-line bg-accent-wash text-accent', glyph: '●' };
  if (status === 'skipped') return { box: 'border-border bg-surface-subtle text-ink-3', glyph: '–' };
  if (status === 'terminal') {
    if (outcome === 'WIN') return { box: 'border-up-line bg-up-wash text-up-strong', glyph: '✓' };
    if (outcome === 'LOSS') return { box: 'border-down-line bg-down-wash text-down-strong', glyph: '✕' };
    return { box: 'border-warn-line bg-warn-wash text-warn-strong', glyph: '■' };
  }
  return { box: 'border-border bg-surface-subtle text-ink-3', glyph: '○' };
}

/* ── Component ──────────────────────────────────────────────── */

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
  // Missing timestamps render "age unknown" — never a silent today/just-now.
  const age = signalAgeLabel(row.timeMs, now > 0 ? now : undefined);
  const dir = directionText(row.direction);
  const fill = executionInfo(row);
  const pnl = position ? positionUnrealized(position) : null;
  const showExecution = stage === 'EXECUTED' || fill.fillPrice !== null;

  const contractLabel = optionContractLabel(row.raw);
  const statusInfo = liveStatusLabel(stage, row.state, pnl);
  const title = contractLabel ?? row.symbol;

  // Risk:Reward ratio from raw data
  const riskPts = row.raw.risk_points ?? row.raw.risk_reward_t1;
  const rr = typeof riskPts === 'number' && riskPts > 0
    ? `1:${riskPts.toFixed(1)}`
    : row.t1 && row.sl && row.triggerLevel
      ? `1:${Math.abs(((row.t1 - row.triggerLevel) / (row.triggerLevel - row.sl))).toFixed(1)}`
      : null;

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
      title="Open signal detail"
    >
      {/* Header: single title row + single meta row */}
      <div className="px-3 pb-2 pt-2.5">
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-baseline gap-2">
            <span className="truncate text-[13px] font-bold tracking-tight text-ink">
              {title}
            </span>
            {contractLabel ? (
              <span className="shrink-0 text-[11px] font-semibold text-ink-3">{row.symbol}</span>
            ) : null}
          </div>
          <span
            className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-bold tracking-wider ${STATUS_TONE_CLASSES[statusInfo.tone] ?? STATUS_TONE_CLASSES.settled}`}
          >
            <span
              className={`inline-block h-1.5 w-1.5 rounded-full ${
                statusInfo.tone === 'live' ? 'bg-accent animate-pulse' :
                statusInfo.tone === 'profit' ? 'bg-up' :
                statusInfo.tone === 'loss' ? 'bg-down' :
                'bg-ink-3'
              }`}
            />
            {statusInfo.text}
          </span>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[11px]">
          <span className="sg-sym text-[12px]">{row.symbol}</span>
          <span className={`sg-dir text-[10px] ${dir === 'LONG' ? 'long' : dir === 'SHORT' ? 'short' : 'neut'}`}>
            {dir}
          </span>
          <span className={`sg-tag text-[10px] ${stateTone(row.state) === 'bull' ? 'bull' : stateTone(row.state) === 'bear' ? 'bear' : stateTone(row.state) === 'info' ? 'info' : stateTone(row.state) === 'warn' ? 'warn' : 'neut'}`}>
            {row.state}
          </span>
          {row.isScalp !== null ? (
            <span className={`sg-tag text-[10px] ${row.isScalp ? 'info' : 'neut'}`}>
              {row.isScalp ? 'SCALP' : 'INTRADAY'}
            </span>
          ) : null}
          {row.quarantined ? <span className="sg-tag warn text-[10px]">QUARANTINED</span> : null}
          <span className="sg-rownote">
            {row.strategy} · {shortId(row.id)}
          </span>
          <span className="sg-meta">
            <i className={row.incomplete ? '' : 'on'} />
            conf {confPct(row.confidence01)}% · {age}
          </span>
          <span className={`sg-ttl ${ttl.tone === 'expired' ? 'expired' : ttl.tone === 'warn' ? 'warn' : ''}`}>
            {terminal ? 'settled' : ttl.label}
          </span>
        </div>
      </div>

      {/* Lifecycle stepper */}
      <div className="border-t border-border-subtle px-4 py-2.5">
        <div className="flex items-start">
          {steps.map((step, index) => {
            const tone = stepTone(step, outcome);
            const stamp = formatStamp(step.timestampMs);
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
                  <span className={`absolute left-[-50%] right-[50%] top-[10px] h-[2px] ${connector}`} aria-hidden="true" />
                ) : null}
                <div className="relative flex flex-col items-center gap-1 text-center">
                  <span
                    className={`z-10 flex h-[20px] w-[20px] items-center justify-center rounded-full border text-[11px] font-bold ${tone.box}`}
                    title={step.reason ?? step.label}
                  >
                    {tone.glyph}
                  </span>
                  <span className="text-[11px] font-semibold text-ink-2">
                    {step.label}
                  </span>
                  <span className="mono min-h-[14px] text-[10px] text-ink-3">{stamp ?? ''}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Levels */}
      <div className="border-t border-border-subtle px-3 py-2">
        <div className={`grid gap-x-4 gap-y-1.5 ${showExecution ? 'grid-cols-3 sm:grid-cols-6' : 'grid-cols-2 sm:grid-cols-5'}`}>
          <div>
            <span className="stat-l text-[10px]">Trigger</span>
            <div className="mono text-[13px] font-semibold">{safeNum(row.triggerLevel)}</div>
          </div>
          <div>
            <span className="stat-l text-[10px]">Stop</span>
            <div className="mono text-[13px] font-semibold">{safeNum(row.sl)}</div>
          </div>
          <div>
            <span className="stat-l text-[10px]">Target 1</span>
            <div className="mono text-[13px] font-semibold">{safeNum(row.t1)}</div>
          </div>
          <div>
            <span className="stat-l text-[10px]">Distance</span>
            <div className="mono text-[13px] font-semibold">{fmtDist(row.triggerLevel, row.spot)}</div>
          </div>
          <div>
            {position && pnl !== null ? (
              <>
                <span className="stat-l text-[10px]">Live P&amp;L</span>
                <div className={`mono text-[13px] font-bold ${pnlClass(pnl)}`}>{fmtInr(pnl, true)}</div>
              </>
            ) : showExecution ? (
              <>
                <span className="stat-l text-[10px]">Fill{fill.quantity ? ` · ${fill.quantity}` : ''}</span>
                <div className="mono text-[13px] font-semibold">{safeNum(fill.fillPrice)}</div>
              </>
            ) : rr ? (
              <>
                <span className="stat-l text-[10px]">R:R</span>
                <div className="mono text-[13px] font-semibold">{rr}</div>
              </>
            ) : null}
          </div>
          {showExecution ? (
            <div>
              <span className="stat-l text-[10px]">Qty</span>
              <div className="mono text-[13px] font-semibold">{fill.quantity ?? '—'}</div>
            </div>
          ) : null}
        </div>
      </div>

      {/* Footer: outcome + actions */}
      <div className="flex items-center gap-2 border-t border-border-subtle px-3 py-1.5">
        {terminal ? (
          <span
            className={`sg-tag text-[10px] ${outcome === 'WIN' ? 'bull' : outcome === 'LOSS' ? 'bear' : 'neut'}`}
          >
            {outcome}
          </span>
        ) : (
          <span className="sg-rownote">{eligibility.eligible ? 'Ready to execute' : (eligibility.reason ?? '')}</span>
        )}
        <div className="ml-auto flex items-center gap-1">
          <button
            type="button"
            className="sg-ibtn"
            title="Signal detail and dossier"
            onClick={(event) => {
              event.stopPropagation();
              onOpen(row);
            }}
          >
            <Info size={13} />
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
            <Play size={13} />
          </button>
          <button
            type="button"
            className="sg-ibtn danger"
            title={isTerminalSignalState(row.state) ? 'Delete signal record' : 'Close and square off'}
            disabled={busy}
            onClick={(event) => {
              event.stopPropagation();
              onDelete(row);
            }}
          >
            <Trash2 size={13} />
          </button>
        </div>
      </div>
    </article>
  );
}
