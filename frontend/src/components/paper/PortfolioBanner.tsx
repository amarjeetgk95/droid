'use client';

import { PortfolioSummary } from '@/lib/types';
import { Wallet, TrendingUp, TrendingDown, ShieldAlert, RotateCcw, AlertOctagon } from 'lucide-react';

export function PortfolioBanner({
  summary,
  onSquareOffAll,
  onReset,
  loading,
}: {
  summary: PortfolioSummary;
  onSquareOffAll: () => void;
  onReset: () => void;
  loading: boolean;
}) {
  const isPos = summary.total_portfolio_pnl >= 0;
  const isMtmPos = summary.total_unrealized_pnl >= 0;

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-4 shadow-xs">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Wallet className="w-5 h-5 text-primary" />
          <h2 className="text-sm font-bold text-foreground">Virtual Trading Account (Paper Trading)</h2>
        </div>

        {/* Quick Action Controls */}
        <div className="flex items-center gap-2">
          <button
            onClick={onSquareOffAll}
            disabled={loading || summary.open_positions_count === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-destructive hover:bg-destructive/90 text-destructive-foreground rounded-lg text-xs font-bold transition-all cursor-pointer shadow-xs disabled:opacity-40"
          >
            <AlertOctagon className="w-3.5 h-3.5" />
            <span>Square Off All ({summary.open_positions_count})</span>
          </button>

          <button
            onClick={onReset}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-secondary hover:bg-secondary/80 text-foreground rounded-lg text-xs font-bold transition-all cursor-pointer border border-border"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Reset Account</span>
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
          <div className={`text-base font-mono font-black ${isPos ? 'text-emerald-400' : 'text-rose-400'}`}>
            {isPos ? '+' : ''}₹{summary.total_portfolio_pnl.toLocaleString('en-IN')}
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
                className={`h-full transition-all ${
                  summary.margin_utilization_pct > 80 ? 'bg-rose-500' : 'bg-primary'
                }`}
                style={{ width: `${Math.min(100, summary.margin_utilization_pct)}%` }}
              ></div>
            </div>
            <span className="text-[9px] text-muted-foreground font-mono block">
              Used: ₹{summary.used_margin.toLocaleString('en-IN')} ({summary.margin_utilization_pct}%)
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
