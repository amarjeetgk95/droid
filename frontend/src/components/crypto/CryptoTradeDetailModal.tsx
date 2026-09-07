'use client';

import React, { useEffect, useState } from 'react';
import {
  X,
  TrendingUp,
  TrendingDown,
  CheckCircle2,
  AlertTriangle,
  Clock,
  ShieldAlert,
  Zap,
  DollarSign,
  Copy,
  Check,
  Trash2,
  ExternalLink,
  Layers,
  ArrowRight,
  ShieldCheck,
  FileText,
} from 'lucide-react';
import {
  CryptoScalpExecutionRecord,
  CryptoScalpExecutionEvent,
} from '@/lib/types';

interface CryptoTradeDetailModalProps {
  trade: CryptoScalpExecutionRecord | null;
  isOpen: boolean;
  onClose: () => void;
  onDeleteRecord?: (tradeId: string) => Promise<void> | void;
}

export function formatDetailedExitReason(trade: CryptoScalpExecutionRecord): {
  title: string;
  badgeColor: string;
  bannerBg: string;
  icon: typeof CheckCircle2;
  description: string;
} {
  const isLong = trade.direction === 'LONG';
  const sym = trade.symbol.replace('USDT', '');
  const rStr = trade.r_multiple !== 0 ? (trade.r_multiple > 0 ? `+${trade.r_multiple.toFixed(2)}R` : `${trade.r_multiple.toFixed(2)}R`) : '0.00R';
  const exitP = trade.exit_price ? `$${trade.exit_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : 'market price';

  if (trade.position_state === 'ACTIVE') {
    return {
      title: 'Position Active & Running',
      badgeColor: 'bg-blue-50 text-blue-700 border-blue-200',
      bannerBg: 'bg-blue-50/70 border-blue-200/80 text-blue-900',
      icon: Clock,
      description: `Active in-market trade for ${sym} ${trade.direction}. Real-time monitoring toward Target 1 ($${trade.target_1_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}) and Stop Loss ($${trade.current_stop_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}). Live mark-to-market updates active.`,
    };
  }

  if (trade.position_state === 'PARTIALLY_CLOSED') {
    return {
      title: 'Target 1 Hit — 50% Secured, Breakeven Ratchet Active',
      badgeColor: 'bg-amber-50 text-amber-700 border-amber-200',
      bannerBg: 'bg-amber-50/70 border-amber-200/80 text-amber-900',
      icon: Zap,
      description: `Target 1 ($${trade.target_1_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}) reached! 50% of the position has been booked with profit. The remaining runner's stop loss was automatically ratcheted to the entry fill price ($${trade.entry_fill_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}) to eliminate downside risk.`,
    };
  }

  const reason = trade.exit_reason;

  if (reason === 'T2_HIT') {
    return {
      title: 'Target 2 Profit Target Breached (Full Win)',
      badgeColor: 'bg-emerald-50 text-emerald-700 border-emerald-200',
      bannerBg: 'bg-emerald-50/70 border-emerald-200/80 text-emerald-900',
      icon: CheckCircle2,
      description: trade.exit_reason_detail || `Target 2 was breached at ${exitP} on ${sym}. Full position scale-out completed, booking the maximum profit envelope of ${rStr} net of fees and slippage drag.`,
    };
  }

  if (reason === 'BREAKEVEN_STOP' || reason === 'BREAKEVEN_RATCHET') {
    return {
      title: 'Breakeven Stop Hit (Runner Preserved Capital)',
      badgeColor: 'bg-sky-50 text-sky-700 border-sky-200',
      bannerBg: 'bg-sky-50/70 border-sky-200/80 text-sky-900',
      icon: ShieldCheck,
      description: trade.exit_reason_detail || `After banking 50% profit at Target 1, the market retraced to the entry fill price (${exitP}). The remaining runner was closed at breakeven, preserving a positive net realization of ${rStr}.`,
    };
  }

  if (reason === 'INITIAL_STOP') {
    return {
      title: 'Structural Stop Loss Breached (Risk Contained)',
      badgeColor: 'bg-rose-50 text-rose-700 border-rose-200',
      bannerBg: 'bg-rose-50/70 border-rose-200/80 text-rose-900',
      icon: ShieldAlert,
      description: trade.exit_reason_detail || `Adverse market move broke the defined risk boundary at ${exitP} on ${sym}. Position was immediately liquidated to strictly honor the risk envelope at ${rStr}, preventing unconstrained drawdown.`,
    };
  }

  if (reason === 'TIME_STOP') {
    return {
      title: 'Maximum Scalp Duration Exceeded (Time-Out)',
      badgeColor: 'bg-purple-50 text-purple-700 border-purple-200',
      bannerBg: 'bg-purple-50/70 border-purple-200/80 text-purple-900',
      icon: Clock,
      description: trade.exit_reason_detail || `Scalping time-horizon cap reached after ${trade.duration_str}. As momentum decayed without triggering targets, the trade was squared off at ${exitP} (${rStr}) to recycle capital.`,
    };
  }

  if (reason === 'MANUAL_CLOSE') {
    return {
      title: 'Manual Square-Off by Operator',
      badgeColor: 'bg-slate-100 text-slate-700 border-slate-300',
      bannerBg: 'bg-slate-50 border-slate-200 text-slate-800',
      icon: AlertTriangle,
      description: trade.exit_reason_detail || `Position was squared off manually prior to automated target or stop hit at ${exitP} (${rStr}).`,
    };
  }

  return {
    title: `Trade Closed (${trade.exit_reason || 'Reconciled'})`,
    badgeColor: 'bg-slate-100 text-slate-700 border-slate-200',
    bannerBg: 'bg-slate-50 border-slate-200 text-slate-800',
    icon: CheckCircle2,
    description: trade.exit_reason_detail || `Trade closed at ${exitP} with net realization ${rStr}.`,
  };
}

export function CryptoTradeDetailModal({
  trade,
  isOpen,
  onClose,
  onDeleteRecord,
}: CryptoTradeDetailModalProps) {
  const [copiedId, setCopiedId] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
    }
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen || !trade) return null;

  const isLong = trade.direction === 'LONG';
  const isProfit = trade.net_pnl_usd > 0;
  const isLoss = trade.net_pnl_usd < 0;
  const exitDetail = formatDetailedExitReason(trade);
  const ExitIcon = exitDetail.icon;

  const handleCopyId = () => {
    navigator.clipboard.writeText(trade.trade_id);
    setCopiedId(true);
    setTimeout(() => setCopiedId(false), 2000);
  };

  const handleDelete = async () => {
    if (!onDeleteRecord) return;
    if (window.confirm('Permanently delete this execution record from the ledger?')) {
      setDeleting(true);
      try {
        await onDeleteRecord(trade.trade_id);
        onClose();
      } finally {
        setDeleting(false);
      }
    }
  };

  const createdDate = new Date(
    trade.created_at_utc < 1e11 ? trade.created_at_utc * 1000 : trade.created_at_utc
  );
  const closedDate = trade.closed_at_utc
    ? new Date(trade.closed_at_utc < 1e11 ? trade.closed_at_utc * 1000 : trade.closed_at_utc)
    : null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-3 sm:p-5 overflow-y-auto"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="relative w-full max-w-3xl bg-white border border-slate-200 rounded-2xl shadow-2xl overflow-hidden my-6 max-h-[92vh] flex flex-col animate-in fade-in zoom-in-95 duration-150 text-slate-800"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 1. Modal Header */}
        <div className="p-4 sm:p-5 border-b border-slate-100 flex items-start sm:items-center justify-between gap-3 bg-slate-50/60">
          <div className="space-y-1">
            <div className="flex items-center gap-2.5 flex-wrap">
              <span className="text-base font-bold text-slate-900 tracking-tight flex items-center gap-1.5">
                <span>{trade.symbol.replace('USDT', '')} / USDT</span>
              </span>

              {/* Side Pill */}
              <span
                className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-mono font-bold ${
                  isLong
                    ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                    : 'bg-rose-50 text-rose-700 border border-rose-200'
                }`}
              >
                {isLong ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
                {trade.direction}
              </span>

              {/* Strategy Badge */}
              <span className="px-2 py-0.5 rounded-md text-[11px] font-medium bg-slate-100 text-slate-700 border border-slate-200">
                {trade.strategy_name || trade.strategy}
              </span>

              {/* State Badge */}
              <span
                className={`px-2.5 py-0.5 rounded-full text-[11px] font-bold ${
                  trade.position_state === 'ACTIVE'
                    ? 'bg-blue-50 text-blue-700 border border-blue-200'
                    : trade.position_state === 'PARTIALLY_CLOSED'
                    ? 'bg-amber-50 text-amber-700 border border-amber-200'
                    : 'bg-slate-100 text-slate-700 border border-slate-200'
                }`}
              >
                {trade.position_state === 'PARTIALLY_CLOSED' ? 'T1 HIT (50% SECURED)' : trade.position_state}
              </span>
            </div>

            {/* Trade ID & Timestamps */}
            <div className="flex items-center gap-3 text-xs text-slate-500 flex-wrap">
              <div className="flex items-center gap-1 font-mono">
                <span>ID: {trade.trade_id}</span>
                <button
                  type="button"
                  onClick={handleCopyId}
                  className="p-1 hover:text-slate-800 text-slate-400 rounded transition-colors"
                  title="Copy Trade ID"
                >
                  {copiedId ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3" />}
                </button>
              </div>
              <span>•</span>
              <span className="font-mono">Created: {createdDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
              {closedDate && (
                <>
                  <span>•</span>
                  <span className="font-mono">Closed: {closedDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
                </>
              )}
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* 2. Modal Body */}
        <div className="p-4 sm:p-6 space-y-5 overflow-y-auto flex-1 text-xs">
          {/* Detailed Exit Reason Banner */}
          <div className={`p-4 rounded-xl border ${exitDetail.bannerBg} space-y-1.5 transition-all`}>
            <div className="flex items-center gap-2">
              <ExitIcon className="w-4 h-4 shrink-0" />
              <h4 className="font-bold text-sm tracking-tight">{exitDetail.title}</h4>
            </div>
            <p className="text-xs leading-relaxed opacity-90 pl-6">
              {exitDetail.description}
            </p>
          </div>

          {/* Written P&L Hero Card */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {/* Written Profit / Loss Hero */}
            <div className="sm:col-span-2 bg-slate-50 border border-slate-200 rounded-xl p-4 flex flex-col justify-between">
              <div className="flex items-center justify-between pb-2">
                <span className="text-[11px] font-mono uppercase tracking-wider text-slate-500 font-semibold">
                  Realized Trade Outcome
                </span>
                {trade.position_state === 'CLOSED' ? (
                  <span
                    className={`px-2.5 py-1 rounded-full text-xs font-bold font-mono inline-flex items-center gap-1 ${
                      isProfit
                        ? 'bg-emerald-100 text-emerald-800 border border-emerald-300'
                        : isLoss
                        ? 'bg-rose-100 text-rose-800 border border-rose-300'
                        : 'bg-slate-200 text-slate-800'
                    }`}
                  >
                    {isProfit ? 'PROFIT' : isLoss ? 'LOSS' : 'BREAKEVEN'}
                  </span>
                ) : (
                  <span className="px-2.5 py-1 rounded-full text-xs font-bold font-mono bg-blue-100 text-blue-800 border border-blue-200">
                    OPEN POSITION
                  </span>
                )}
              </div>

              <div className="flex items-baseline gap-3 my-1">
                <span
                  className={`text-2xl sm:text-3xl font-bold font-mono tracking-tight ${
                    isProfit ? 'text-emerald-600' : isLoss ? 'text-rose-600' : 'text-slate-800'
                  }`}
                >
                  {trade.position_state === 'CLOSED'
                    ? trade.net_pnl_usd >= 0
                      ? `+$${trade.net_pnl_usd.toFixed(2)} Profit`
                      : `-$${Math.abs(trade.net_pnl_usd).toFixed(2)} Loss`
                    : 'Active MTM'}
                </span>

                <span
                  className={`text-sm font-bold font-mono ${
                    trade.r_multiple > 0
                      ? 'text-emerald-600'
                      : trade.r_multiple < 0
                      ? 'text-rose-600'
                      : 'text-slate-500'
                  }`}
                >
                  ({trade.r_multiple >= 0 ? `+${trade.r_multiple.toFixed(2)}R` : `${trade.r_multiple.toFixed(2)}R`})
                </span>
              </div>

              <div className="text-[11px] text-slate-500 flex items-center gap-3 pt-1 font-mono">
                <span>Return on Risk: <strong>{trade.net_return_pct >= 0 ? `+${trade.net_return_pct.toFixed(1)}%` : `${trade.net_return_pct.toFixed(1)}%`}</strong></span>
                <span>•</span>
                <span>Duration: <strong>{trade.duration_str}</strong></span>
              </div>
            </div>

            {/* Friction & Drag Card */}
            <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 flex flex-col justify-between space-y-2">
              <span className="text-[11px] font-mono uppercase tracking-wider text-slate-500 font-semibold">
                Friction Drag
              </span>
              <div className="space-y-1 text-xs">
                <div className="flex justify-between">
                  <span className="text-slate-500">Theoretical R:</span>
                  <strong className="font-mono">{trade.theoretical_r.toFixed(2)}R</strong>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Execution Drag:</span>
                  <strong className="font-mono text-amber-600">-{trade.execution_drag_r.toFixed(2)}R</strong>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Taker Fees:</span>
                  <strong className="font-mono">${trade.fees_usd.toFixed(2)}</strong>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Slippage:</span>
                  <strong className="font-mono">${trade.slippage_usd.toFixed(2)}</strong>
                </div>
              </div>
            </div>
          </div>

          {/* Execution Milestones & Price Ladder */}
          <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3 shadow-2xs">
            <h5 className="font-bold text-xs uppercase tracking-wider text-slate-600 flex items-center gap-1.5 font-mono">
              <Layers className="w-3.5 h-3.5 text-blue-600" />
              <span>Execution Price Milestones</span>
            </h5>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="bg-slate-50 p-2.5 rounded-lg border border-slate-200/80">
                <span className="text-[10px] text-slate-500 font-mono block">ENTRY FILL</span>
                <span className="text-sm font-bold font-mono text-slate-900 mt-0.5 block">
                  ${trade.entry_fill_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </span>
                <span className="text-[10px] text-slate-400 font-mono">
                  Signal: ${trade.signal_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </span>
              </div>

              <div className="bg-slate-50 p-2.5 rounded-lg border border-slate-200/80">
                <span className="text-[10px] text-slate-500 font-mono block">TARGET 1 (50%)</span>
                <span className="text-sm font-bold font-mono text-emerald-600 mt-0.5 block">
                  ${trade.target_1_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </span>
                <span className="text-[10px] text-slate-400 font-mono">
                  {trade.t1_hit_at ? '✓ Reached' : 'Pending'}
                </span>
              </div>

              <div className="bg-slate-50 p-2.5 rounded-lg border border-slate-200/80">
                <span className="text-[10px] text-slate-500 font-mono block">TARGET 2 (MAX)</span>
                <span className="text-sm font-bold font-mono text-emerald-700 mt-0.5 block">
                  ${trade.target_2_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </span>
                <span className="text-[10px] text-slate-400 font-mono">
                  {trade.t2_hit_at ? '✓ Reached' : 'Pending'}
                </span>
              </div>

              <div className="bg-slate-50 p-2.5 rounded-lg border border-slate-200/80">
                <span className="text-[10px] text-slate-500 font-mono block">
                  {trade.current_stop_price !== trade.initial_stop_price ? 'RATCHETED STOP' : 'INITIAL STOP'}
                </span>
                <span className="text-sm font-bold font-mono text-rose-600 mt-0.5 block">
                  ${trade.current_stop_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </span>
                <span className="text-[10px] text-slate-400 font-mono">
                  Initial: ${trade.initial_stop_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </span>
              </div>
            </div>

            {/* Position Sizing Attributes */}
            <div className="pt-2 border-t border-slate-100 grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px] font-mono text-slate-600">
              <div>Qty Initial: <strong className="text-slate-900">{trade.quantity_initial}</strong></div>
              <div>Qty Closed T1: <strong className="text-slate-900">{trade.quantity_closed_t1}</strong></div>
              <div>Qty Closed Final: <strong className="text-slate-900">{trade.quantity_closed_final}</strong></div>
              <div>Notional: <strong className="text-slate-900">${trade.notional_usd.toFixed(2)}</strong></div>
            </div>
          </div>

          {/* Chronological Audit Event Timeline */}
          <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3 shadow-2xs">
            <div className="flex items-center justify-between">
              <h5 className="font-bold text-xs uppercase tracking-wider text-slate-600 flex items-center gap-1.5 font-mono">
                <FileText className="w-3.5 h-3.5 text-blue-600" />
                <span>Granular Event Audit Timeline ({trade.events?.length || 0} Events)</span>
              </h5>
              <span className="text-[10px] text-slate-400 font-mono">Chronological fills & state transitions</span>
            </div>

            {trade.events && trade.events.length > 0 ? (
              <div className="space-y-2">
                {trade.events.map((ev, idx) => {
                  const evTime = new Date(ev.timestamp_ms);
                  const isPositiveEv = ev.net_pnl_usd > 0;
                  const isNegativeEv = ev.net_pnl_usd < 0;

                  return (
                    <div
                      key={ev.event_id || idx}
                      className="p-3 bg-slate-50 border border-slate-200 rounded-lg flex flex-col sm:flex-row sm:items-center justify-between gap-2.5"
                    >
                      <div className="flex items-center gap-2.5 flex-wrap">
                        <span className="font-mono text-[10px] text-slate-400">
                          {evTime.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                        </span>
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-white text-slate-700 border border-slate-200">
                          {ev.event_type}
                        </span>
                        <span className="text-slate-700">
                          Fill: <strong className="font-mono">${ev.fill_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}</strong>
                        </span>
                        <span className="text-slate-500 font-mono">
                          Qty: {ev.quantity}
                        </span>
                      </div>

                      <div className="flex items-center gap-3 font-mono text-[11px] self-end sm:self-auto">
                        <span className="text-slate-400 text-[10px]">
                          Fee: ${ev.fee_usd.toFixed(3)}
                        </span>
                        {ev.net_pnl_usd !== 0 && (
                          <span
                            className={`font-bold ${
                              isPositiveEv ? 'text-emerald-600' : isNegativeEv ? 'text-rose-600' : 'text-slate-600'
                            }`}
                          >
                            {isPositiveEv ? `+$${ev.net_pnl_usd.toFixed(2)} Profit` : `-$${Math.abs(ev.net_pnl_usd).toFixed(2)} Loss`}
                          </span>
                        )}
                        <span className="text-[10px] text-slate-400">
                          {ev.state_before} &rarr; {ev.state_after}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="p-4 text-center border border-dashed border-slate-200 rounded-lg text-slate-400 text-xs italic bg-slate-50/50">
                No granular tick-by-tick events recorded for this execution record.
              </div>
            )}
          </div>
        </div>

        {/* 3. Modal Footer */}
        <div className="p-3.5 sm:p-4 border-t border-slate-100 flex items-center justify-between bg-slate-50/60">
          <div>
            {onDeleteRecord && (
              <button
                type="button"
                onClick={handleDelete}
                disabled={deleting}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-rose-600 hover:text-rose-700 hover:bg-rose-50 border border-transparent hover:border-rose-200 rounded-lg transition-colors cursor-pointer font-medium disabled:opacity-50"
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>{deleting ? 'Deleting...' : 'Delete Record'}</span>
              </button>
            )}
          </div>

          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 bg-slate-900 hover:bg-slate-800 text-white rounded-lg text-xs font-semibold transition-colors cursor-pointer shadow-xs"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
