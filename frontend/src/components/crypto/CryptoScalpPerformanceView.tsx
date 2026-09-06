'use client';

import React from 'react';
import {
  TrendingUp,
  TrendingDown,
  Percent,
  Activity,
  AlertTriangle,
  Clock,
  DollarSign,
  ShieldCheck,
  Zap,
} from 'lucide-react';
import { CryptoScalpPerformanceMetrics } from '@/lib/types';

interface CryptoScalpPerformanceViewProps {
  metrics: CryptoScalpPerformanceMetrics | null;
  loading?: boolean;
}

export function CryptoScalpPerformanceView({
  metrics,
  loading = false,
}: CryptoScalpPerformanceViewProps) {
  if (loading && !metrics) {
    return (
      <div className="flex items-center justify-center p-12 bg-slate-900/40 rounded-xl border border-slate-800">
        <div className="flex items-center gap-3 text-slate-400">
          <Activity className="w-5 h-5 animate-spin text-cyan-400" />
          <span className="text-sm">Calculating empirical track record analytics...</span>
        </div>
      </div>
    );
  }

  if (!metrics) {
    return null;
  }

  const isProfitable = metrics.net_pnl_usd >= 0;
  const isExpPositive = metrics.expectancy_r >= 0;

  return (
    <div className="space-y-6">
      {/* 1. Statistical Sample Gate Banner */}
      {metrics.insufficient_sample && (
        <div className="bg-amber-500/10 border border-amber-500/20 rounded-xl p-4 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
          <div className="space-y-1 text-sm">
            <div className="font-semibold text-amber-300 flex items-center gap-2">
              <span>Statistical Sample Gate Active</span>
              <span className="text-xs px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-200 border border-amber-500/30">
                Sample Size N = {metrics.completed_trades} / 10
              </span>
            </div>
            <p className="text-slate-300 text-xs leading-relaxed">
              Institutional quantitative validity requires a minimum of 10 closed paper trades to achieve statistical significance.
              Metrics (Win Rate %, Profit Factor, Expectancy R) will dynamically calibrate as the 24/7 background worker executes ticks.
            </p>
          </div>
        </div>
      )}

      {/* 2. Top-Level Quantitative KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {/* Win Rate */}
        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-4 space-y-1">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Win Rate</span>
            <Percent className="w-3.5 h-3.5 text-cyan-400" />
          </div>
          <div className="text-xl font-bold text-slate-100">
            {metrics.win_rate_pct.toFixed(1)}%
          </div>
          <div className="text-[11px] text-slate-400">
            <span className="text-emerald-400 font-medium">{metrics.winning_trades}W</span>
            {' / '}
            <span className="text-rose-400 font-medium">{metrics.losing_trades}L</span>
            {' / '}
            <span className="text-slate-400">{metrics.breakeven_trades}BE</span>
          </div>
        </div>

        {/* Profit Factor */}
        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-4 space-y-1">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Profit Factor</span>
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
          </div>
          <div className="text-xl font-bold text-slate-100">
            {metrics.profit_factor >= 999 ? 'MAX' : metrics.profit_factor.toFixed(2)}
          </div>
          <div className="text-[11px] text-slate-400 truncate">
            ${metrics.gross_profit_usd.toFixed(0)} / ${metrics.gross_loss_usd.toFixed(0)}
          </div>
        </div>

        {/* Expectancy R */}
        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-4 space-y-1">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Expectancy R</span>
            {isExpPositive ? (
              <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
            ) : (
              <TrendingDown className="w-3.5 h-3.5 text-rose-400" />
            )}
          </div>
          <div className={`text-xl font-bold ${isExpPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
            {metrics.expectancy_r > 0 ? `+${metrics.expectancy_r.toFixed(2)}R` : `${metrics.expectancy_r.toFixed(2)}R`}
          </div>
          <div className="text-[11px] text-slate-400">
            Win: +{metrics.average_win_r.toFixed(2)}R | Loss: {metrics.average_loss_r.toFixed(2)}R
          </div>
        </div>

        {/* Net Realized PnL */}
        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-4 space-y-1">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Net Paper P&L</span>
            <DollarSign className="w-3.5 h-3.5 text-cyan-400" />
          </div>
          <div className={`text-xl font-bold ${isProfitable ? 'text-emerald-400' : 'text-rose-400'}`}>
            {metrics.net_pnl_usd >= 0 ? `+$${metrics.net_pnl_usd.toFixed(2)}` : `-$${Math.abs(metrics.net_pnl_usd).toFixed(2)}`}
          </div>
          <div className="text-[11px] text-slate-400">
            $100 risk per trade
          </div>
        </div>

        {/* Execution Friction */}
        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-4 space-y-1">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Execution Drag</span>
            <Zap className="w-3.5 h-3.5 text-amber-400" />
          </div>
          <div className="text-xl font-bold text-amber-300">
            ${metrics.total_execution_drag_usd.toFixed(2)}
          </div>
          <div className="text-[11px] text-slate-400">
            Fees: ${metrics.total_fees_usd.toFixed(1)} | Slip: ${metrics.total_slippage_usd.toFixed(1)}
          </div>
        </div>

        {/* Average Hold Duration */}
        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-4 space-y-1">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Avg Hold Time</span>
            <Clock className="w-3.5 h-3.5 text-indigo-400" />
          </div>
          <div className="text-xl font-bold text-slate-100">
            {metrics.average_duration_str || '0s'}
          </div>
          <div className="text-[11px] text-slate-400">
            Active: {metrics.active_positions} / Total: {metrics.total_signals}
          </div>
        </div>
      </div>

      {/* 3. Strategy Attribution Breakdown Table */}
      <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-cyan-400" />
            <span>Strategy Win Rate & Expectancy Attribution (5 Strategies)</span>
          </h3>
          <span className="text-xs text-slate-400">Deterministic FSM with T1 Partial Exits & BE Ratchets</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400">
                <th className="py-2.5 px-3 font-medium">Strategy</th>
                <th className="py-2.5 px-3 font-medium text-center">Trades</th>
                <th className="py-2.5 px-3 font-medium text-center">W / L / BE</th>
                <th className="py-2.5 px-3 font-medium text-right">Win Rate</th>
                <th className="py-2.5 px-3 font-medium text-right">Profit Factor</th>
                <th className="py-2.5 px-3 font-medium text-right">Expectancy R</th>
                <th className="py-2.5 px-3 font-medium text-right">Net P&L</th>
                <th className="py-2.5 px-3 font-medium text-center">Sample Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {Object.values(metrics.strategy_breakdown || {}).map((strat) => {
                const isStratExpPos = strat.expectancy_r >= 0;
                const isStratPnlPos = strat.net_pnl_usd >= 0;

                return (
                  <tr key={strat.strategy} className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-2.5 px-3">
                      <div className="font-medium text-slate-200">{strat.strategy_name}</div>
                      <div className="text-[10px] text-slate-500 font-mono">{strat.strategy}</div>
                    </td>
                    <td className="py-2.5 px-3 text-center text-slate-300">
                      {strat.completed_trades}
                    </td>
                    <td className="py-2.5 px-3 text-center text-slate-400">
                      <span className="text-emerald-400 font-medium">{strat.winning_trades}</span>
                      {' / '}
                      <span className="text-rose-400 font-medium">{strat.losing_trades}</span>
                      {' / '}
                      <span>{strat.breakeven_trades}</span>
                    </td>
                    <td className="py-2.5 px-3 text-right font-semibold text-slate-200">
                      {strat.completed_trades > 0 ? `${strat.win_rate_pct.toFixed(1)}%` : '—'}
                    </td>
                    <td className="py-2.5 px-3 text-right font-medium text-slate-300">
                      {strat.completed_trades > 0
                        ? strat.profit_factor >= 999
                          ? 'MAX'
                          : strat.profit_factor.toFixed(2)
                        : '—'}
                    </td>
                    <td className={`py-2.5 px-3 text-right font-semibold ${isStratExpPos ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {strat.completed_trades > 0
                        ? strat.expectancy_r > 0
                          ? `+${strat.expectancy_r.toFixed(2)}R`
                          : `${strat.expectancy_r.toFixed(2)}R`
                        : '—'}
                    </td>
                    <td className={`py-2.5 px-3 text-right font-semibold ${isStratPnlPos ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {strat.completed_trades > 0
                        ? strat.net_pnl_usd >= 0
                          ? `+$${strat.net_pnl_usd.toFixed(2)}`
                          : `-$${Math.abs(strat.net_pnl_usd).toFixed(2)}`
                        : '$0.00'}
                    </td>
                    <td className="py-2.5 px-3 text-center">
                      {strat.insufficient_sample ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] bg-amber-500/10 text-amber-300 border border-amber-500/20">
                          <Clock className="w-2.5 h-2.5" />
                          <span>N={strat.completed_trades}/10</span>
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
                          <ShieldCheck className="w-2.5 h-2.5" />
                          <span>Reliable</span>
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* 4. Asset Split (BTC vs ETH) */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {Object.entries(metrics.asset_breakdown || {}).map(([assetKey, assetStat]) => (
          <div key={assetKey} className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-4 space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className={`w-2.5 h-2.5 rounded-full ${assetKey === 'BTC' ? 'bg-amber-400' : 'bg-cyan-400'}`} />
                <span className="font-semibold text-slate-200">{assetStat.symbol} ({assetStat.asset})</span>
              </div>
              <span className="text-xs text-slate-400">{assetStat.total_trades} completed trades</span>
            </div>

            <div className="grid grid-cols-3 gap-2 pt-2 text-xs border-t border-slate-800/60">
              <div>
                <span className="text-slate-500 text-[11px] block">Win Rate</span>
                <span className="font-bold text-slate-200">{assetStat.win_rate_pct.toFixed(1)}%</span>
              </div>
              <div>
                <span className="text-slate-500 text-[11px] block">Profit Factor</span>
                <span className="font-bold text-slate-200">
                  {assetStat.profit_factor >= 999 ? 'MAX' : assetStat.profit_factor.toFixed(2)}
                </span>
              </div>
              <div>
                <span className="text-slate-500 text-[11px] block">Net Realized PnL</span>
                <span className={`font-bold ${assetStat.net_pnl_usd >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {assetStat.net_pnl_usd >= 0 ? `+$${assetStat.net_pnl_usd.toFixed(2)}` : `-$${Math.abs(assetStat.net_pnl_usd).toFixed(2)}`}
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
