'use client';

import { useState } from 'react';
import { Shield, Clock, TrendingUp, XCircle, ArrowUpRight, ArrowDownRight } from 'lucide-react';
import type { SwingPositionDTO } from '@/lib/api/swing';

export type SwingPositionsTableProps = {
  positions: SwingPositionDTO[];
  closedPositions?: SwingPositionDTO[];
  onExitPosition?: (positionId: string, exitPrice: number) => Promise<any>;
};

export function SwingPositionsTable({
  positions,
  closedPositions = [],
  onExitPosition,
}: SwingPositionsTableProps) {
  const [exitingId, setExitingId] = useState<string | null>(null);
  const [viewTab, setViewTab] = useState<'open' | 'closed'>('open');

  const handleExit = async (pos: SwingPositionDTO) => {
    if (!onExitPosition) return;
    setExitingId(pos.position_id);
    try {
      await onExitPosition(pos.position_id, pos.current_price);
    } catch {
      // Handled by parent
    } finally {
      setExitingId(null);
    }
  };

  const getTrailingBadge = (method: string) => {
    switch (method) {
      case 'BREAK_EVEN':
        return <span className="px-2 py-0.5 text-[10px] font-semibold rounded bg-sky-500/10 text-sky-400 border border-sky-500/20">BREAK-EVEN</span>;
      case 'EMA_20':
        return <span className="px-2 py-0.5 text-[10px] font-semibold rounded bg-purple-500/10 text-purple-400 border border-purple-500/20">20 EMA TRAIL</span>;
      case 'THREE_DAY_LOW':
        return <span className="px-2 py-0.5 text-[10px] font-semibold rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">3D LOW TRAIL</span>;
      default:
        return <span className="px-2 py-0.5 text-[10px] font-semibold rounded bg-muted text-muted-foreground border border-border">INITIAL PIVOT</span>;
    }
  };

  return (
    <div className="rounded-xl border border-border bg-card text-card-foreground shadow-sm overflow-hidden">
      {/* Table Sub-header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-border bg-muted/20">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setViewTab('open')}
            className={`px-3 py-1 text-xs font-semibold rounded-lg transition-colors ${
              viewTab === 'open'
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted'
            }`}
          >
            Active Positions ({positions.length})
          </button>
          <button
            onClick={() => setViewTab('closed')}
            className={`px-3 py-1 text-xs font-semibold rounded-lg transition-colors ${
              viewTab === 'closed'
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted'
            }`}
          >
            Closed History ({closedPositions.length})
          </button>
        </div>
        <span className="text-xs text-muted-foreground">
          {viewTab === 'open' ? 'Carried past market close without 15:15 auto-close' : 'Realized swing outcomes'}
        </span>
      </div>

      {/* Table Content */}
      <div className="overflow-x-auto">
        {viewTab === 'open' ? (
          positions.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground text-xs gap-2">
              <Shield className="w-8 h-8 opacity-40 text-muted-foreground" />
              <span>No open swing trades in portfolio.</span>
              <span className="text-[11px] opacity-70">Enter setups from the Setups & Radar tab.</span>
            </div>
          ) : (
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-border/60 bg-muted/40 text-muted-foreground font-medium text-[11px]">
                  <th className="py-2.5 px-4">Instrument</th>
                  <th className="py-2.5 px-3">Days Held</th>
                  <th className="py-2.5 px-3">Qty & Entry</th>
                  <th className="py-2.5 px-3">Current LTP</th>
                  <th className="py-2.5 px-3">Trailing Stop</th>
                  <th className="py-2.5 px-3">Target 1 / 2</th>
                  <th className="py-2.5 px-3 text-right">P&L / Return</th>
                  <th className="py-2.5 px-4 text-center">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40">
                {positions.map((pos) => {
                  const isProfit = pos.unrealized_pnl >= 0;
                  return (
                    <tr key={pos.position_id} className="hover:bg-muted/30 transition-colors">
                      <td className="py-3 px-4 font-semibold text-foreground">
                        <div className="flex items-center gap-1.5">
                          <span>{pos.symbol}</span>
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground font-normal">
                            {pos.sector}
                          </span>
                        </div>
                        <div className="text-[10px] text-muted-foreground font-normal">{pos.strategy.replace(/_/g, ' ')}</div>
                      </td>

                      <td className="py-3 px-3">
                        <div className="flex items-center gap-1 text-foreground font-mono">
                          <Clock className="w-3.5 h-3.5 text-muted-foreground" />
                          <span>Day {pos.days_held}</span>
                        </div>
                      </td>

                      <td className="py-3 px-3">
                        <div className="font-mono text-foreground">{pos.quantity} shares</div>
                        <div className="text-[10px] text-muted-foreground font-mono">@ ₹{pos.entry_price.toFixed(2)}</div>
                      </td>

                      <td className="py-3 px-3 font-mono font-medium text-foreground">
                        ₹{pos.current_price.toFixed(2)}
                      </td>

                      <td className="py-3 px-3">
                        <div className="font-mono font-semibold text-destructive">₹{pos.current_stop.toFixed(2)}</div>
                        <div className="mt-0.5">{getTrailingBadge(pos.trailing_method)}</div>
                      </td>

                      <td className="py-3 px-3 text-[11px] font-mono">
                        <div className="text-emerald-500 font-semibold">T1: ₹{pos.target_1.toFixed(2)}</div>
                        <div className="text-muted-foreground">T2: ₹{pos.target_2.toFixed(2)}</div>
                      </td>

                      <td className="py-3 px-3 text-right">
                        <div className={`font-mono font-bold text-sm ${isProfit ? 'text-emerald-500' : 'text-rose-500'}`}>
                          {isProfit ? '+' : ''}₹{pos.unrealized_pnl.toFixed(2)}
                        </div>
                        <div className={`text-[11px] font-mono flex items-center justify-end gap-0.5 ${isProfit ? 'text-emerald-500' : 'text-rose-500'}`}>
                          {isProfit ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                          <span>{isProfit ? '+' : ''}{pos.pnl_pct.toFixed(2)}% ({pos.r_multiple.toFixed(1)}R)</span>
                        </div>
                      </td>

                      <td className="py-3 px-4 text-center">
                        <button
                          onClick={() => handleExit(pos)}
                          disabled={exitingId === pos.position_id}
                          className="px-2.5 py-1 text-[11px] font-medium rounded-md border border-destructive/40 text-destructive hover:bg-destructive/10 transition-colors disabled:opacity-50"
                        >
                          {exitingId === pos.position_id ? 'Closing...' : 'Close Trade'}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )
        ) : (
          closedPositions.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground text-xs gap-2">
              <Shield className="w-8 h-8 opacity-40 text-muted-foreground" />
              <span>No closed swing trades recorded yet.</span>
            </div>
          ) : (
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-border/60 bg-muted/40 text-muted-foreground font-medium text-[11px]">
                  <th className="py-2.5 px-4">Instrument</th>
                  <th className="py-2.5 px-3">Days Held</th>
                  <th className="py-2.5 px-3">Entry Price</th>
                  <th className="py-2.5 px-3">Exit Price</th>
                  <th className="py-2.5 px-3">Exit Reason</th>
                  <th className="py-2.5 px-4 text-right">Realized P&L</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40">
                {closedPositions.map((pos) => {
                  const isProfit = pos.unrealized_pnl >= 0;
                  return (
                    <tr key={pos.position_id} className="hover:bg-muted/30 transition-colors">
                      <td className="py-3 px-4 font-semibold text-foreground">
                        {pos.symbol}
                        <span className="ml-2 text-[10px] text-muted-foreground font-normal">{pos.sector}</span>
                      </td>
                      <td className="py-3 px-3 font-mono">{pos.days_held} days</td>
                      <td className="py-3 px-3 font-mono">₹{pos.entry_price.toFixed(2)}</td>
                      <td className="py-3 px-3 font-mono">₹{(pos.close_price || pos.current_price).toFixed(2)}</td>
                      <td className="py-3 px-3">
                        <span className="px-2 py-0.5 text-[10px] font-semibold rounded bg-muted text-muted-foreground">
                          {pos.exit_reason || 'MANUAL_EXIT'}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right">
                        <div className={`font-mono font-bold ${isProfit ? 'text-emerald-500' : 'text-rose-500'}`}>
                          {isProfit ? '+' : ''}₹{pos.unrealized_pnl.toFixed(2)}
                        </div>
                        <div className={`text-[10px] font-mono ${isProfit ? 'text-emerald-500' : 'text-rose-500'}`}>
                          {pos.r_multiple.toFixed(1)}R
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )
        )}
      </div>
    </div>
  );
}
