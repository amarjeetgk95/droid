'use client';

import { useState, useEffect, useMemo } from 'react';
import { PortfolioSummary } from '@/lib/types';
import { Wallet, TrendingUp, TrendingDown, ShieldAlert, RotateCcw, AlertOctagon, X, Download } from 'lucide-react';

type BusyAction = 'square-off-all' | 'reset' | null;

export function PortfolioBanner({
  summary,
  onSquareOffAll,
  onReset,
  loading,
  busyAction,
  pnlSpark,
  onExportOrders,
  onExportPositions,
}: {
  summary: PortfolioSummary;
  onSquareOffAll: () => void;
  onReset: () => void;
  loading: boolean;
  busyAction?: BusyAction;
  pnlSpark?: number[];
  onExportOrders?: () => void;
  onExportPositions?: () => void;
}) {
  const [confirmTarget, setConfirmTarget] = useState<Exclude<BusyAction, null> | null>(null);
  const isPos = summary.total_portfolio_pnl >= 0;
  const isMtmPos = summary.total_unrealized_pnl >= 0;
  // Prefer per-action busy state when provided, fall back to legacy global loading.
  const squareOffBusy = busyAction !== undefined ? busyAction === 'square-off-all' : loading;
  const resetBusy = busyAction !== undefined ? busyAction === 'reset' : loading;
  const anyBusy = squareOffBusy || resetBusy;

  // Escape closes the confirm dialog.
  useEffect(() => {
    if (!confirmTarget) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setConfirmTarget(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [confirmTarget]);

  const handleConfirm = () => {
    if (confirmTarget === 'square-off-all') onSquareOffAll();
    else if (confirmTarget === 'reset') onReset();
    setConfirmTarget(null);
  };

  const marginBar = summary.margin_utilization_pct > 90 ? 'bg-rose-500' : summary.margin_utilization_pct > 70 ? 'bg-amber-500' : 'bg-primary';

  const sparkPath = useMemo(() => {
    const data = (pnlSpark ?? []).slice(-30);
    if (data.length < 2) return null;
    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;
    const w = 120;
    const h = 28;
    const pts = data.map((v, i) => {
      const x = (i / (data.length - 1)) * w;
      const y = h - 3 - ((v - min) / range) * (h - 6);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });
    return { d: `M${pts.join(' L')}`, up: data[data.length - 1] >= data[0] };
  }, [pnlSpark]);

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-4 shadow-xs">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Wallet className="w-5 h-5 text-primary" />
          <h2 className="text-sm font-bold text-foreground">Virtual Trading Account (Paper Trading)</h2>
        </div>

        {/* Quick Action Controls */}
        <div className="flex items-center gap-2 flex-wrap">
          {(onExportOrders || onExportPositions) && (
            <span className="flex items-center gap-1">
              {onExportPositions && (
                <button
                  type="button"
                  onClick={onExportPositions}
                  title="Export positions CSV"
                  className="flex items-center gap-1 px-2 py-1.5 bg-secondary hover:bg-secondary/80 text-muted-foreground hover:text-foreground rounded-lg text-[11px] font-bold transition-all cursor-pointer border border-border"
                >
                  <Download className="w-3 h-3" /> Positions
                </button>
              )}
              {onExportOrders && (
                <button
                  type="button"
                  onClick={onExportOrders}
                  title="Export orders CSV"
                  className="flex items-center gap-1 px-2 py-1.5 bg-secondary hover:bg-secondary/80 text-muted-foreground hover:text-foreground rounded-lg text-[11px] font-bold transition-all cursor-pointer border border-border"
                >
                  <Download className="w-3 h-3" /> Orders
                </button>
              )}
            </span>
          )}
          <button
            onClick={() => setConfirmTarget('square-off-all')}
            disabled={squareOffBusy || summary.open_positions_count === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-destructive hover:bg-destructive/90 text-destructive-foreground rounded-lg text-xs font-bold transition-all cursor-pointer shadow-xs disabled:opacity-40"
          >
            <AlertOctagon className="w-3.5 h-3.5" />
            <span>{squareOffBusy ? 'Squaring off…' : `Square Off All (${summary.open_positions_count})`}</span>
          </button>

          <button
            onClick={() => setConfirmTarget('reset')}
            disabled={resetBusy}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-secondary hover:bg-secondary/80 text-foreground rounded-lg text-xs font-bold transition-all cursor-pointer border border-border"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>{resetBusy ? 'Resetting…' : 'Reset Account'}</span>
          </button>
        </div>
      </div>

      {/* Account Metrics Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {/* Virtual Capital & Equity */}
        <div className="bg-secondary/40 border border-border rounded-xl p-3 space-y-1">
          <span className="text-[11px] text-muted-foreground font-semibold">Total Account Value</span>
          <div className="text-base font-mono font-black text-foreground">
            ₹{(summary.virtual_capital + summary.total_portfolio_pnl).toLocaleString('en-IN')}
          </div>
          <span className="text-[10px] text-muted-foreground font-mono">
            Base: ₹{summary.virtual_capital.toLocaleString('en-IN')}
          </span>
        </div>

        {/* Unrealized MTM */}
        <div className="bg-secondary/40 border border-border rounded-xl p-3 space-y-1">
          <span className="text-[11px] text-muted-foreground font-semibold flex items-center justify-between">
            Open Positions MTM
            {isMtmPos ? <TrendingUp className="w-3.5 h-3.5 text-emerald-400" /> : <TrendingDown className="w-3.5 h-3.5 text-rose-400" />}
          </span>
          <div className={`text-base font-mono font-black ${isMtmPos ? 'text-emerald-400' : 'text-rose-400'}`}>
            {isMtmPos ? '+' : ''}₹{summary.total_unrealized_pnl.toLocaleString('en-IN')}
          </div>
          <span className="text-[10px] text-muted-foreground font-mono">
            Active: <strong>{summary.open_positions_count} open</strong>
          </span>
        </div>

        {/* Total Realized & Net P&L */}
        <div className="bg-secondary/40 border border-border rounded-xl p-3 space-y-1">
          <span className="text-[11px] text-muted-foreground font-semibold flex items-center justify-between">
            Net Total P&L
            {isPos ? <TrendingUp className="w-3.5 h-3.5 text-emerald-400" /> : <TrendingDown className="w-3.5 h-3.5 text-rose-400" />}
          </span>
          <div className="flex items-end justify-between gap-2">
            <div className={`text-base font-mono font-black ${isPos ? 'text-emerald-400' : 'text-rose-400'}`}>
              {isPos ? '+' : ''}₹{summary.total_portfolio_pnl.toLocaleString('en-IN')}
            </div>
            {sparkPath && (
              <svg width="120" height="28" viewBox="0 0 120 28" className="shrink-0 opacity-90" aria-hidden="true">
                <path d={sparkPath.d} fill="none" stroke={sparkPath.up ? '#34d399' : '#fb7185'} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
              </svg>
            )}
          </div>
          <span className="text-[10px] text-muted-foreground font-mono">
            Realized: <strong className={summary.total_realized_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}>{summary.total_realized_pnl >= 0 ? '+' : ''}₹{summary.total_realized_pnl.toLocaleString('en-IN')}</strong>
          </span>
        </div>

        {/* Margin Usage */}
        <div className="bg-secondary/40 border border-border rounded-xl p-3 space-y-1">
          <span className="text-[11px] text-muted-foreground font-semibold flex items-center justify-between">
            Available Margin
            <ShieldAlert className="w-3.5 h-3.5 text-primary" />
          </span>
          <div className="text-base font-mono font-black text-foreground">
            ₹{summary.available_margin.toLocaleString('en-IN')}
          </div>
          {/* Usage Bar */}
          <div className="space-y-1 pt-0.5">
            <div className="w-full bg-secondary h-1.5 rounded-full overflow-hidden">
              <div
                className={`h-full transition-all ${marginBar}`}
                style={{ width: `${Math.min(100, summary.margin_utilization_pct)}%` }}
              ></div>
            </div>
            <span className="text-[9px] text-muted-foreground font-mono block">
              Used: ₹{summary.used_margin.toLocaleString('en-IN')} ({summary.margin_utilization_pct}%)
            </span>
          </div>
        </div>
      </div>

      {/* Confirm destructive action — avoids accidental wipe of the virtual account */}
      {confirmTarget && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          onClick={() => !anyBusy && setConfirmTarget(null)}
          role="presentation"
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label={confirmTarget === 'square-off-all' ? 'Confirm square off all' : 'Confirm reset account'}
            className="w-full max-w-sm rounded-xl border border-border bg-card p-5 space-y-3 shadow-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-2">
              <h3 className="text-sm font-bold text-foreground">
                {confirmTarget === 'square-off-all' ? 'Square off all positions?' : 'Reset virtual account?'}
              </h3>
              <button
                type="button"
                onClick={() => setConfirmTarget(null)}
                className="text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                aria-label="Close confirmation"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            {confirmTarget === 'square-off-all' ? (
              <p className="text-xs text-muted-foreground leading-relaxed">
                You will close <strong className="text-foreground">{summary.open_positions_count} open position(s)</strong> and
                realize approx <strong className={isMtmPos ? 'text-emerald-400' : 'text-rose-400'}>
                  {isMtmPos ? '+' : ''}₹{summary.total_unrealized_pnl.toLocaleString('en-IN')}
                </strong> of open MTM. Booked P&L so far:{' '}
                <strong className="text-foreground">₹{summary.total_realized_pnl.toLocaleString('en-IN')}</strong>.
              </p>
            ) : (
              <p className="text-xs text-muted-foreground leading-relaxed">
                This clears all positions and order history and resets P&L to zero (base ₹
                {summary.virtual_capital.toLocaleString('en-IN')}). This cannot be undone.
              </p>
            )}
            <div className="flex justify-end gap-2 pt-1">
              <button
                type="button"
                onClick={() => setConfirmTarget(null)}
                className="px-3 py-1.5 rounded-lg bg-secondary hover:bg-secondary/80 text-foreground border border-border text-xs font-bold transition-all cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirm}
                disabled={anyBusy}
                className="px-3 py-1.5 rounded-lg bg-destructive hover:bg-destructive/90 text-destructive-foreground text-xs font-bold transition-all cursor-pointer disabled:opacity-50"
              >
                {confirmTarget === 'square-off-all' ? 'Confirm Square-Off' : 'Confirm Reset'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
