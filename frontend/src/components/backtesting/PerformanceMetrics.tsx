'use client';

import { BacktestResult } from '@/lib/types';
import { TrendingUp, TrendingDown, ShieldAlert, Award, Activity } from 'lucide-react';

export function PerformanceMetrics({
  result,
}: {
  result: BacktestResult;
}) {
  const isPositive = result.total_net_pnl >= 0;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {/* Total Net P&L */}
      <div className="bg-card border border-border rounded-xl p-3.5 space-y-1 shadow-xs">
        <span className="text-[11px] text-muted-foreground font-semibold flex items-center justify-between">
          Net Post-Tax P&L
          {isPositive ? <TrendingUp className="w-3.5 h-3.5 text-emerald-400" /> : <TrendingDown className="w-3.5 h-3.5 text-rose-400" />}
        </span>
        <div className={`text-base font-mono font-black ${isPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
          {isPositive ? '+' : ''}₹{result.total_net_pnl.toLocaleString('en-IN')}
        </div>
        <span className="text-[10px] text-muted-foreground font-mono">
          ROI: <strong className={isPositive ? 'text-emerald-400' : 'text-rose-400'}>{isPositive ? '+' : ''}{result.net_roi_percent}%</strong>
        </span>
      </div>

      {/* Sharpe & Sortino */}
      <div className="bg-card border border-border rounded-xl p-3.5 space-y-1 shadow-xs">
        <span className="text-[11px] text-muted-foreground font-semibold flex items-center justify-between">
          Risk-Adjusted Ratios
          <Activity className="w-3.5 h-3.5 text-primary" />
        </span>
        <div className="text-base font-mono font-black text-foreground">
          {result.sharpe_ratio.toFixed(2)} <span className="text-xs text-muted-foreground font-normal">Sharpe</span>
        </div>
        <span className="text-[10px] text-muted-foreground font-mono">
          Sortino: <strong className="text-foreground">{result.sortino_ratio.toFixed(2)}</strong>
        </span>
      </div>

      {/* Max Drawdown */}
      <div className="bg-card border border-border rounded-xl p-3.5 space-y-1 shadow-xs">
        <span className="text-[11px] text-muted-foreground font-semibold flex items-center justify-between">
          Max Drawdown (MDD)
          <ShieldAlert className="w-3.5 h-3.5 text-rose-400" />
        </span>
        <div className="text-base font-mono font-black text-rose-400">
          -{result.max_drawdown_percent}%
        </div>
        <span className="text-[10px] text-muted-foreground font-mono">
          Peak Decline: -₹{result.max_drawdown_amount.toLocaleString('en-IN')}
        </span>
      </div>

      {/* Win Rate & Profit Factor */}
      <div className="bg-card border border-border rounded-xl p-3.5 space-y-1 shadow-xs">
        <span className="text-[11px] text-muted-foreground font-semibold flex items-center justify-between">
          Win Rate & Profit Factor
          <Award className="w-3.5 h-3.5 text-warning" />
        </span>
        <div className="text-base font-mono font-black text-foreground">
          {result.win_rate_percent}% <span className="text-xs text-muted-foreground font-normal">({result.winning_trades}W / {result.losing_trades}L)</span>
        </div>
        <span className="text-[10px] text-muted-foreground font-mono">
          Profit Factor: <strong className="text-foreground">{result.profit_factor}</strong>
        </span>
      </div>
    </div>
  );
}
