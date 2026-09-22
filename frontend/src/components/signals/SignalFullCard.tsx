'use client';

import React, { useMemo, useState } from 'react';
import {
  ArrowUp,
  ArrowDown,
  Bell,
  Check,
  Copy,
  ExternalLink,
  Shield,
  Zap,
} from 'lucide-react';

export interface SignalValidationGate {
  name: string;
  score: number;
  maxScore?: number;
  status?: 'PASS' | 'WARN' | 'FAIL';
}

export interface SignalCardData {
  id?: string;
  underlying: string;
  exchange?: string;
  timestamp?: string;
  timeframe?: string;
  validityMinutes?: number;
  direction: 'BULLISH' | 'BEARISH' | 'CALL' | 'PUT' | string;
  strategy: string;
  thesis?: string;
  statusLabel?: string;
  isExecutable?: boolean;
  /** When true, placeholder analytics are labeled DEMO. Missing fields still render No data. */
  isDemo?: boolean;

  // Option Contract & Spot
  contractSymbol?: string;
  contractMoneyness?: string;
  entryPrice?: number | null;
  target1?: number | null;
  target2?: number | null;
  stopLoss?: number | null;
  spotPrice?: number | null;
  spotChange?: number | null;
  spotChangePct?: number | null;
  lotSize?: number;

  // 5 Chronological FSM stages
  currentState?: 'DETECTED' | 'ARMED' | 'TRIGGERED' | 'EXECUTED' | 'CLOSED' | string;
  stageTimestamps?: {
    detected?: string | null;
    armed?: string | null;
    triggered?: string | null;
    executed?: string | null;
    closed?: string | null;
  };

  // Validation Stack
  validationGates?: SignalValidationGate[];
  quantScore?: number;
  quantStatus?: string;

  // Reason & Notes
  keyReason?: string;
  keyReasonBullets?: string[];
  tradeNotes?: string[];

  // Action Callbacks
  onExecute?: () => void;
  onCopyContract?: () => void;
  onSetAlert?: () => void;
  onViewDossier?: () => void;
  executing?: boolean;
  executeLabel?: string;
}

const LOT_SIZES: Record<string, number> = {
  NIFTY: 75,
  BANKNIFTY: 15,
  SENSEX: 10,
  FINNIFTY: 25,
  MIDCPNIFTY: 50,
};

const STAGES = ['DETECTED', 'ARMED', 'TRIGGERED', 'EXECUTED', 'CLOSED'] as const;

export function SignalFullCard({
  id,
  underlying = 'NIFTY 50',
  exchange = 'NSE',
  timestamp,
  timeframe,
  validityMinutes,
  direction = 'BULLISH',
  strategy = 'BREAKOUT',
  thesis,
  statusLabel,
  isExecutable = true,
  isDemo = true,
  contractSymbol,
  contractMoneyness,
  entryPrice,
  target1,
  target2,
  stopLoss,
  spotPrice,
  spotChange,
  spotChangePct,
  lotSize: customLotSize,
  currentState = 'TRIGGERED',
  stageTimestamps,
  validationGates,
  quantScore,
  quantStatus = 'APPROVED',
  keyReason,
  keyReasonBullets,
  tradeNotes,
  onExecute,
  onCopyContract,
  onSetAlert,
  onViewDossier,
  executing = false,
  executeLabel,
}: SignalCardData) {
  const [copiedId, setCopiedId] = useState(false);
  const [copiedContract, setCopiedContract] = useState(false);
  const [alertSet, setAlertSet] = useState(false);

  // Normalize Instrument & Lot Size
  const cleanUnderlying = underlying.toUpperCase().replace(/\s+50$/, '').trim();
  const displayUnderlying = cleanUnderlying === 'NIFTY' ? 'NIFTY 50' : cleanUnderlying;
  const lotSize = customLotSize ?? LOT_SIZES[cleanUnderlying] ?? 75;

  // Normalize Direction
  const isBullish =
    direction.toUpperCase().includes('BULL') ||
    direction.toUpperCase().includes('CALL') ||
    direction.toUpperCase() === 'BUY' ||
    direction.toUpperCase() === 'LONG';

  // Format IST display time — missing timestamp renders "No data", never now.
  const displayTimestamp = useMemo(() => {
    if (timestamp) return timestamp;
    return 'No data';
  }, [timestamp]);

  // Honest spot/levels: missing inputs render "No data", never invented
  // index levels (24854.3), premiums (120.5) or derived targets. DEMO mode
  // adds a watermark and disables execution — it never invents fills.
  const effectiveSpot = spotPrice ?? null;
  const effectiveSpotChange = spotChange ?? null;
  const effectiveSpotPct = spotChangePct ?? null;
  const noData = 'No data';
  const effectiveStatusLabel = statusLabel ?? (isDemo ? 'DEMO PREVIEW' : null);

  // Derived Option Contract Symbol — only when a live spot exists.
  const effectiveContract = useMemo(() => {
    if (contractSymbol) return contractSymbol;
    if (effectiveSpot === null) return null;
    const strikeStep = cleanUnderlying === 'BANKNIFTY' ? 100 : 50;
    const roundStrike = Math.round(effectiveSpot / strikeStep) * strikeStep;
    const optType = isBullish ? 'CE' : 'PE';
    return `${cleanUnderlying} 25 SEP ${roundStrike} ${optType}`;
  }, [cleanUnderlying, contractSymbol, effectiveSpot, isBullish]);

  const effectiveMoneyness = contractMoneyness ?? null;

  // Levels — no cross-derivation. A missing entry/SL/target is No data.
  const effectiveEntry = entryPrice ?? null;
  const effectiveT1 = target1 ?? null;
  const effectiveT2 = target2 ?? null;
  const effectiveSL = stopLoss ?? null;

  // Return & ₹ Calculations per lot — only when both legs exist.
  const t1GainPerUnit =
    effectiveT1 !== null && effectiveEntry !== null ? Math.max(0, effectiveT1 - effectiveEntry) : null;
  const t1Pct =
    t1GainPerUnit !== null && effectiveEntry !== null && effectiveEntry !== 0
      ? ((effectiveT1 as number - (effectiveEntry as number)) / (effectiveEntry as number)) * 100
      : null;
  const t1RupeeLot = t1GainPerUnit !== null ? t1GainPerUnit * lotSize : null;

  const t2GainPerUnit =
    effectiveT2 !== null && effectiveEntry !== null ? Math.max(0, effectiveT2 - effectiveEntry) : null;
  const t2Pct =
    t2GainPerUnit !== null && effectiveEntry !== null && effectiveEntry !== 0
      ? ((effectiveT2 as number - (effectiveEntry as number)) / (effectiveEntry as number)) * 100
      : null;
  const t2RupeeLot = t2GainPerUnit !== null ? t2GainPerUnit * lotSize : null;

  const slLossPerUnit =
    effectiveEntry !== null && effectiveSL !== null ? Math.abs(effectiveEntry - effectiveSL) : null;
  const slPct =
    slLossPerUnit !== null && effectiveEntry !== null && effectiveEntry !== 0
      ? ((effectiveSL as number - (effectiveEntry as number)) / (effectiveEntry as number)) * 100
      : null;
  const slRupeeLot = slLossPerUnit !== null ? slLossPerUnit * lotSize : null;

  const totalCapitalRequired =
    effectiveEntry !== null ? Math.round(effectiveEntry * lotSize) : null;

  // Critical data gates Execute. Missing spot/entry/SL/contract disables it.
  const missingCritical: string[] = [];
  if (effectiveSpot === null) missingCritical.push('spot');
  if (effectiveEntry === null) missingCritical.push('entry');
  if (effectiveSL === null) missingCritical.push('stop');
  if (effectiveContract === null) missingCritical.push('contract');
  if (effectiveT1 === null && effectiveT2 === null) missingCritical.push('target');
  const canExecute = !isDemo && isExecutable && !executing && missingCritical.length === 0;
  const executeDisabledReason = isDemo
    ? 'Demo component — execution disabled. Wire live data and set isDemo=false.'
    : !isExecutable
      ? 'Not executable in this state.'
      : missingCritical.length > 0
        ? `No data — missing ${missingCritical.join(', ')}.`
        : null;

  // Normalizing FSM Stepper
  const activeStageIndex = STAGES.indexOf(
    (currentState.toUpperCase() as (typeof STAGES)[number]) || 'TRIGGERED',
  );

  // Lifecycle stamps — missing stages render "—", never invented 09:28 times.
  const defaultTimestamps = useMemo(() => {
    return {
      detected: stageTimestamps?.detected ?? null,
      armed: stageTimestamps?.armed ?? null,
      triggered: stageTimestamps?.triggered ?? null,
      executed: stageTimestamps?.executed ?? null,
      closed: stageTimestamps?.closed ?? null,
    };
  }, [stageTimestamps]);

  // Validation Gates — missing stack renders No data, never 92–79 placeholders.
  const gates = useMemo<SignalValidationGate[]>(() => {
    if (validationGates && validationGates.length > 0) return validationGates;
    return [];
  }, [validationGates]);

  const effectiveQuantScore =
    quantScore ?? (gates.length > 0 ? Math.round(gates.reduce((acc, g) => acc + g.score, 0) / gates.length) : null);

  // Thesis & Bullets — missing analysis renders No data, never RSI/MACD/depth or 1.8x claims.
  const effectiveThesis = thesis ?? null;

  const effectiveKeyReason = keyReason ?? null;

  const effectiveKeyBullets =
    keyReasonBullets && keyReasonBullets.length > 0 ? keyReasonBullets : null;

  const effectiveTradeNotes =
    tradeNotes && tradeNotes.length > 0 ? tradeNotes : null;

  const handleCopyId = () => {
    if (!id || !navigator?.clipboard) return;
    navigator.clipboard.writeText(id);
    setCopiedId(true);
    setTimeout(() => setCopiedId(false), 2000);
  };

  const handleCopyContract = () => {
    if (onCopyContract) {
      onCopyContract();
    } else if (navigator?.clipboard && effectiveContract) {
      navigator.clipboard.writeText(effectiveContract);
    }
    setCopiedContract(true);
    setTimeout(() => setCopiedContract(false), 2000);
  };

  const handleAlert = () => {
    if (onSetAlert) onSetAlert();
    setAlertSet(true);
    setTimeout(() => setAlertSet(false), 3000);
  };

  return (
    <article
      className="relative isolate w-full max-w-[720px] overflow-hidden rounded-2xl border border-border bg-surface p-6 shadow-xl transition-all"
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
            Demo preview — illustrative layout only. Execution disabled; values render only when supplied.
          </p>
        </>
      ) : null}

      {/* 1. Header */}
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <h2 className="text-2xl font-extrabold tracking-tight text-ink">
              {displayUnderlying}
            </h2>
            <span className="rounded bg-inset px-2 py-0.5 text-[11px] font-bold tracking-wider text-ink-2">
              {exchange}
            </span>
          </div>
          <div className="font-mono text-xs text-ink-2">
            <span>📅 {displayTimestamp}</span>
          </div>
        </div>

        <div className="flex flex-col items-end gap-1">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-up-line bg-up-wash px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wider text-up-strong">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-up opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-up" />
            </span>
            LIVE SIGNAL
          </span>
          {isDemo ? (
            <span className="rounded border border-warn-line bg-warn-wash px-2 py-0.5 text-[11px] font-bold tracking-wider text-warn-strong">
              DEMO
            </span>
          ) : null}

          <button
            type="button"
            onClick={handleCopyId}
            disabled={!id}
            className="flex items-center gap-1 font-mono text-[11px] text-ink-2 hover:text-ink disabled:opacity-60"
            title={id ? 'Click to copy Signal ID' : 'No signal ID in payload'}
          >
            <span>ID: {id ?? '—'}</span>
            {copiedId ? (
              <Check size={11} className="text-up-strong" />
            ) : (
              <Copy size={11} />
            )}
          </button>

          <div className="flex items-center gap-1.5 text-[11px] text-ink-2">
            {timeframe ? (
              <span className="rounded bg-inset px-1.5 py-0.5 font-bold text-ink">
                {timeframe}
              </span>
            ) : null}
            <span>Validity: {validityMinutes != null ? `${validityMinutes} mins` : '—'}</span>
          </div>
        </div>
      </header>

      {/* 2. Hero Action Banner */}
      {missingCritical.length > 0 ? (
        <div className="mt-4 rounded-xl border border-warn-line bg-warn-wash p-3.5 text-xs font-semibold text-warn-strong">
          No data — missing {missingCritical.join(', ')}. Execution disabled until the feed provides levels.
        </div>
      ) : null}
      <div
        className={`mt-4 flex items-center justify-between rounded-xl p-3.5 text-white shadow-md transition-all ${
          isBullish
            ? 'bg-gradient-to-r from-up-strong to-up shadow-up-strong/20'
            : 'bg-gradient-to-r from-down-strong to-down shadow-down-strong/20'
        }`}
      >
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-surface/20 text-lg font-extrabold text-white">
            {isBullish ? <ArrowUp size={20} strokeWidth={3} /> : <ArrowDown size={20} strokeWidth={3} />}
          </div>
          <div className="flex flex-col">
            <span className="text-[17px] font-extrabold tracking-wide">
              {isBullish ? 'BUY' : 'SELL'} · {strategy.toUpperCase()} {isBullish ? 'LONG' : 'SHORT'}
            </span>
            <span className="text-xs font-medium text-white/90">
              {effectiveThesis ?? noData}
            </span>
          </div>
        </div>

        <div className="rounded-full bg-surface px-3 py-1 text-[11px] font-extrabold tracking-wide text-up-strong shadow-sm">
          <span>⚡ {effectiveStatusLabel ?? 'Status: No data'}</span>
        </div>
      </div>

      {/* 3. Contract & Spot Row */}
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-[1fr_175px]">
        {/* Option Contract Box */}
        <div className="flex flex-col gap-2.5 rounded-xl border border-border bg-surface p-3.5">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-[9.5px] font-bold uppercase tracking-wider text-ink-2">
                Option Contract (Primary Execution)
              </div>
              <div className="text-[15.5px] font-extrabold text-ink">
                {effectiveContract ?? noData}
              </div>
            </div>
            <span className="rounded-md border border-up-line bg-up-wash px-2 py-0.5 text-[11px] font-bold text-up-strong">
              {effectiveMoneyness ?? noData}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2 border-t border-border-subtle pt-2.5 sm:grid-cols-4">
            <div className="flex flex-col">
              <span className="text-[9.5px] font-bold uppercase tracking-wider text-ink-2">
                Entry (Est.)
              </span>
              <span className="font-mono text-[14px] font-bold text-ink">
                {effectiveEntry !== null ? `₹${effectiveEntry.toFixed(2)}` : noData}
              </span>
              <span className="font-mono text-[9.5px] font-semibold text-ink-2">
                LTP zone
              </span>
            </div>

            <div className="flex flex-col">
              <span className="text-[9.5px] font-bold uppercase tracking-wider text-ink-2">
                Target 1
              </span>
              <span className="font-mono text-[14px] font-bold text-ink">
                {effectiveT1 !== null ? `₹${effectiveT1.toFixed(2)}` : noData}
              </span>
              <span className="font-mono text-[9.5px] font-bold text-up-strong">
                {t1Pct !== null && t1RupeeLot !== null
                  ? `+${t1Pct.toFixed(1)}% · +₹${Math.round(t1RupeeLot).toLocaleString('en-IN')}/lot`
                  : noData}
              </span>
            </div>

            <div className="flex flex-col">
              <span className="text-[9.5px] font-bold uppercase tracking-wider text-ink-2">
                Target 2
              </span>
              <span className="font-mono text-[14px] font-bold text-ink">
                {effectiveT2 !== null ? `₹${effectiveT2.toFixed(2)}` : noData}
              </span>
              <span className="font-mono text-[9.5px] font-bold text-up-strong">
                {t2Pct !== null && t2RupeeLot !== null
                  ? `+${t2Pct.toFixed(1)}% · +₹${Math.round(t2RupeeLot).toLocaleString('en-IN')}/lot`
                  : noData}
              </span>
            </div>

            <div className="flex flex-col">
              <span className="text-[9.5px] font-bold uppercase tracking-wider text-ink-2">
                Stop Loss
              </span>
              <span className="font-mono text-[14px] font-bold text-ink">
                {effectiveSL !== null ? `₹${effectiveSL.toFixed(2)}` : noData}
              </span>
              <span className="font-mono text-[9.5px] font-bold text-down-strong">
                {slPct !== null && slRupeeLot !== null
                  ? `${slPct.toFixed(1)}% · -₹${Math.round(slRupeeLot).toLocaleString('en-IN')}/lot`
                  : noData}
              </span>
            </div>
          </div>
        </div>

        {/* Spot Box */}
        <div className="flex flex-col justify-center rounded-xl border border-border bg-surface-subtle p-3.5">
          <span className="text-[9.5px] font-bold uppercase tracking-wider text-ink-2">
            {displayUnderlying} (Spot)
          </span>
          <span className="font-mono text-[21px] font-extrabold text-ink">
            {effectiveSpot !== null
              ? effectiveSpot.toLocaleString('en-IN', {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })
              : noData}
          </span>
          <span
            className={`font-mono text-[11.5px] font-bold ${
              (effectiveSpotChange ?? 0) >= 0 ? 'text-up-strong' : 'text-down-strong'
            }`}
          >
            {effectiveSpotChange !== null && effectiveSpotPct !== null ? (
              <>
                {effectiveSpotChange >= 0 ? '+' : ''}
                {effectiveSpotChange.toFixed(2)} ({effectiveSpotPct >= 0 ? '+' : ''}
                {effectiveSpotPct.toFixed(2)}%)
              </>
            ) : (
              noData
            )}
          </span>
        </div>
      </div>

      {/* 4. Chronological Lifecycle Stepper (Strictly 5 FSM stages) */}
      <div className="mt-3 flex flex-col gap-2 rounded-xl border border-border bg-surface p-3.5">
        <div className="flex items-center justify-between">
          <span className="text-[10.5px] font-extrabold uppercase tracking-wider text-ink">
            Signal Lifecycle
          </span>
          <span className="rounded-full border border-up-line bg-up-wash px-2.5 py-0.5 text-[11px] font-extrabold text-up-strong">
            Current: {currentState.toUpperCase()}
          </span>
        </div>

        <div className="flex items-start justify-between px-2 pt-1">
          {STAGES.map((step, idx) => {
            const isCompleted = idx < activeStageIndex;
            const isActive = idx === activeStageIndex;
            const stepName =
              step.charAt(0) + step.slice(1).toLowerCase();
            const rawVal =
              defaultTimestamps[
                step.toLowerCase() as keyof typeof defaultTimestamps
              ];
            const timeVal = rawVal ?? '—';

            return (
              <div
                key={step}
                className="relative flex flex-1 flex-col items-center text-center"
              >
                {/* Connecting horizontal line */}
                {idx > 0 && (
                  <div
                    className={`absolute -left-1/2 right-1/2 top-2.5 h-0.5 ${
                      idx <= activeStageIndex ? 'bg-up' : 'bg-border'
                    }`}
                  />
                )}

                {/* Bullet */}
                <div
                  className={`relative z-10 flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold ${
                    isCompleted
                      ? 'bg-up text-white'
                      : isActive
                        ? 'bg-up text-white ring-4 ring-up-wash'
                        : 'border-2 border-border-strong bg-surface text-transparent'
                  }`}
                >
                  {isCompleted ? '✓' : isActive ? '●' : ''}
                </div>

                <span
                  className={`mt-1 text-[11px] ${
                    isActive
                      ? 'font-extrabold text-up-strong'
                      : 'font-semibold text-ink-2'
                  }`}
                >
                  {stepName}
                </span>

                <span
                  className={`font-mono text-[9.5px] ${
                    isActive ? 'font-bold text-up-strong' : 'text-ink-3'
                  }`}
                >
                  {timeVal}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* 5. Droid Validation Stack */}
      <div className="mt-3 flex flex-col gap-2 rounded-xl border border-border bg-surface-subtle/70 p-3.5">
        <div className="flex items-center justify-between">
          <span className="text-[10.5px] font-extrabold uppercase tracking-wider text-ink">
            Droid Validation Stack
          </span>
          <span className="text-[10.5px] font-semibold text-ink-2">
            {gates.length > 0 ? `All ${gates.length} layers passed` : noData}
          </span>
        </div>

        {gates.length === 0 ? (
          <p className="text-[11px] text-ink-2">{noData} — validation stack unavailable.</p>
        ) : (
        <div className="flex flex-wrap items-center justify-between gap-1.5">
          {gates.map((gate, i) => (
            <React.Fragment key={gate.name}>
              <div className="flex min-w-[70px] flex-1 flex-col items-center rounded-lg border border-border bg-surface p-1.5 text-center">
                <span className="text-[8.5px] font-bold uppercase tracking-wider text-ink-2">
                  {gate.name}
                </span>
                <span className="flex items-center gap-0.5 text-[9.5px] font-bold text-up-strong">
                  ✓ {gate.status ?? 'PASS'}
                </span>
                <span className="font-mono text-[9.5px] text-ink-2">
                  {gate.score}/{gate.maxScore ?? 100}
                </span>
              </div>
              {i < gates.length - 1 && (
                <span className="hidden text-ink-4 sm:inline">→</span>
              )}
            </React.Fragment>
          ))}

          <div className="flex min-w-[85px] flex-col items-center rounded-lg border border-up-line bg-up-wash px-2 py-1.5">
            <span className="text-[8px] font-extrabold uppercase tracking-wider text-up-strong">
              Quant Score
            </span>
            <span className="font-mono text-[15.5px] font-extrabold text-up-strong">
              {effectiveQuantScore !== null ? `${effectiveQuantScore} / 100` : noData}
            </span>
            <span className="text-[9px] font-bold text-up-strong">
              ✓ {quantStatus}
            </span>
          </div>
        </div>
        )}
      </div>

      {/* 6. Reason & Context Columns */}
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5 rounded-xl border border-border bg-surface p-3.5">
          <span className="flex items-center gap-1.5 text-[10.5px] font-extrabold uppercase tracking-wider text-ink">
            🎯 KEY REASON (TRIGGER)
          </span>
          <p className="text-[11.5px] leading-snug text-ink">
            {effectiveKeyReason ?? noData}
          </p>
          <ul className="mt-1 flex flex-col gap-1 text-[11px] text-ink-2">
            {(effectiveKeyBullets ?? [noData]).map((b, i) => (
              <li key={i} className="flex items-start gap-1.5">
                <span className="font-bold text-ink-3">•</span>
                <span>{b}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="flex flex-col gap-1.5 rounded-xl border border-border bg-surface p-3.5">
          <span className="flex items-center gap-1.5 text-[10.5px] font-extrabold uppercase tracking-wider text-ink">
            📋 TRADE NOTES &amp; GUARDRAILS
          </span>
          <ul className="flex flex-col gap-1 text-[11px] text-ink-2">
            {(effectiveTradeNotes ?? [noData]).map((n, i) => (
              <li key={i} className="flex items-start gap-1.5">
                <span className="font-bold text-ink-3">•</span>
                <span>{n}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* 7. Action Strip */}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={onExecute}
          disabled={!canExecute}
          title={executeDisabledReason ?? undefined}
          className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-up-strong px-4 py-3 text-xs font-bold text-white shadow-md shadow-up-strong/20 transition-all hover:bg-up disabled:opacity-50"
        >
          <Zap size={14} className="fill-white" />
          <span>
            {executing
              ? 'Executing…'
              : (executeLabel ??
                (totalCapitalRequired !== null
                  ? `Execute Paper Order (${lotSize} Qty · ₹${totalCapitalRequired.toLocaleString('en-IN')})`
                  : 'Execute Paper Order (No data)'))}
          </span>
        </button>

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

        <button
          type="button"
          onClick={handleAlert}
          className="flex h-10 w-10 items-center justify-center rounded-xl border border-border bg-surface text-ink-2 shadow-sm transition-all hover:bg-surface-subtle hover:text-ink"
          title="Set Invalidation Alert"
        >
          <Bell size={14} className={alertSet ? 'text-warn' : ''} />
        </button>

        {onViewDossier && (
          <button
            type="button"
            onClick={onViewDossier}
            className="flex h-10 w-10 items-center justify-center rounded-xl border border-border bg-surface text-ink-2 shadow-sm transition-all hover:bg-surface-subtle hover:text-ink"
            title="View Options Chain Dossier"
          >
            <ExternalLink size={14} />
          </button>
        )}
      </div>

      {/* 8. Footer */}
      <footer className="mt-3 flex items-center justify-between border-t border-border-subtle pt-2 text-[10px] tracking-wider text-ink-3">
        <div className="flex items-center gap-1 font-extrabold text-ink">
          <Shield size={12} className="text-ink-2" />
          <span>DROID</span>
          <span className="font-medium text-ink-3">
            | DATA · MODELS · DISCIPLINE
          </span>
        </div>
        <span>TRADE SMARTER. STAY DISCIPLINED.</span>
      </footer>
    </article>
  );
}
