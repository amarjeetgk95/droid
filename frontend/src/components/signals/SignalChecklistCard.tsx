'use client';

import { Info, Play, Trash2 } from 'lucide-react';
import {
  executionEligibility,
  fmtDist,
  fmtTtl,
  isTerminalSignalState,
  pickMs,
  pickNum,
  pickStr,
  shortId,
  signalAgeLabel,
} from '@/lib/signalsNormalize';
import type { ActiveRow } from '@/lib/signalsNormalize';
import type { VirtualPosition } from '@/lib/types';
import { fmtInr, pnlClass, positionUnrealized } from '@/lib/ledger';
import { safeNum } from '@/lib/utils';
import { closedOutcome, executionInfo, stageOf, stateLabel } from '@/lib/signalStages';

import { SignalStageRail } from './parts/SignalStageRail';
import { SignalGatesStrip } from './parts/SignalGatesStrip';
import { SignalLevelGrid } from './parts/SignalLevelGrid';

/* ── helpers ── */

function directionText(direction: unknown): 'LONG' | 'SHORT' | string {
  const value = typeof direction === 'string' ? direction.toUpperCase() : '';
  if (value.includes('CALL') || value.includes('BULL') || value === 'LONG') return 'LONG';
  if (value.includes('PUT') || value.includes('BEAR') || value === 'SHORT') return 'SHORT';
  return value || '—';
}

function fmtISTFull(ms: number | null): string {
  if (ms === null || !Number.isFinite(ms)) return '—';
  const d = new Date(ms);
  if (Number.isNaN(d.getTime())) return '—';
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Kolkata',
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).formatToParts(d);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? '';
  return `${get('day')} ${get('month')} ${get('hour')}:${get('minute')}:${get('second')} IST`;
}

function optionContractLabel(raw: Record<string, unknown>): string | null {
  const contract = raw.option_contract;
  if (!contract || typeof contract !== 'object') return null;
  const c = contract as Record<string, unknown>;
  const sym =
    (typeof c.display_symbol === 'string' && c.display_symbol) ||
    (typeof c.symbol === 'string' && c.symbol) ||
    (typeof c.broker_symbol === 'string' && c.broker_symbol);
  if (sym) return sym.replace(/^(NSE|BSE):/i, '').replace(/-EQ$/i, '');
  return null;
}

/* ── compact scanning tile — full dossier lives in SignalDetailDrawer ── */

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
  const eligibility = executionEligibility(row.state, marketClosed);
  const ttl = now > 0 ? fmtTtl(row.expiresMs, now) : ({ label: '—', tone: 'ok' } as const);
  const age = signalAgeLabel(row.timeMs, now > 0 ? now : undefined);
  const dir = directionText(row.direction);
  const isLong = dir === 'LONG';
  const isShort = dir === 'SHORT';
  const fill = executionInfo(row);
  const pnl = position ? positionUnrealized(position) : null;

  const raw = (row.raw ?? {}) as Record<string, unknown>;
  const contractLabel = optionContractLabel(raw);
  const timeframe = pickStr(raw, 'timeframe') ?? null;
  const deskLabel =
    row.isScalp !== null ? (row.isScalp ? 'SCALP' : 'INTRADAY') : (row.desk ?? pickStr(raw, 'signal_type'));
  const dataQuality = pickStr(raw, 'data_quality') ?? null;
  const createdMs = pickMs(raw, 'created_at_utc', 'created_at_ms', 'created_at', 'created_at_iso') ?? row.timeMs;
  const expiresMs = row.expiresMs ?? pickMs(raw, 'expires_at_utc', 'expiry_ms') ?? null;
  const triggeredMs = pickMs(raw, 'triggered_at_utc', 'triggered_at') ?? null;

  const rrT1 = pickNum(raw, 'risk_reward_t1', 'risk_reward_1', 'rr_t1');
  const rrT2 = pickNum(raw, 'risk_reward_t2', 'risk_reward_2', 'rr_t2');
  const synthRr =
    row.t1 !== null && row.sl !== null && row.triggerLevel !== null && row.triggerLevel !== row.sl
      ? Math.abs((row.t1 - row.triggerLevel) / (row.triggerLevel - row.sl))
      : null;
  const rrT1Final = rrT1 ?? synthRr;
  const rrText =
    rrT1Final !== null || rrT2 !== null
      ? `1:${rrT1Final !== null ? rrT1Final.toFixed(2) : '—'}${rrT2 !== null ? ` / 1:${rrT2.toFixed(2)}` : ''}`
      : null;

  const spotAtDetect = row.spot ?? pickNum(raw, 'spot_price', 'spot_price_at_creation', 'current_price');
  const distPts = pickNum(raw, 'distance_to_trigger_pts');
  const distPct = pickNum(raw, 'distance_to_trigger_pct');
  const distText =
    distPts !== null || distPct !== null
      ? `${distPts !== null ? `${distPts >= 0 ? '+' : ''}${distPts.toFixed(2)}` : '—'}${distPct !== null ? ` (${distPct >= 0 ? '+' : ''}${distPct.toFixed(2)}%)` : ''}`
      : fmtDist(row.triggerLevel, spotAtDetect);

  const qty = fill.quantity ?? pickNum(raw, 'quantity', 'lots', 'intended_qty');
  const exitPrice = pickNum(raw, 'exit_price');
  const exitReason = pickStr(raw, 'exit_reason');

  const steps = (() => {
    // Reason line reads the latest transition reason off the checklist.
    const historyEntries = Array.isArray(row.raw.state_history) ? row.raw.state_history : [];
    const latest = historyEntries[historyEntries.length - 1];
    if (latest && typeof latest === 'object') {
      const reason = pickStr(latest as Record<string, unknown>, 'reason_code');
      if (reason) return reason;
    }
    return null;
  })();
  const reasonLine =
    `${dir} ${row.strategy}${timeframe ? ` ${timeframe}` : ''} — ${stateLabel(row.state)}` +
    (steps ? ` (${steps})` : '');

  const spine = terminal ? 'bg-ink-3' : isLong ? 'bg-up' : isShort ? 'bg-down' : 'bg-accent';
  const statusPill = terminal
    ? outcome === 'WIN'
      ? 'border-up-line bg-up-wash text-up-strong'
      : outcome === 'LOSS'
        ? 'border-down-line bg-down-wash text-down-strong'
        : 'border-warn-line bg-warn-wash text-warn-strong'
    : 'border-accent-line bg-accent-wash text-accent';
  const statusText = terminal ? (outcome ?? stateLabel(row.state)).toUpperCase() : stage.toUpperCase();

  return (
    <article
      className="card group relative flex h-full w-full cursor-pointer flex-col gap-2 p-3 transition-all hover:-translate-y-[1px] hover:border-border-strong hover:shadow-lg"
      role="button"
      tabIndex={0}
      onClick={() => onOpen(row)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onOpen(row);
        }
      }}
      title={`Open signal dossier · ${row.id}`}
    >
      <span className={`absolute inset-y-0 left-0 w-[3px] rounded-l-lg ${spine}`} aria-hidden="true" />

      {/* header */}
      <div className="flex items-center justify-between gap-2 pl-1">
        <div className="flex min-w-0 items-center gap-1.5">
          <span
            className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-extrabold tracking-wider text-white ${
              isLong ? 'bg-up' : isShort ? 'bg-down' : 'bg-ink-2'
            }`}
          >
            {dir}
          </span>
          <h3 className="truncate text-[14px] font-extrabold tracking-tight text-ink" title={contractLabel ?? row.symbol}>
            {row.symbol}
          </h3>
          <span className="truncate text-[10px] font-semibold uppercase tracking-wide text-ink-2">
            {row.strategy}
            {timeframe ? ` · ${timeframe}` : ''}
          </span>
        </div>
        <span
          className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-px text-[10px] font-extrabold tracking-wider ${statusPill}`}
          title={`FSM ${row.state} · stage ${stage}`}
        >
          {!terminal ? <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-current" /> : null}
          {statusText}
        </span>
      </div>

      {/* contract + id */}
      <div className="mono truncate pl-1 font-mono text-[10px] text-ink-2" title={contractLabel ?? row.id}>
        {contractLabel ?? shortId(row.id)}
        {deskLabel ? ` · ${deskLabel}` : ''}
        {dataQuality && dataQuality !== 'LIVE' ? ` · ${dataQuality}` : ''}
        {row.quarantined ? ' · QUARANTINED' : ''}
      </div>

      {/* levels */}
      <div className="pl-1">
        <SignalLevelGrid row={row} />
      </div>

      {/* spot / dist / rr */}
      <div
        className="mono truncate pl-1 font-mono text-[10px] tabular-nums text-ink-2"
        title={`Spot @ detect ${spotAtDetect !== null ? safeNum(spotAtDetect) : '—'}${createdMs !== null ? ` · ${fmtISTFull(createdMs)}` : ''}`}
      >
        Spot {spotAtDetect !== null ? safeNum(spotAtDetect) : '—'} · {distText}
        {rrText ? ` · R:R ${rrText}` : ''}
        {position && pnl !== null ? (
          <span className={`font-extrabold ${pnlClass(pnl)}`}> · {fmtInr(pnl, true)}</span>
        ) : null}
      </div>

      {/* lifecycle rail */}
      <div className="pl-1 pr-1">
        <SignalStageRail row={row} />
        <div className="mono mt-1 flex items-center justify-between font-mono text-[9.5px] text-ink-3">
          <span title={createdMs !== null ? `Created ${fmtISTFull(createdMs)}` : undefined}>{age}</span>
          <span title={expiresMs !== null ? `Expires ${fmtISTFull(expiresMs)}` : undefined}>
            {terminal ? (exitReason ?? exitPrice !== null ? `Exit ${safeNum(exitPrice)}` : 'settled') : `⏳ ${ttl.label}`}
          </span>
        </div>
      </div>

      {/* gates strip */}
      <div className="pl-1">
        <SignalGatesStrip row={row} />
      </div>

      {/* reason + warnings */}
      <p className="truncate pl-1 text-[11px] font-medium text-ink-2" title={reasonLine}>
        {reasonLine}
      </p>
      {row.incomplete || row.quarantined ? (
        <p className="truncate rounded-md border border-warn-line bg-warn-wash px-1.5 py-0.5 text-[10px] font-semibold text-warn-strong">
          {row.incomplete ? `Missing ${row.missingLevels.join(', ')}. ` : ''}
          {row.quarantined ? `Quarantined: ${row.quarantineReason ?? 'off-domain data'}.` : ''}
        </p>
      ) : null}

      {/* actions */}
      <div className="mt-auto flex items-center gap-1.5 pl-1 pt-1">
        {!terminal ? (
          <button
            type="button"
            disabled={!eligibility.eligible || busy}
            title={eligibility.eligible ? `Execute · trigger ${safeNum(row.triggerLevel)} · SL ${safeNum(row.sl)}` : (eligibility.reason ?? 'Not executable')}
            onClick={(event) => {
              event.stopPropagation();
              onExecute(row);
            }}
            className="flex min-w-0 flex-1 items-center justify-center gap-1 rounded-lg bg-up-strong px-2 py-1.5 text-[11px] font-bold text-white transition-all hover:opacity-90 disabled:opacity-40"
          >
            <Play size={12} />
            <span className="truncate">{busy ? 'Working…' : `Execute${qty !== null ? ` · ${qty}` : ''}`}</span>
          </button>
        ) : null}
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onOpen(row);
          }}
          className="flex items-center gap-1 rounded-lg border border-border bg-surface px-2 py-1.5 text-[11px] font-semibold text-ink-2 transition-colors hover:border-accent hover:text-accent"
          title={`Dossier · created ${fmtISTFull(createdMs)}${triggeredMs !== null ? ` · triggered ${fmtISTFull(triggeredMs)}` : ''}`}
        >
          <Info size={12} />
          <span>Dossier</span>
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={(event) => {
            event.stopPropagation();
            onDelete(row);
          }}
          className="flex items-center gap-1 rounded-lg border border-border bg-surface px-2 py-1.5 text-[11px] font-semibold text-ink-2 transition-colors hover:border-down hover:text-down-strong disabled:opacity-40"
          title={isTerminalSignalState(row.state) ? `Delete ${shortId(row.id)}` : 'Close and square off'}
        >
          <Trash2 size={12} />
          <span>Delete</span>
        </button>
      </div>
    </article>
  );
}