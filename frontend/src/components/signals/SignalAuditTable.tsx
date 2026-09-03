'use client';

import React, { useState, useMemo } from 'react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useMarketStream } from '@/hooks/useMarketStream';
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

  // Real-Time Live Mark-to-Market Fields
  current_price?: number;
  unrealized_pnl_inr?: number;
  unrealized_pnl_points?: number;
  unrealized_pnl_pct?: number;
  total_pnl_inr?: number;
  live_duration_seconds?: number;
  live_duration_str?: string;

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
  net_unrealized_pnl_inr?: number;
  total_pnl_inr?: number;
  live_winning_trades?: number;
  live_losing_trades?: number;
  total_active_exposure_inr?: number;
  gross_profit_inr: number;
  gross_loss_inr: number;
  profit_factor: number;
  max_win_inr: number;
  max_loss_inr: number;
  avg_trade_pnl_inr: number;
  avg_holding_time_seconds: number;
  strategy_breakdown: Record<string, any>;
  underlying_breakdown: Record<string, any>;
  realtime_sync_ts?: number;
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

  // WebSocket real-time market stream for sub-second tick MTM updates
  const { latestTicks, streamState } = useMarketStream();

  // Compute live trade values with latest websocket ticks or backend MTM
  const computedTrades = useMemo(() => {
    return trades.map((t) => {
      const isOpen = ['ARMED', 'CONFIRMED', 'EXECUTED'].includes(t.status);
      if (!isOpen) {
        return {
          ...t,
          displayPrice: t.exit_price ?? t.actual_fill_price ?? t.trigger_price,
          displayPnlInr: t.actual_pnl_inr ?? 0,
          displayPoints: t.actual_pnl_points ?? 0,
          displayPct: t.actual_pnl_pct ?? 0,
          isProfit: (t.actual_pnl_inr ?? 0) >= 0,
          liveLtp: t.exit_price,
        };
      }

      // Live trade: lookup current tick
      const tick = latestTicks[t.underlying] || latestTicks[`${t.underlying} 50`] || latestTicks[t.underlying.replace('50', '')];
      const livePrice = tick?.ltp ? Number(tick.ltp) : (t.current_price ?? t.actual_fill_price ?? t.trigger_price);
      const entryPrice = t.actual_fill_price || t.trigger_price;
      const isBullish = (t.direction.includes('CALL') || t.direction === 'BULLISH') && !t.direction.includes('PUT') && !t.direction.includes('BEARISH');
      const ptsDiff = isBullish ? livePrice - entryPrice : entryPrice - livePrice;
      const livePnlInr = t.unrealized_pnl_inr !== undefined && t.unrealized_pnl_inr !== null && !tick
        ? t.unrealized_pnl_inr
        : Math.round(ptsDiff * t.quantity * 100) / 100;
      const margin = t.margin_used || (entryPrice * t.quantity);
      const livePct = margin > 0 ? Math.round((livePnlInr / margin * 100) * 100) / 100 : 0;

      return {
        ...t,
        displayPrice: livePrice,
        displayPnlInr: livePnlInr,
        displayPoints: Math.round(ptsDiff * 100) / 100,
        displayPct: livePct,
        isProfit: livePnlInr >= 0,
        liveLtp: livePrice,
      };
    });
  }, [trades, latestTicks]);

  const filtered = computedTrades.filter((t) => {
    if (filterInstr !== 'ALL' && t.underlying !== filterInstr) return false;
    if (filterStatus === 'WON' && t.status !== 'WON') return false;
    if (filterStatus === 'LOST' && t.status !== 'LOST') return false;
    if (filterStatus === 'OPEN' && !['ARMED', 'CONFIRMED', 'EXECUTED'].includes(t.status)) return false;
    return true;
  });

  // Calculate live aggregate totals
  const openTrades = computedTrades.filter((t) => ['ARMED', 'CONFIRMED', 'EXECUTED'].includes(t.status));
  const liveUnrealizedPnl = summary?.net_unrealized_pnl_inr ?? openTrades.reduce((acc, t) => acc + t.displayPnlInr, 0);
  const netRealizedPnl = summary?.net_realized_pnl_inr ?? 0;
  const totalCombinedPnl = summary?.total_pnl_inr ?? (netRealizedPnl + liveUnrealizedPnl);
  const isUnrealizedProfit = liveUnrealizedPnl >= 0;
  const isTotalProfit = totalCombinedPnl >= 0;
  const isRealizedProfit = netRealizedPnl >= 0;

  const liveWinningCount = summary?.live_winning_trades ?? openTrades.filter((t) => t.displayPnlInr > 0).length;
  const liveLosingCount = summary?.live_losing_trades ?? openTrades.filter((t) => t.displayPnlInr < 0).length;

  return (
    <div className="space-y-4">
      {/* ── 3-TIER LIVE P&L SUMMARY KPI STRIP ── */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        {/* Card 1: LIVE UNREALIZED MTM P&L */}
        <Card className={`relative overflow-hidden ${isUnrealizedProfit ? 'bg-emerald-500/10 border-emerald-500/30' : 'bg-rose-500/10 border-rose-500/30'}`}>
          <CardContent className="p-3">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-semibold flex items-center gap-1.5 text-foreground">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </span>
                Live Unrealized P&L
              </span>
              <Badge variant="outline" className={`text-[9px] px-1.5 py-0 font-mono font-bold ${isUnrealizedProfit ? 'bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 border-emerald-500/30' : 'bg-rose-500/20 text-rose-700 dark:text-rose-300 border-rose-500/30'}`}>
                LIVE MTM
              </Badge>
            </div>
            <div className={`text-xl font-extrabold font-mono mt-1 ${isUnrealizedProfit ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
              {liveUnrealizedPnl >= 0 ? `+₹${liveUnrealizedPnl.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : `-₹${Math.abs(liveUnrealizedPnl).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
            </div>
            <div className="text-[10px] text-muted-foreground mt-0.5 flex items-center justify-between">
              <span>{openTrades.length} Open Positions</span>
              <span className="font-mono">
                <span className="text-emerald-600 font-bold">{liveWinningCount}W</span> / <span className="text-rose-600 font-bold">{liveLosingCount}L</span>
              </span>
            </div>
          </CardContent>
        </Card>

        {/* Card 2: NET REALIZED P&L */}
        <Card className={`${isRealizedProfit ? 'bg-emerald-500/5 border-emerald-500/20' : 'bg-rose-500/5 border-rose-500/20'}`}>
          <CardContent className="p-3">
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-muted-foreground font-medium">Net Realized P&L</span>
              {isRealizedProfit ? <TrendingUp className="w-4 h-4 text-emerald-500" /> : <TrendingDown className="w-4 h-4 text-rose-500" />}
            </div>
            <div className={`text-xl font-bold font-mono mt-1 ${isRealizedProfit ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
              {netRealizedPnl >= 0 ? `+₹${netRealizedPnl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : `-₹${Math.abs(netRealizedPnl).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`}
            </div>
            <div className="text-[10px] text-muted-foreground mt-0.5 truncate">
              Gross: +₹{(summary?.gross_profit_inr || 0).toLocaleString()} / -₹{(summary?.gross_loss_inr || 0).toLocaleString()}
            </div>
          </CardContent>
        </Card>

        {/* Card 3: COMBINED TOTAL PORTFOLIO P&L */}
        <Card className={`border-2 ${isTotalProfit ? 'border-primary/40 bg-primary/5' : 'border-rose-500/30 bg-rose-500/5'}`}>
          <CardContent className="p-3">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold text-foreground flex items-center gap-1">
                <DollarSign className="w-3.5 h-3.5 text-primary" /> Total Net P&L
              </span>
              <Badge variant="secondary" className="text-[9px] px-1 py-0 font-mono">
                COMBINED
              </Badge>
            </div>
            <div className={`text-xl font-extrabold font-mono mt-1 ${isTotalProfit ? 'text-primary' : 'text-rose-600'}`}>
              {totalCombinedPnl >= 0 ? `+₹${totalCombinedPnl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : `-₹${Math.abs(totalCombinedPnl).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`}
            </div>
            <div className="text-[10px] text-muted-foreground mt-0.5">
              Realized + Live Open MTM
            </div>
          </CardContent>
        </Card>

        {/* Card 4: WIN RATE & PROFIT FACTOR */}
        <Card className="bg-secondary/20">
          <CardContent className="p-3">
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-muted-foreground font-medium">Win Rate & Factor</span>
              <Award className="w-4 h-4 text-amber-500/70" />
            </div>
            <div className="text-xl font-bold font-mono mt-1 flex items-center gap-1.5">
              <span className="text-emerald-600">{summary?.win_rate_pct !== undefined ? `${summary.win_rate_pct}%` : '0%'}</span>
              <span className="text-xs text-muted-foreground font-normal">({summary?.profit_factor || 1.0}x)</span>
            </div>
            <div className="text-[10px] text-muted-foreground mt-0.5">
              {summary?.winning_trades || 0}W - {summary?.losing_trades || 0}L ({summary?.closed_trades || 0} closed)
            </div>
          </CardContent>
        </Card>

        {/* Card 5: ACTIVE EXPOSURE & PAPER EXECUTIONS */}
        <Card className="bg-secondary/20">
          <CardContent className="p-3">
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-muted-foreground font-medium">Active Exposure</span>
              <Activity className="w-4 h-4 text-primary/70" />
            </div>
            <div className="text-xl font-bold font-mono mt-1">
              ₹{((summary?.total_active_exposure_inr || 0) / 1000).toFixed(1)}k
            </div>
            <div className="text-[10px] text-muted-foreground mt-0.5 flex items-center justify-between">
              <span>{openTrades.length} Paper Trades</span>
              <span className="font-mono text-primary">{summary?.total_signals_audited || 0} Logged</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ── FILTER & REAL-TIME STATUS BAR ── */}
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

            {(['ALL', 'OPEN', 'WON', 'LOST'] as const).map((st) => (
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

          <div className="flex items-center gap-2">
            <div className="hidden sm:flex items-center gap-1.5 text-[11px] font-mono px-2 py-1 rounded bg-secondary/50 border text-muted-foreground">
              <span className={`h-2 w-2 rounded-full ${streamState === 'CONNECTED' ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500'}`} />
              {streamState === 'CONNECTED' ? 'Live Stream Active' : 'Polling (3s)'}
            </div>

            <Button variant="outline" size="sm" onClick={onRefresh} disabled={loading} className="h-8 text-xs gap-1.5">
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              Sync Ledger
            </Button>
          </div>
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
                <th className="py-2.5 px-3">Trigger / Fill / LTP</th>
                <th className="py-2.5 px-3">Exit / Target Progress</th>
                <th className="py-2.5 px-3">Duration</th>
                <th className="py-2.5 px-3 text-right">Actual & Live P&L</th>
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
                  const isOpen = ['ARMED', 'CONFIRMED', 'EXECUTED'].includes(t.status);
                  const isWin = t.isProfit;
                  const pnlInr = t.displayPnlInr;

                  return (
                    <tr
                      key={t.audit_id}
                      onClick={() => onSelectSignal?.(t.signal_id)}
                      className={`hover:bg-muted/30 transition-colors cursor-pointer group ${isOpen ? 'bg-primary/5' : ''}`}
                    >
                      {/* Time & Signal */}
                      <td className="py-2.5 px-3 font-mono">
                        <div className="font-semibold text-foreground flex items-center gap-1">
                          {isOpen && <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-ping shrink-0" />}
                          {new Date(t.created_at_utc).toLocaleTimeString('en-IN', { hour12: false })}
                        </div>
                        <div className="text-[10px] text-muted-foreground">{t.signal_id.slice(0, 8)}…</div>
                      </td>

                      {/* Instrument & Strategy */}
                      <td className="py-2.5 px-3">
                        <div className="flex items-center gap-1.5">
                          <span className="font-bold text-foreground">{t.underlying}</span>
                          <Badge variant="outline" className="text-[9px] px-1 py-0 h-4">
                            {t.timeframe}
                          </Badge>
                        </div>
                        <div className="text-[10px] font-mono text-muted-foreground mt-0.5">
                          {t.strategy} • <span className={t.direction.includes('CALL') || t.direction === 'BULLISH' ? 'text-emerald-500 font-semibold' : 'text-rose-500 font-semibold'}>{t.direction}</span>
                        </div>
                      </td>

                      {/* Option Contract */}
                      <td className="py-2.5 px-3 font-mono">
                        <div className="text-[11px] font-semibold text-foreground">
                          {t.option_symbol || `${t.underlying} ATM ${t.option_type || 'CE'}`}
                        </div>
                        <div className="text-[10px] text-muted-foreground">
                          {t.lots} Lot ({t.quantity} Qty)
                        </div>
                      </td>

                      {/* Trigger / Fill / LTP */}
                      <td className="py-2.5 px-3 font-mono">
                        <div className="text-foreground">
                          Trig: ₹{t.trigger_price?.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </div>
                        {t.actual_fill_price ? (
                          <div className="text-[10px] text-muted-foreground">
                            Fill: ₹{t.actual_fill_price.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                          </div>
                        ) : null}
                        {isOpen && t.liveLtp && (
                          <div className={`text-[10px] font-bold flex items-center gap-0.5 mt-0.5 ${t.isProfit ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
                            LTP: ₹{t.liveLtp.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                          </div>
                        )}
                      </td>

                      {/* Exit / Target Progress */}
                      <td className="py-2.5 px-3 font-mono">
                        {t.exit_price ? (
                          <div>
                            <div className="font-semibold text-foreground">
                              ₹{t.exit_price.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                            </div>
                            <div className="text-[10px] text-muted-foreground">{t.exit_reason || 'Square-off'}</div>
                          </div>
                        ) : (
                          <div className="space-y-0.5">
                            <div className="text-[11px] text-emerald-600 font-semibold">
                              T1: ₹{t.target_1?.toLocaleString('en-IN', { minimumFractionDigits: 1 })} (1.5R)
                            </div>
                            <div className="text-[10px] text-destructive">
                              SL: ₹{t.stop_loss?.toLocaleString('en-IN', { minimumFractionDigits: 1 })}
                            </div>
                          </div>
                        )}
                      </td>

                      {/* Duration */}
                      <td className="py-2.5 px-3 font-mono text-[11px]">
                        {isOpen ? (
                          <span className="text-emerald-600 font-semibold flex items-center gap-1">
                            <Clock className="w-3 h-3" /> {t.live_duration_str || t.holding_time_str || '1m'} (Live)
                          </span>
                        ) : (
                          <span className="text-muted-foreground">{t.holding_time_str || '—'}</span>
                        )}
                      </td>

                      {/* Actual & Live P&L */}
                      <td className="py-2.5 px-3 text-right font-mono">
                        <div>
                          {isOpen && (
                            <Badge className="bg-primary/10 text-primary border-primary/20 text-[9px] px-1 py-0 mb-0.5">
                              LIVE MTM
                            </Badge>
                          )}
                          <div
                            className={`text-xs font-bold ${
                              isWin ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'
                            }`}
                          >
                            {pnlInr >= 0
                              ? `+₹${pnlInr.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                              : `-₹${Math.abs(pnlInr).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
                          </div>
                          <div className="text-[10px] text-muted-foreground">
                            {t.displayPoints ? `${t.displayPoints > 0 ? '+' : ''}${t.displayPoints} pts` : ''}
                            {t.displayPct ? ` (${t.displayPct > 0 ? '+' : ''}${t.displayPct}%)` : ''}
                          </div>
                        </div>
                      </td>

                      {/* Status */}
                      <td className="py-2.5 px-3 text-center">
                        <Badge
                          className={`text-[10px] font-mono px-2 py-0.5 ${
                            t.status === 'WON'
                              ? 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20'
                              : t.status === 'LOST'
                              ? 'bg-rose-500/10 text-rose-600 border-rose-500/20'
                              : t.status === 'EXECUTED'
                              ? 'bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 border-emerald-500/40 animate-pulse'
                              : t.status === 'CONFIRMED'
                              ? 'bg-amber-500/10 text-amber-600 border-amber-500/20'
                              : 'bg-muted text-muted-foreground'
                          }`}
                        >
                          {t.status === 'EXECUTED' ? 'EXECUTED (LIVE)' : t.status}
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
