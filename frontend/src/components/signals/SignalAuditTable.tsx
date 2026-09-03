'use client';

import React, { useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  Award,
  CheckCircle2,
  Clock,
  DollarSign,
  Filter,
  Layers,
  RefreshCw,
  TrendingDown,
  TrendingUp,
  XCircle,
  Zap,
} from 'lucide-react';

export interface AuditTradeRecord {
  audit_id: string;
  signal_id: string;
  underlying: string;
  strategy: string;
  direction: string;
  timeframe: string;
  option_symbol?: string;
  option_type?: string;
  option_strike?: number;
  lot_size: number;
  lots: number;
  quantity: number;
  spot_price_at_creation: number;
  trigger_price: number;
  stop_loss: number;
  target_1: number;
  target_2: number;
  paper_order_id?: string;
  paper_side?: string;
  actual_fill_price?: number;
  executed_at_utc?: number;
  slippage_points?: number;
  margin_used?: number;
  exit_price?: number;
  exited_at_utc?: number;
  exit_reason?: string;
  holding_time_seconds?: number;
  holding_time_str?: string;
  actual_pnl_inr?: number;
  actual_pnl_points?: number;
  actual_pnl_pct?: number;
  theoretical_pnl_points?: number;
  theoretical_pnl_inr?: number;
  status: 'DETECTED' | 'ARMED' | 'CONFIRMED' | 'EXECUTED' | 'WON' | 'LOST' | 'EXPIRED' | 'CLOSED';
  outcome_label?: string;
  is_winner?: boolean;
  created_at_utc: number;
}

export interface AuditSummary {
  total_signals_audited: number;
  open_trades: number;
  closed_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate_pct: number;
  net_realized_pnl_inr: number;
  gross_profit_inr: number;
  gross_loss_inr: number;
  profit_factor: number;
  max_win_inr: number;
  max_loss_inr: number;
  avg_trade_pnl_inr: number;
  avg_holding_time_seconds: number;
  strategy_breakdown: Record<string, any>;
  underlying_breakdown: Record<string, any>;
}

type Props = {
  trades: AuditTradeRecord[];
  summary: AuditSummary | null;
  loading: boolean;
  onRefresh: () => void;
  onSelectSignal?: (signalId: string) => void;
};

export function SignalAuditTable({ trades, summary, loading, onRefresh, onSelectSignal }: Props) {
  const [filterInstr, setFilterInstr] = useState<string>('ALL');
  const [filterStatus, setFilterStatus] = useState<string>('ALL');

  const filtered = trades.filter((t) => {
    if (filterInstr !== 'ALL' && t.underlying !== filterInstr) return false;
    if (filterStatus === 'WON' && t.status !== 'WON') return false;
    if (filterStatus === 'LOST' && t.status !== 'LOST') return false;
    if (filterStatus === 'OPEN' && !['ARMED', 'CONFIRMED', 'EXECUTED'].includes(t.status)) return false;
    return true;
  });

  const netPnl = summary?.net_realized_pnl_inr ?? 0;
  const isNetProfit = netPnl >= 0;

  return (
    <div className="space-y-4">
      {/* ── SUMMARY KPI STRIP ── */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <Card className={`${isNetProfit ? 'bg-emerald-500/5 border-emerald-500/20' : 'bg-rose-500/5 border-rose-500/20'}`}>
          <CardContent className="p-3">
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-muted-foreground font-medium">Net Realized P&L</span>
              {isNetProfit ? <TrendingUp className="w-4 h-4 text-emerald-500" /> : <TrendingDown className="w-4 h-4 text-rose-500" />}
            </div>
            <div className={`text-xl font-bold font-mono mt-1 ${isNetProfit ? 'text-emerald-600' : 'text-rose-600'}`}>
              {netPnl >= 0 ? `+₹${netPnl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : `-₹${Math.abs(netPnl).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`}
            </div>
            <div className="text-[10px] text-muted-foreground mt-0.5">
              Gross: +₹{summary?.gross_profit_inr?.toLocaleString() || 0} / -₹{summary?.gross_loss_inr?.toLocaleString() || 0}
            </div>
          </CardContent>
        </Card>

        <Card className="bg-secondary/20">
          <CardContent className="p-3">
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-muted-foreground font-medium">Win Rate</span>
              <Award className="w-4 h-4 text-primary/70" />
            </div>
            <div className="text-xl font-bold font-mono text-primary mt-1">
              {summary?.win_rate_pct !== undefined ? `${summary.win_rate_pct}%` : '0%'}
            </div>
            <div className="text-[10px] text-muted-foreground mt-0.5">
              {summary?.winning_trades || 0}W - {summary?.losing_trades || 0}L ({summary?.closed_trades || 0} closed)
            </div>
          </CardContent>
        </Card>

        <Card className="bg-secondary/20">
          <CardContent className="p-3">
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-muted-foreground font-medium">Profit Factor</span>
              <Zap className="w-4 h-4 text-amber-500/70" />
            </div>
            <div className="text-xl font-bold font-mono mt-1">
              {summary?.profit_factor !== undefined ? `${summary.profit_factor}x` : '—'}
            </div>
            <div className="text-[10px] text-muted-foreground mt-0.5">
              Avg Trade: ₹{summary?.avg_trade_pnl_inr?.toLocaleString() || 0}
            </div>
          </CardContent>
        </Card>

        <Card className="bg-secondary/20">
          <CardContent className="p-3">
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-muted-foreground font-medium">Paper Executions</span>
              <Activity className="w-4 h-4 text-primary/70" />
            </div>
            <div className="text-xl font-bold font-mono mt-1">
              {summary?.open_trades || 0} Open
            </div>
            <div className="text-[10px] text-muted-foreground mt-0.5">
              {summary?.total_signals_audited || 0} Total Signals Logged
            </div>
          </CardContent>
        </Card>

        <Card className="bg-secondary/20">
          <CardContent className="p-3">
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-muted-foreground font-medium">Avg Holding Time</span>
              <Clock className="w-4 h-4 text-muted-foreground" />
            </div>
            <div className="text-xl font-bold font-mono mt-1">
              {summary?.avg_holding_time_seconds ? `${Math.round(summary.avg_holding_time_seconds / 60)}m` : '—'}
            </div>
            <div className="text-[10px] text-muted-foreground mt-0.5">
              Max Win: ₹{summary?.max_win_inr?.toLocaleString() || 0}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ── FILTER & ACTION BAR ── */}
      <Card className="p-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-semibold text-muted-foreground flex items-center gap-1">
              <Filter className="w-3.5 h-3.5" /> Filter:
            </span>

            {(['ALL', 'NIFTY', 'BANKNIFTY', 'SENSEX'] as const).map((instr) => (
              <button
                key={instr}
                onClick={() => setFilterInstr(instr)}
                className={`px-2.5 py-1 text-xs font-bold rounded-lg border transition-all ${
                  filterInstr === instr
                    ? 'bg-primary text-primary-foreground border-primary'
                    : 'bg-secondary/60 hover:bg-secondary border-transparent'
                }`}
              >
                {instr}
              </button>
            ))}

            <div className="h-4 w-px bg-border mx-1" />

            {(['ALL', 'WON', 'LOST', 'OPEN'] as const).map((st) => (
              <button
                key={st}
                onClick={() => setFilterStatus(st)}
                className={`px-2 py-0.5 text-[11px] font-mono rounded-md border transition-all ${
                  filterStatus === st
                    ? 'bg-primary text-primary-foreground border-primary font-bold'
                    : 'bg-secondary/60 hover:bg-secondary border-transparent'
                }`}
              >
                {st}
              </button>
            ))}
          </div>

          <Button variant="outline" size="sm" onClick={onRefresh} disabled={loading} className="h-8 text-xs gap-1.5">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Sync Ledger
          </Button>
        </div>
      </Card>

      {/* ── AUDIT LEDGER TABLE ── */}
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b bg-muted/40 font-semibold text-muted-foreground">
                <th className="py-2.5 px-3">Time & Signal</th>
                <th className="py-2.5 px-3">Instrument & Strategy</th>
                <th className="py-2.5 px-3">Option Contract</th>
                <th className="py-2.5 px-3">Trigger / Fill Price</th>
                <th className="py-2.5 px-3">Exit Price & Reason</th>
                <th className="py-2.5 px-3">Duration</th>
                <th className="py-2.5 px-3 text-right">Actual Realized P&L</th>
                <th className="py-2.5 px-3 text-center">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-muted-foreground">
                    <p className="text-sm font-medium">No audited signals recorded yet.</p>
                    <p className="text-xs mt-1">Confirmed signals and paper executions will appear here automatically with live P&L.</p>
                  </td>
                </tr>
              ) : (
                filtered.map((t) => {
                  const isWin = t.is_winner === true;
                  const isLoss = t.is_winner === false && (t.actual_pnl_inr ?? 0) < 0;
                  const pnlInr = t.actual_pnl_inr;

                  return (
                    <tr
                      key={t.audit_id}
                      onClick={() => onSelectSignal?.(t.signal_id)}
                      className="hover:bg-muted/30 transition-colors cursor-pointer group"
                    >
                      <td className="py-2.5 px-3 font-mono">
                        <div className="font-semibold text-foreground">
                          {new Date(t.created_at_utc).toLocaleTimeString('en-IN', { hour12: false })}
                        </div>
                        <div className="text-[10px] text-muted-foreground">{t.signal_id.slice(0, 8)}…</div>
                      </td>

                      <td className="py-2.5 px-3">
                        <div className="flex items-center gap-1.5">
                          <span className="font-bold text-foreground">{t.underlying}</span>
                          <Badge variant="outline" className="text-[9px] px-1 py-0 h-4">
                            {t.timeframe}
                          </Badge>
                        </div>
                        <div className="text-[10px] font-mono text-muted-foreground mt-0.5">
                          {t.strategy} • <span className={t.direction.includes('CALL') || t.direction === 'BULLISH' ? 'text-emerald-500' : 'text-rose-500'}>{t.direction}</span>
                        </div>
                      </td>

                      <td className="py-2.5 px-3 font-mono">
                        <div className="text-[11px] font-semibold text-foreground">
                          {t.option_symbol || `${t.underlying} ATM ${t.option_type || 'CE'}`}
                        </div>
                        <div className="text-[10px] text-muted-foreground">
                          {t.lots} Lot ({t.quantity} Qty)
                        </div>
                      </td>

                      <td className="py-2.5 px-3 font-mono">
                        <div className="text-foreground">
                          Trig: ₹{t.trigger_price?.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </div>
                        {t.actual_fill_price ? (
                          <div className="text-[10px] text-emerald-600 dark:text-emerald-400">
                            Fill: ₹{t.actual_fill_price.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                            {t.slippage_points ? ` (${t.slippage_points > 0 ? '+' : ''}${t.slippage_points} pts)` : ''}
                          </div>
                        ) : (
                          <div className="text-[10px] text-muted-foreground">Pending Fill</div>
                        )}
                      </td>

                      <td className="py-2.5 px-3 font-mono">
                        {t.exit_price ? (
                          <div>
                            <div className="font-semibold text-foreground">
                              ₹{t.exit_price.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                            </div>
                            <div className="text-[10px] text-muted-foreground">{t.exit_reason || 'Exit'}</div>
                          </div>
                        ) : (
                          <div className="text-muted-foreground">
                            SL: ₹{t.stop_loss?.toLocaleString('en-IN', { minimumFractionDigits: 1 })} • T1: ₹{t.target_1?.toLocaleString('en-IN', { minimumFractionDigits: 1 })}
                          </div>
                        )}
                      </td>

                      <td className="py-2.5 px-3 font-mono text-muted-foreground text-[11px]">
                        {t.holding_time_str || '—'}
                      </td>

                      <td className="py-2.5 px-3 text-right font-mono">
                        {pnlInr !== undefined && pnlInr !== null ? (
                          <div>
                            <div
                              className={`text-xs font-bold ${
                                isWin ? 'text-emerald-600 dark:text-emerald-400' : isLoss ? 'text-rose-600 dark:text-rose-400' : 'text-muted-foreground'
                              }`}
                            >
                              {pnlInr >= 0 ? `+₹${pnlInr.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : `-₹${Math.abs(pnlInr).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`}
                            </div>
                            <div className="text-[10px] text-muted-foreground">
                              {t.actual_pnl_points ? `${t.actual_pnl_points > 0 ? '+' : ''}${t.actual_pnl_points} pts` : ''}
                              {t.actual_pnl_pct ? ` (${t.actual_pnl_pct > 0 ? '+' : ''}${t.actual_pnl_pct}%)` : ''}
                            </div>
                          </div>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>

                      <td className="py-2.5 px-3 text-center">
                        <Badge
                          className={`text-[10px] font-mono px-2 py-0.5 ${
                            t.status === 'WON'
                              ? 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20'
                              : t.status === 'LOST'
                              ? 'bg-rose-500/10 text-rose-600 border-rose-500/20'
                              : t.status === 'EXECUTED'
                              ? 'bg-blue-500/10 text-blue-600 border-blue-500/20'
                              : t.status === 'CONFIRMED'
                              ? 'bg-amber-500/10 text-amber-600 border-amber-500/20'
                              : 'bg-muted text-muted-foreground'
                          }`}
                        >
                          {t.status}
                        </Badge>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
