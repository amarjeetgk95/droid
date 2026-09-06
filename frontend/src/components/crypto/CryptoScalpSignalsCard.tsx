'use client';

import React, { useState } from 'react';
import {
  TrendingUp,
  TrendingDown,
  Clock,
  Target,
  Copy,
  Check,
  Zap,
  Filter,
  CheckCircle2,
  Trash2,
  Layers,
  ShieldCheck,
} from 'lucide-react';
import { CryptoScalpSignal } from '@/lib/types';

interface CryptoScalpSignalsCardProps {
  signals: CryptoScalpSignal[];
  loading: boolean;
  onRefresh: () => void;
  onDeleteSignal?: (signalId: string) => void;
  selectedAssetFilter?: string;
  onSelectAssetFilter?: (asset: string) => void;
}

// ── FSM STAGES DEFINITION ─────────────────────────────────────────────
const STAGES = [
  { id: 'DETECTED', label: 'Detected' },
  { id: 'VALIDATED', label: 'Validated' },
  { id: 'ARMED', label: 'Armed' },
  { id: 'TRIGGERED', label: 'Triggered' },
  { id: 'CONFIRMED', label: 'Confirmed' },
] as const;

function getStageIndex(state?: string): number {
  if (!state) return 2;
  const s = state.toUpperCase();
  if (s === 'DETECTED') return 0;
  if (s === 'VALIDATED') return 1;
  if (s === 'ARMED') return 2;
  if (s === 'TRIGGERED') return 3;
  if (s === 'CONFIRMED') return 4;
  if (s.includes('TARGET') || s.includes('STOP') || s.includes('CLOSED')) return 5;
  return 2;
}

interface FormattedSignalTimestamp {
  localTimeStr: string;
  localDateStr: string;
  fullLocalStr: string;
  utcStr: string;
  relative: string;
}

function parseAndFormatTimestamp(timestampUtc?: number, timestampStr?: string): FormattedSignalTimestamp {
  let ts = Date.now();
  if (typeof timestampUtc === 'number' && timestampUtc > 0) {
    ts = timestampUtc < 1e11 ? timestampUtc * 1000 : timestampUtc;
  } else if (timestampStr) {
    const parsed = new Date(timestampStr).getTime();
    if (!Number.isNaN(parsed) && parsed > 0) {
      ts = parsed;
    }
  }

  const date = new Date(ts);

  let localTimeStr = '';
  let localDateStr = '';
  let fullLocalStr = '';
  try {
    localTimeStr = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: true });
    localDateStr = date.toLocaleDateString([], { month: 'short', day: '2-digit' });
    fullLocalStr = `${localDateStr}, ${localTimeStr}`;
  } catch {
    fullLocalStr = date.toISOString().substring(0, 16).replace('T', ' ');
    localTimeStr = date.toISOString().substring(11, 16);
    localDateStr = date.toISOString().substring(5, 10);
  }

  const utcHours = String(date.getUTCHours()).padStart(2, '0');
  const utcMins = String(date.getUTCMinutes()).padStart(2, '0');
  const utcStr = `${utcHours}:${utcMins} UTC`;

  const now = Date.now();
  const diffSeconds = Math.max(0, Math.floor((now - ts) / 1000));
  let relative = 'Just now';
  if (diffSeconds >= 86400) {
    const days = Math.floor(diffSeconds / 86400);
    relative = `${days}d ago`;
  } else if (diffSeconds >= 3600) {
    const hrs = Math.floor(diffSeconds / 3600);
    const mins = Math.floor((diffSeconds % 3600) / 60);
    relative = mins > 0 ? `${hrs}h ${mins}m ago` : `${hrs}h ago`;
  } else if (diffSeconds >= 60) {
    relative = `${Math.floor(diffSeconds / 60)}m ago`;
  } else if (diffSeconds > 10) {
    relative = `${diffSeconds}s ago`;
  }

  return { localTimeStr, localDateStr, fullLocalStr, utcStr, relative };
}

function getSpecialId(sig: CryptoScalpSignal): string {
  if (sig.id.startsWith('SCALP-')) {
    const parts = sig.id.split('-');
    if (parts.length >= 5) {
      const symShort = parts[1].replace('USDT', '');
      const stratShort = parts[2].substring(0, 3);
      const tail = parts[4].slice(-4);
      return `#${symShort}-${stratShort}-${tail}`;
    }
  }
  return `#SIG-${sig.id.slice(-6).toUpperCase()}`;
}

export function CryptoScalpSignalsCard({
  signals,
  loading,
  onRefresh,
  onDeleteSignal,
  selectedAssetFilter = 'ALL',
  onSelectAssetFilter,
}: CryptoScalpSignalsCardProps) {
  const [assetFilter, setAssetFilter] = useState<string>(selectedAssetFilter);
  const [dirFilter, setDirFilter] = useState<'ALL' | 'LONG' | 'SHORT'>('ALL');
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const handleAssetSelect = (asset: string) => {
    setAssetFilter(asset);
    if (onSelectAssetFilter) {
      onSelectAssetFilter(asset);
    }
  };

  const handleCopyId = (sig: CryptoScalpSignal, e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(sig.id);
    setCopiedId(sig.id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleCopyPlan = (sig: CryptoScalpSignal) => {
    const timeInfo = parseAndFormatTimestamp(sig.created_at_utc, sig.timestamp);
    const text = `⚡ CRYPTO SCALP [${getSpecialId(sig)}]: ${sig.direction} ${sig.symbol} (${sig.timeframe.toUpperCase()})
Strategy: ${sig.strategy_name}
Status: ${sig.fsm_state || 'ARMED'}
Confidence: ${sig.confidence.toFixed(0)}% | R:R: 1:${sig.risk_reward_ratio.toFixed(1)}
Time: ${timeInfo.fullLocalStr} (${timeInfo.utcStr}) [${timeInfo.relative}]
🎯 Entry Trigger: $${sig.entry_price.toLocaleString()}
🛑 Stop Loss: $${sig.stop_loss.toLocaleString()} (-${sig.risk_percent.toFixed(2)}%)
🎯 Target 1: $${sig.target_1.toLocaleString()}
🎯 Target 2: $${sig.target_2.toLocaleString()}
Rationale: ${sig.rationale}`;

    navigator.clipboard.writeText(text);
    setCopiedId(`plan_${sig.id}`);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleDelete = async (signalId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!onDeleteSignal) return;
    setDeletingId(signalId);
    try {
      await onDeleteSignal(signalId);
    } finally {
      setDeletingId(null);
    }
  };

  const filteredSignals = signals.filter((s) => {
    if (assetFilter !== 'ALL' && s.asset !== assetFilter && s.symbol !== assetFilter) return false;
    if (dirFilter !== 'ALL' && s.direction !== dirFilter) return false;
    return true;
  });

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs space-y-6">
      {/* ── HEADER & CONTROLS ────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-100">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="p-1.5 rounded-lg bg-amber-50 text-amber-700 border border-amber-200">
              <Zap className="w-4 h-4" />
            </div>
            <h2 className="text-base font-semibold tracking-tight text-slate-900">
              Live Scalping Signals
            </h2>
            <span className="text-[11px] px-2.5 py-0.5 rounded-full font-mono bg-slate-100 text-slate-700 font-bold border border-slate-200">
              {filteredSignals.length} Active
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1 leading-relaxed">
            Multi-stage verified setups passing Trigger Integrity, Risk Envelopes, and Confluence Fusion.
          </p>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Asset Pills */}
          <div className="flex bg-slate-100 rounded-lg p-1 border border-slate-200">
            {['ALL', 'BTC', 'ETH'].map((sym) => (
              <button
                key={sym}
                type="button"
                onClick={() => handleAssetSelect(sym)}
                className={`px-3 py-1 text-xs font-medium rounded-md transition-all cursor-pointer ${
                  assetFilter === sym
                    ? 'bg-white text-slate-900 font-semibold shadow-xs border border-slate-200'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                {sym}
              </button>
            ))}
          </div>

          {/* Direction Filter */}
          <div className="flex bg-slate-100 rounded-lg p-1 border border-slate-200">
            {(['ALL', 'LONG', 'SHORT'] as const).map((dir) => (
              <button
                key={dir}
                type="button"
                onClick={() => setDirFilter(dir)}
                className={`px-3 py-1 text-xs font-medium rounded-md transition-all cursor-pointer ${
                  dirFilter === dir
                    ? dir === 'LONG'
                      ? 'bg-emerald-100 text-emerald-800 font-semibold border border-emerald-300'
                      : dir === 'SHORT'
                      ? 'bg-rose-100 text-rose-800 font-semibold border border-rose-300'
                      : 'bg-white text-slate-900 font-semibold shadow-xs border border-slate-200'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                {dir}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── SIGNALS GRID ─────────────────────────────────────────────── */}
      {loading ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {Array.from({ length: 2 }).map((_, i) => (
            <div key={i} className="h-56 bg-slate-50 border border-slate-200 rounded-xl animate-pulse" />
          ))}
        </div>
      ) : filteredSignals.length === 0 ? (
        <div className="p-10 text-center border border-dashed border-slate-200 rounded-xl space-y-3 bg-slate-50/60">
          <div className="w-10 h-10 rounded-full bg-white flex items-center justify-center mx-auto border border-slate-200 text-slate-400 shadow-2xs">
            <Filter className="w-5 h-5" />
          </div>
          <div className="space-y-1">
            <p className="text-sm font-semibold text-slate-900">No Scalp Signals Active Right Now</p>
            <p className="text-xs text-slate-500 max-w-md mx-auto leading-relaxed">
              Institutional criteria require confirmed breakout momentum, 5M/15M MTF trend agreement, and favorable order book depth before a signal is armed.
            </p>
          </div>
          <button
            type="button"
            onClick={onRefresh}
            className="mt-3 inline-flex items-center gap-1.5 px-3.5 py-1.5 bg-slate-900 hover:bg-slate-800 text-white rounded-lg text-xs font-semibold transition-all cursor-pointer shadow-xs"
          >
            <Zap className="w-3.5 h-3.5 text-amber-300" />
            <span>Scan Market Now</span>
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {filteredSignals.map((sig) => {
            const isLong = sig.direction === 'LONG';
            const priceDecimals = sig.entry_price > 100 ? 2 : 4;
            const specialId = getSpecialId(sig);
            const { localTimeStr, localDateStr, fullLocalStr, utcStr, relative: relativeTime } = parseAndFormatTimestamp(sig.created_at_utc, sig.timestamp);
            const stageIndex = getStageIndex(sig.fsm_state);
            const currentState = sig.fsm_state || 'ARMED';

            return (
              <div
                key={sig.id}
                className="relative flex flex-col justify-between rounded-xl border border-slate-200 bg-white hover:border-slate-300 transition-all p-5 shadow-xs space-y-4"
              >
                {/* 1. TOP BAR: Asset, Direction, Special ID, Time & Delete */}
                <div className="flex items-start justify-between gap-3">
                  <div className="flex flex-wrap items-center gap-2">
                    {/* Direction Badge */}
                    <span
                      className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold font-mono tracking-wider ${
                        isLong
                          ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                          : 'bg-rose-50 text-rose-700 border border-rose-200'
                      }`}
                    >
                      {isLong ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
                      {sig.direction}
                    </span>

                    {/* Symbol */}
                    <span className="font-bold text-sm text-slate-900 tracking-tight font-mono">
                      {sig.symbol}
                    </span>

                    {/* Timeframe */}
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200">
                      {sig.timeframe.toUpperCase()}
                    </span>

                    {/* Special ID Badge with Copy */}
                    <button
                      type="button"
                      onClick={(e) => handleCopyId(sig, e)}
                      title={`Full ID: ${sig.id} (Click to copy)`}
                      className="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded bg-slate-100 text-slate-700 hover:bg-slate-200 border border-slate-200 cursor-pointer transition-all"
                    >
                      <span className="font-bold text-slate-900">{specialId}</span>
                      {copiedId === sig.id ? (
                        <Check className="w-2.5 h-2.5 text-emerald-600" />
                      ) : (
                        <Copy className="w-2.5 h-2.5 text-slate-400 hover:text-slate-700" />
                      )}
                    </button>
                  </div>

                  {/* Right Actions: Time & Delete Button */}
                  <div className="flex items-center gap-2">
                    {/* Date / Time */}
                    <div className="text-right">
                      <div className="flex items-center justify-end gap-1 text-[11px] font-mono text-slate-800 font-semibold">
                        <Clock className="w-3 h-3 text-slate-400" />
                        <span>{localTimeStr}</span>
                        <span className="text-slate-500 font-normal text-[10px]">({relativeTime})</span>
                      </div>
                      <span className="text-[10px] font-mono text-slate-400 block mt-0.5">
                        {localDateStr} · {utcStr}
                      </span>
                    </div>

                    {/* Delete Button */}
                    {onDeleteSignal && (
                      <button
                        type="button"
                        onClick={(e) => handleDelete(sig.id, e)}
                        disabled={deletingId === sig.id}
                        title="Dismiss / Delete this signal"
                        className="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-all border border-transparent hover:border-rose-200 cursor-pointer disabled:opacity-50"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </div>

                {/* 2. STAGE PROGRESSION STEPPER (FSM LIFECYCLE) */}
                <div className="bg-slate-50 border border-slate-200/80 rounded-lg p-3 space-y-2">
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="font-mono text-slate-500 font-medium">Signal Lifecycle:</span>
                    <span
                      className={`font-mono text-[10px] font-bold px-2 py-0.5 rounded ${
                        currentState === 'ARMED'
                          ? 'bg-amber-100 text-amber-800 border border-amber-300'
                          : currentState === 'TRIGGERED'
                          ? 'bg-blue-100 text-blue-800 border border-blue-300'
                          : currentState === 'CONFIRMED'
                          ? 'bg-emerald-100 text-emerald-800 border border-emerald-300'
                          : currentState.includes('TARGET_1')
                          ? 'bg-emerald-100 text-emerald-800 border border-emerald-300'
                          : 'bg-slate-200 text-slate-700'
                      }`}
                    >
                      {currentState === 'ARMED' && 'ARMED · Waiting Breakout'}
                      {currentState === 'TRIGGERED' && 'TRIGGERED · Fill Pending'}
                      {currentState === 'CONFIRMED' && 'CONFIRMED · Position Active'}
                      {currentState === 'TARGET_1_HIT' && 'T1 HIT · 50% Booked'}
                      {currentState === 'TARGET_2_HIT' && 'T2 HIT · Completed'}
                      {currentState === 'STOP_LOSS_HIT' && 'STOP HIT · Exited'}
                      {!['ARMED', 'TRIGGERED', 'CONFIRMED', 'TARGET_1_HIT', 'TARGET_2_HIT', 'STOP_LOSS_HIT'].includes(currentState) && currentState}
                    </span>
                  </div>

                  {/* Horizontal Stage Progress Bar */}
                  <div className="flex items-center justify-between gap-1 pt-1">
                    {STAGES.map((st, idx) => {
                      const isPast = idx < stageIndex;
                      const isCurrent = idx === stageIndex;

                      return (
                        <React.Fragment key={st.id}>
                          <div className="flex flex-col items-center gap-1 flex-1">
                            <div
                              className={`w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-mono font-bold transition-all ${
                                isPast
                                  ? 'bg-emerald-600 text-white shadow-2xs'
                                  : isCurrent
                                  ? 'bg-amber-500 text-white ring-2 ring-amber-200 animate-pulse'
                                  : 'bg-slate-200 text-slate-500 border border-slate-300'
                              }`}
                            >
                              {isPast ? <Check className="w-3 h-3 text-white" /> : idx + 1}
                            </div>
                            <span
                              className={`text-[9px] font-mono tracking-tight ${
                                isCurrent
                                  ? 'text-amber-800 font-bold'
                                  : isPast
                                  ? 'text-slate-700 font-medium'
                                  : 'text-slate-400'
                              }`}
                            >
                              {st.label}
                            </span>
                          </div>
                          {idx < STAGES.length - 1 && (
                            <div
                              className={`h-[2px] flex-1 mb-3 transition-all ${
                                idx < stageIndex ? 'bg-emerald-500' : 'bg-slate-200'
                              }`}
                            />
                          )}
                        </React.Fragment>
                      );
                    })}
                  </div>
                </div>

                {/* 3. STRATEGY & METRICS SUMMARY */}
                <div className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-1.5 font-medium text-slate-800">
                    <Layers className="w-3.5 h-3.5 text-blue-600" />
                    <span>{sig.strategy_name}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-[11px] font-mono text-slate-500">
                      Confidence: <strong className="text-emerald-700">{sig.confidence.toFixed(0)}%</strong>
                    </span>
                    <span className="text-[11px] font-mono text-slate-500">
                      R:R <strong className="text-slate-800">1:{sig.risk_reward_ratio.toFixed(1)}</strong>
                    </span>
                  </div>
                </div>

                {/* 4. CLEAN PRICING MATRIX GRID (SOBER LIGHT TONE) */}
                <div className="grid grid-cols-4 gap-2 bg-slate-50 border border-slate-200/80 rounded-lg p-3 text-center">
                  <div>
                    <span className="text-[10px] font-mono text-slate-500 uppercase tracking-wider block">
                      Entry Trigger
                    </span>
                    <span className="text-xs font-mono font-bold text-slate-900">
                      ${sig.entry_price.toFixed(priceDecimals)}
                    </span>
                  </div>

                  <div>
                    <span className="text-[10px] font-mono text-rose-600 uppercase tracking-wider block">
                      Stop Loss
                    </span>
                    <span className="text-xs font-mono font-bold text-rose-600">
                      ${sig.stop_loss.toFixed(priceDecimals)}
                    </span>
                    <span className="text-[9px] font-mono text-rose-500 block">
                      -{sig.risk_percent.toFixed(2)}%
                    </span>
                  </div>

                  <div>
                    <span className="text-[10px] font-mono text-emerald-600 uppercase tracking-wider block">
                      Target 1 (50%)
                    </span>
                    <span className="text-xs font-mono font-bold text-emerald-700">
                      ${sig.target_1.toFixed(priceDecimals)}
                    </span>
                  </div>

                  <div>
                    <span className="text-[10px] font-mono text-emerald-600 uppercase tracking-wider block">
                      Target 2 (Runner)
                    </span>
                    <span className="text-xs font-mono font-bold text-emerald-800">
                      ${sig.target_2.toFixed(priceDecimals)}
                    </span>
                  </div>
                </div>

                {/* 5. RATIONALE & CONFLUENCE FACTORS */}
                <div className="space-y-2">
                  {sig.confluence_factors && sig.confluence_factors.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {sig.confluence_factors.map((factor, idx) => (
                        <span
                          key={idx}
                          className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200"
                        >
                          <CheckCircle2 className="w-2.5 h-2.5 text-emerald-600" />
                          <span>{factor}</span>
                        </span>
                      ))}
                    </div>
                  )}

                  {sig.rationale && (
                    <p className="text-[11px] text-slate-600 leading-relaxed border-l-2 border-slate-300 pl-2.5 py-0.5">
                      {sig.rationale}
                    </p>
                  )}
                </div>

                {/* 6. BOTTOM BAR: Telemetry & Copy Plan */}
                <div className="flex items-center justify-between pt-3 border-t border-slate-100 text-[10px] text-slate-500">
                  <div className="flex items-center gap-3">
                    <span className="inline-flex items-center gap-1 text-emerald-700 font-mono font-medium">
                      <ShieldCheck className="w-3 h-3" />
                      <span>Two-Clock Guard</span>
                    </span>
                    <span className="text-slate-400 font-mono">
                      Created: {fullLocalStr} ({utcStr})
                    </span>
                  </div>

                  <button
                    type="button"
                    onClick={() => handleCopyPlan(sig)}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 transition-all cursor-pointer border border-slate-200 text-xs font-medium"
                  >
                    {copiedId === `plan_${sig.id}` ? (
                      <>
                        <Check className="w-3 h-3 text-emerald-600" />
                        <span className="text-emerald-700 font-semibold">Plan Copied</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3 h-3 text-slate-400" />
                        <span>Copy Plan</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
