'use client';

import { useMemo, useState } from 'react';
import { ArrowDown, ArrowUp, Check, Copy, ExternalLink, Shield, Trash2, Zap } from 'lucide-react';
import type { ActiveRow } from '@/lib/signalsNormalize';
import { executionEligibility, pickMs, pickNum, pickStr } from '@/lib/signalsNormalize';
import type { VirtualPosition } from '@/lib/types';
import { fmtInr, pnlClass, positionUnrealized } from '@/lib/ledger';
import { safeNum } from '@/lib/utils';
import { closedOutcome, executionInfo, stageOf, stateLabel } from '@/lib/signalStages';

import { SignalStageRail } from './parts/SignalStageRail';
import { SignalGatesStrip } from './parts/SignalGatesStrip';
import { SignalLevelGrid } from './parts/SignalLevelGrid';

function directionText(direction: unknown): 'LONG' | 'SHORT' | string {
  const value = typeof direction === 'string' ? direction.toUpperCase() : '';
  if (value.includes('PUT') || value.includes('BEAR') || value === 'SHORT') return 'SHORT';
  if (value.includes('CALL') || value.includes('BULL') || value === 'LONG') return 'LONG';
  return value || '—';
}

export type SignalFullCardContext = {
  thesis?: string | null;
  keyReason?: string | null;
  bullets?: string[];
  tradeNotes?: string[];
};

export function SignalFullCard({
  row,
  position,
  marketClosed = false,
  busy = false,
  isDemo = false,
  context,
  onExecute,
  onCopyContract,
  onDelete,
  onViewDossier,
}: {
  row: ActiveRow;
  position?: VirtualPosition;
  marketClosed?: boolean;
  busy?: boolean;
  isDemo?: boolean;
  context?: SignalFullCardContext;
  onExecute?: () => void;
  onCopyContract?: () => void;
  onDelete?: () => void;
  onViewDossier?: () => void;
}) {
  const [copiedContract, setCopiedContract] = useState(false);
  const [copiedId, setCopiedId] = useState(false);

  const stage = stageOf(row.state);
  const terminal = stage === 'CLOSED';
  const outcome = terminal ? closedOutcome(row.state) : null;
  const dir = directionText(row.direction);
  const isLong = dir === 'LONG';
  const isShort = dir === 'SHORT';

  const raw = (row.raw ?? {}) as Record<string, unknown>;
  const contract = raw.option_contract && typeof raw.option_contract === 'object'
    ? (raw.option_contract as Record<string, unknown>)
    : null;
  const contractLabel =
    pickStr(contract ?? {}, 'display_symbol', 'symbol', 'broker_symbol')
      ?.replace(/^(NSE|BSE):/i, '')
      .replace(/-EQ$/i, '') ?? null;
  const moneyness = pickStr(contract ?? {}, 'moneyness') ?? pickStr(raw, 'moneyness') ?? null;
  const priceChange = pickNum(raw, 'spot_change', 'change');
  const priceChangePct = pickNum(raw, 'spot_change_pct', 'change_pct');
  const timeframe = pickStr(raw, 'timeframe') ?? null;
  const deskLabel =
    row.isScalp !== null ? (row.isScalp ? 'SCALP' : 'INTRADAY') : (row.desk ?? pickStr(raw, 'signal_type'));
  const dataQuality = pickStr(raw, 'data_quality') ?? null;
  const createdMs = pickMs(raw, 'created_at_utc', 'created_at_ms', 'created_at', 'created_at_iso') ?? row.timeMs;
  const createdLabel = createdMs !== null
    ? new Date(createdMs).toLocaleString('en-IN', {
        timeZone: 'Asia/Kolkata',
        day: '2-digit',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      })
    : null;

  const fill = executionInfo(row);
  const pnl = position ? positionUnrealized(position) : null;
  const eligibility = marketClosed === false ? executionEligibility(row.state, false) : { eligible: false, reason: 'Market closed — paper execution is disabled.' };
  const canExecute = !isDemo && !terminal && !busy && Boolean(onExecute) && eligibility.eligible;

  const thesis = context?.thesis ?? pickStr(raw, 'thesis', 'key_reason', 'rationale');
  const keyReason = context?.keyReason ?? null;
  const bullets = context?.bullets ?? null;
  const tradeNotes = context?.tradeNotes ?? null;

  const signed = useMemo(() => {
    if (priceChange === null && priceChangePct === null) return null;
    return `${priceChange !== null ? `${priceChange >= 0 ? '+' : ''}${safeNum(priceChange)}` : '—'}${
      priceChangePct !== null ? ` (${priceChangePct >= 0 ? '+' : ''}${priceChangePct.toFixed(2)}%)` : ''
    }`;
  }, [priceChange, priceChangePct]);

  const handleCopyContract = () => {
    if (!contractLabel) return;
    if (onCopyContract) onCopyContract();
    else if (navigator?.clipboard) navigator.clipboard.writeText(contractLabel);
    setCopiedContract(true);
    setTimeout(() => setCopiedContract(false), 2000);
  };

  const handleCopyId = () => {
    if (!row.id || !navigator?.clipboard) return;
    navigator.clipboard.writeText(row.id);
    setCopiedId(true);
    setTimeout(() => setCopiedId(false), 2000);
  };

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
      className="relative isolate w-full overflow-hidden rounded-2xl border border-border bg-surface p-5 shadow-xl transition-all"
      style={{ fontFamily: 'var(--font-sans)' }}
    >
      {isDemo ? (
        <>
          <div
            className="pointer-events-none absolute inset-0 -z-10 flex items-center justify-center overflow-hidden"
            aria-hidden="true"
          >
            <span className="select-none -rotate-[18deg] text-[110px] font-black uppercase tracking-[0.3em] text-warn-strong/10">
              Demo
            </span>
          </div>
          <p
            role="note"
            className="mb-3 rounded-lg border border-warn-line bg-warn-wash px-3 py-1.5 text-[10.5px] font-semibold uppercase tracking-wider text-warn-strong"
          >
            Demo preview — illustrative layout only. Execution disabled.
          </p>
        </>
      ) : null}

      {/* 1. header */}
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <div className="flex items-center gap-2">
            <span
              className={`shrink-0 rounded px-2 py-0.5 text-[11px] font-extrabold tracking-wider text-white ${
                isLong ? 'bg-up' : isShort ? 'bg-down' : 'bg-ink-2'
              }`}
            >
              {dir}
            </span>
            <h2 className="truncate text-2xl font-extrabold tracking-tight text-ink">{row.symbol}</h2>
            <span className="rounded bg-inset px-2 py-0.5 text-[11px] font-bold tracking-wider text-ink-2">
              {deskLabel || '—'}
            </span>
            {timeframe ? (
              <span className="rounded bg-inset px-1.5 py-0.5 text-[11px] font-bold text-ink">{timeframe}</span>
            ) : null}
          </div>
          <div className="mono truncate font-mono text-xs text-ink-2" title={contractLabel ?? row.id}>
            {contractLabel ?? 'No contract on record'}
            {dataQuality && dataQuality !== 'LIVE' ? ` · ${dataQuality}` : ''}
            {row.quarantined ? ' · QUARANTINED' : ''}
            {createdLabel ? ` · ${createdLabel} IST` : ''}
          </div>
        </div>

        <div className="flex shrink-0 flex-col items-end gap-1">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-extrabold uppercase tracking-wider ${statusPill}`}
            title={`FSM ${row.state} · stage ${stage}`}
          >
            {!terminal ? (
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-current" />
              </span>
            ) : null}
            {statusText}
          </span>
          <button
            type="button"
            onClick={handleCopyId}
            className="flex items-center gap-1 font-mono text-[11px] text-ink-2 hover:text-ink"
            title="Click to copy Signal ID"
          >
            <span>ID: {row.id.slice(0, 14)}…</span>
            {copiedId ? <Check size={11} className="text-up-strong" /> : <Copy size={11} />}
          </button>
          <span className="text-[11px] text-ink-3">{row.strategy}</span>
        </div>
      </header>

      {/* 2. hero banner */}
      <div
        className={`mt-4 flex items-center justify-between rounded-xl p-3.5 text-white shadow-md transition-all ${
          isLong
            ? 'bg-gradient-to-r from-up-strong to-up shadow-up-strong/20'
            : isShort
              ? 'bg-gradient-to-r from-down-strong to-down shadow-down-strong/20'
              : 'bg-gradient-to-r from-ink-2 to-ink shadow-ink/20'
        }`}
      >
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-surface/20 text-lg font-extrabold text-white">
            {isLong ? <ArrowUp size={20} strokeWidth={3} /> : isShort ? <ArrowDown size={20} strokeWidth={3} /> : null}
          </div>
          <div className="min-w-0">
            <span className="block text-[17px] font-extrabold tracking-wide">
              {(isLong ? 'LONG' : isShort ? 'SHORT' : dir || 'NEUTRAL')} · {row.strategy}
            </span>
            <span className="block truncate text-xs font-medium text-white/90" title={thesis ?? undefined}>
              {thesis ?? stateLabel(row.state)}
            </span>
          </div>
        </div>
        {position && pnl !== null ? (
          <span
            className={`shrink-0 rounded-full bg-surface px-3 py-1 text-[11px] font-extrabold tracking-wide shadow-sm ${
              pnlClass(pnl)
            }`}
          >
            {fmtInr(pnl, true)}
          </span>
        ) : null}
      </div>

      {/* 3. contract & spot row */}
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-[1fr_175px]">
        <div className="flex flex-col gap-2.5 rounded-xl border border-border bg-surface p-3.5">
          <div className="flex items-center justify-between">
            <div className="min-w-0">
              <div className="text-[9.5px] font-bold uppercase tracking-wider text-ink-2">
                Option Contract {fill.optionSymbol ? '(Primary Execution)' : ''}
              </div>
              <div className="truncate text-[15.5px] font-extrabold text-ink" title={contractLabel ?? undefined}>
                {contractLabel ?? 'No data'}
              </div>
            </div>
            {moneyness ? (
              <span className="shrink-0 rounded-md border border-up-line bg-up-wash px-2 py-0.5 text-[11px] font-bold text-up-strong">
                {moneyness}
              </span>
            ) : null}
          </div>

          <div className="grid grid-cols-2 gap-2 border-t border-border-subtle pt-2.5 sm:grid-cols-4">
            <div className="flex flex-col">
              <span className="text-[9.5px] font-bold uppercase tracking-wider text-ink-2">Fill</span>
              <span className="mono font-mono text-[14px] font-bold text-ink">
                {fill.fillPrice !== null ? safeNum(fill.fillPrice) : 'No data'}
              </span>
              <span className="mono font-mono text-[9.5px] font-semibold text-ink-2">
                {fill.quantity !== null ? `${fill.quantity} qty` : '—'}
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-[9.5px] font-bold uppercase tracking-wider text-ink-2">Strike</span>
              <span className="mono font-mono text-[14px] font-bold text-ink">
                {safeNum(pickNum(contract ?? {}, 'strike') ?? pickNum(raw, 'strike'))}
              </span>
              <span className="font-mono text-[9.5px] font-semibold text-ink-2">
                {pickStr(contract ?? {}, 'option_type') ?? '—'}
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-[9.5px] font-bold uppercase tracking-wider text-ink-2">Expiry</span>
              <span className="mono font-mono text-[14px] font-bold text-ink">
                {pickStr(contract ?? {}, 'expiry_label', 'expiry_date', 'expiry') ?? 'No data'}
              </span>
              <span className="font-mono text-[9.5px] font-semibold text-ink-2">
                {safeNum(pickNum(contract ?? {}, 'lot_size'), '—', 0)} lot
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-[9.5px] font-bold uppercase tracking-wider text-ink-2">Order</span>
              <span className="mono truncate font-mono text-[14px] font-bold text-ink" title={fill.orderId ?? undefined}>
                {fill.orderId ?? 'No data'}
              </span>
              <span className="font-mono text-[9.5px] font-semibold text-ink-2">—</span>
            </div>
          </div>
        </div>

        <div className="flex flex-col justify-center rounded-xl border border-border bg-surface-subtle p-3.5">
          <span className="text-[9.5px] font-bold uppercase tracking-wider text-ink-2">
            {row.symbol} (Spot)
          </span>
          <span className="mono font-mono text-[21px] font-extrabold text-ink">
            {row.spot !== null
              ? row.spot.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
              : 'No data'}
          </span>
          <span
            className={`mono font-mono text-[11.5px] font-bold ${
              (priceChange ?? 0) >= 0 ? 'text-up-strong' : 'text-down-strong'
            }`}
          >
            {signed ?? 'No data'}
          </span>
        </div>
      </div>

      {/* 4. plan levels */}
      <div className="mt-3 rounded-xl border border-border bg-surface p-3.5">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-[10.5px] font-extrabold uppercase tracking-wider text-ink">Plan Levels</span>
          <span className="text-[10.5px] font-semibold text-ink-2">spot-domain · trigger / stop / targets</span>
        </div>
        <SignalLevelGrid row={row} size="lg" />
      </div>

      {/* 5. lifecycle */}
      <div className="mt-3 flex flex-col gap-2 rounded-xl border border-border bg-surface p-3.5">
        <div className="flex items-center justify-between">
          <span className="text-[10.5px] font-extrabold uppercase tracking-wider text-ink">Signal Lifecycle</span>
          <span className={`rounded-full border px-2.5 py-0.5 text-[11px] font-extrabold ${statusPill}`}>
            {statusText}
          </span>
        </div>
        <SignalStageRail row={row} size="lg" />
      </div>

      {/* 6. validation stack */}
      <div className="mt-3 flex flex-col gap-2 rounded-xl border border-border bg-surface-subtle/70 p-3.5">
        <div className="flex items-center justify-between">
          <span className="text-[10.5px] font-extrabold uppercase tracking-wider text-ink">
            Droid Validation Stack
          </span>
          <span className="text-[10.5px] font-semibold text-ink-2">
            {fill.orderId ? 'executed' : terminal ? 'concluded' : stage.toLowerCase()}
          </span>
        </div>
        <SignalGatesStrip row={row} />
        {row.confidence01 === null && !Array.isArray(raw.confluence_breakdown) ? (
          <p className="text-[11px] text-ink-2">No data — validation stack unavailable.</p>
        ) : null}
      </div>

      {/* 7. reason & notes */}
      {keyReason || bullets || tradeNotes ? (
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5 rounded-xl border border-border bg-surface p-3.5">
            <span className="flex items-center gap-1.5 text-[10.5px] font-extrabold uppercase tracking-wider text-ink">
              🎯 Key Reason
            </span>
            <p className="text-[11.5px] leading-snug text-ink">{keyReason}</p>
            {bullets && bullets.length > 0 ? (
              <ul className="mt-1 flex flex-col gap-1 text-[11px] text-ink-2">
                {bullets.map((bullet, index) => (
                  <li key={index} className="flex items-start gap-1.5">
                    <span className="font-bold text-ink-3">•</span>
                    <span>{bullet}</span>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
          {tradeNotes && tradeNotes.length > 0 ? (
            <div className="flex flex-col gap-1.5 rounded-xl border border-border bg-surface p-3.5">
              <span className="flex items-center gap-1.5 text-[10.5px] font-extrabold uppercase tracking-wider text-ink">
                📋 Trade Notes &amp; Guardrails
              </span>
              <ul className="flex flex-col gap-1 text-[11px] text-ink-2">
                {tradeNotes.map((note, index) => (
                  <li key={index} className="flex items-start gap-1.5">
                    <span className="font-bold text-ink-3">•</span>
                    <span>{note}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}

      {/* 8. action strip */}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        {onExecute ? (
          <button
            type="button"
            onClick={onExecute}
            disabled={!canExecute}
            title={canExecute ? undefined : (eligibility.reason ?? 'Not executable')}
            className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-up-strong px-4 py-3 text-xs font-bold text-white shadow-md shadow-up-strong/20 transition-all hover:bg-up disabled:opacity-50"
          >
            <Zap size={14} className="fill-white" />
            <span>{busy ? 'Executing…' : `Execute Paper Order${fill.quantity !== null ? ` · ${fill.quantity}` : ''}`}</span>
          </button>
        ) : null}

        {contractLabel ? (
          <button
            type="button"
            onClick={handleCopyContract}
            className="flex items-center gap-1.5 rounded-xl border border-border-strong bg-surface px-3.5 py-3 text-xs font-semibold text-ink shadow-sm transition-all hover:bg-surface-subtle"
          >
            {copiedContract ? (
              <>
                <Check size={13} className="text-up-strong" />
                <span>Copied</span>
              </>
            ) : (
              <>
                <Copy size={13} />
                <span>Copy Contract</span>
              </>
            )}
          </button>
        ) : null}

        {onDelete ? (
          <button
            type="button"
            disabled={busy}
            onClick={onDelete}
            className="flex items-center gap-1.5 rounded-xl border border-border bg-surface px-3.5 py-3 text-xs font-semibold text-ink-2 shadow-sm transition-all hover:border-down hover:text-down-strong disabled:opacity-50"
            title={terminal ? `Delete ${row.id}` : 'Close and square off'}
          >
            <Trash2 size={14} />
            <span>Delete</span>
          </button>
        ) : null}

        {onViewDossier ? (
          <button
            type="button"
            onClick={onViewDossier}
            className="flex h-10 w-10 items-center justify-center rounded-xl border border-border bg-surface text-ink-2 shadow-sm transition-all hover:bg-surface-subtle hover:text-ink"
            title="Options chain dossier"
          >
            <ExternalLink size={14} />
          </button>
        ) : null}
      </div>

      {/* 9. footer */}
      <footer className="mt-3 flex items-center justify-between border-t border-border-subtle pt-2 text-[10px] tracking-wider text-ink-3">
        <div className="flex items-center gap-1 font-extrabold text-ink">
          <Shield size={12} className="text-ink-2" />
          <span>DROID</span>
          <span className="font-medium text-ink-3">| DATA · MODELS · DISCIPLINE</span>
        </div>
        <span>TRADE SMARTER. STAY DISCIPLINED.</span>
      </footer>
    </article>
  );
}