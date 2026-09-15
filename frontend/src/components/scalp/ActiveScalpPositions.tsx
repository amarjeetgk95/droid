'use client';

import React, { useState } from 'react';
import { ShieldAlert, RefreshCw, XCircle, TrendingUp, TrendingDown } from 'lucide-react';
import { api } from '@/lib/api';
import { VirtualPosition } from '@/lib/types';
import { useToast } from '@/components/ui/toast';
import { useScalpContext } from './ScalpContext';

interface ActiveScalpPositionsProps {
  onSquareOffSingle?: (pos: VirtualPosition) => void;
}

export function ActiveScalpPositions({ onSquareOffSingle }: ActiveScalpPositionsProps) {
  const toast = useToast();
  const { openPositions, refreshPositions, notifyOrderPlaced } = useScalpContext();
  const [exitingId, setExitingId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleManualRefresh = async () => {
    try {
      setLoading(true);
      await refreshPositions();
    } finally {
      setLoading(false);
    }
  };

  const handleSquareOff = async (pos: VirtualPosition) => {
    try {
      setExitingId(pos.position_id);
      await api.squareOffPosition(pos.position_id);
      toast.success(`Position closed: ${pos.symbol}`);
      notifyOrderPlaced();
      onSquareOffSingle?.(pos);
    } catch (err: unknown) {
      toast.error(`Square off failed: ${(err as Error)?.message || 'Unknown error'}`);
    } finally {
      setExitingId(null);
    }
  };

  const totalUnrealized = openPositions.reduce((acc, p) => acc + (p.unrealized_pnl || 0), 0);

  return (
    <div className="flex flex-col text-xs select-none gap-2 h-full">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border/60 pb-1.5 shrink-0">
        <div className="flex items-center gap-2">
          <span className="font-bold text-foreground flex items-center gap-1.5">
            <ShieldAlert className="w-3.5 h-3.5 text-amber-500" />
            Positions ({openPositions.length})
          </span>
          <span
            className={`font-mono font-bold px-2 py-0.5 rounded text-[10px] ${
              totalUnrealized > 0
                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                : totalUnrealized < 0
                  ? 'bg-rose-500/10 text-rose-400 border border-rose-500/30'
                  : 'bg-secondary text-muted-foreground'
            }`}
          >
            Live MTM: {totalUnrealized >= 0 ? '+' : ''}₹
            {totalUnrealized.toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}
          </span>
        </div>

        <button
          type="button"
          onClick={handleManualRefresh}
          disabled={loading}
          className="p-1 hover:bg-secondary rounded text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
          title="Refresh positions"
        >
          <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Content: Empty State vs Cards vs Table */}
      {openPositions.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-5 px-3 text-center text-muted-foreground text-[11px] border border-dashed border-border/50 rounded-lg bg-secondary/10 flex-1 min-h-[100px]">
          <span className="font-semibold text-foreground flex items-center gap-1.5">
            <ShieldAlert className="w-3.5 h-3.5 text-emerald-400" />
            No Active Scalp Positions
          </span>
          <span className="text-[10px] text-muted-foreground mt-0.5">
            Capital safe · Ready for 1-click execution or auto-pilot setups
          </span>
        </div>
      ) : openPositions.length < 3 ? (
        /* Compact Card Grid for 1 or 2 positions */
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 overflow-y-auto">
          {openPositions.map((pos) => {
            const pnl = pos.unrealized_pnl || 0;
            const pnlPct = pos.average_price > 0 ? (pnl / (pos.average_price * pos.quantity)) * 100 : 0;
            const isProfit = pnl >= 0;

            return (
              <div
                key={pos.position_id}
                className="bg-card/70 border border-border/70 rounded-lg p-2.5 flex flex-col justify-between gap-1.5"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <span
                      className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                        pos.side === 'BUY'
                          ? 'bg-emerald-500/20 text-emerald-400'
                          : 'bg-rose-500/20 text-rose-400'
                      }`}
                    >
                      {pos.side}
                    </span>
                    <span className="font-bold text-foreground text-xs">{pos.symbol}</span>
                    <span className="font-mono text-muted-foreground text-[10px]">({pos.quantity}q)</span>
                  </div>

                  <button
                    type="button"
                    disabled={exitingId === pos.position_id}
                    onClick={() => handleSquareOff(pos)}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-rose-500/15 hover:bg-rose-500/25 text-rose-400 border border-rose-500/30 text-[10px] font-semibold transition-colors cursor-pointer"
                  >
                    <XCircle className="w-3 h-3" />
                    {exitingId === pos.position_id ? 'Closing…' : 'Exit'}
                  </button>
                </div>

                <div className="grid grid-cols-3 gap-2 bg-secondary/30 rounded p-1.5 text-[10px] font-mono">
                  <div>
                    <span className="text-muted-foreground block text-[9px]">Entry</span>
                    <span className="text-foreground font-semibold">₹{pos.average_price.toFixed(1)}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground block text-[9px]">LTP</span>
                    <span className="text-foreground font-semibold">₹{pos.ltp.toFixed(1)}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground block text-[9px]">P&L</span>
                    <span
                      className={`font-bold flex items-center gap-0.5 ${
                        isProfit ? 'text-emerald-400' : 'text-rose-400'
                      }`}
                    >
                      {isProfit ? <TrendingUp className="w-2.5 h-2.5" /> : <TrendingDown className="w-2.5 h-2.5" />}
                      {isProfit ? '+' : ''}₹{pnl.toFixed(1)} ({isProfit ? '+' : ''}{pnlPct.toFixed(1)}%)
                    </span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        /* Compact Table for 3+ positions */
        <div className="overflow-x-auto overflow-y-auto">
          <table className="w-full text-[11px] border-collapse font-mono">
            <thead>
              <tr className="border-b border-border/40 text-muted-foreground text-[10px] text-left">
                <th className="py-1 px-2">Instrument</th>
                <th className="py-1 px-2">Side</th>
                <th className="py-1 px-2">Qty</th>
                <th className="py-1 px-2">Avg Entry</th>
                <th className="py-1 px-2">LTP</th>
                <th className="py-1 px-2">Unrealized P&L</th>
                <th className="py-1 px-2 text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {openPositions.map((pos) => {
                const pnl = pos.unrealized_pnl || 0;
                const pnlPct = pos.average_price > 0 ? (pnl / (pos.average_price * pos.quantity)) * 100 : 0;
                const isProfit = pnl >= 0;

                return (
                  <tr
                    key={pos.position_id}
                    className="border-b border-border/30 hover:bg-secondary/20 transition-colors"
                  >
                    <td className="py-1.5 px-2 font-bold text-foreground">{pos.symbol}</td>
                    <td className="py-1.5 px-2">
                      <span
                        className={`px-1 py-0.2 rounded text-[10px] font-bold ${
                          pos.side === 'BUY'
                            ? 'bg-emerald-500/20 text-emerald-400'
                            : 'bg-rose-500/20 text-rose-400'
                        }`}
                      >
                        {pos.side}
                      </span>
                    </td>
                    <td className="py-1.5 px-2 text-foreground font-semibold">{pos.quantity}</td>
                    <td className="py-1.5 px-2 text-muted-foreground">₹{pos.average_price.toFixed(1)}</td>
                    <td className="py-1.5 px-2 text-foreground font-semibold">₹{pos.ltp.toFixed(1)}</td>
                    <td className={`py-1.5 px-2 font-bold ${isProfit ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {isProfit ? '+' : ''}₹{pnl.toFixed(1)} ({isProfit ? '+' : ''}{pnlPct.toFixed(1)}%)
                    </td>
                    <td className="py-1.5 px-2 text-right">
                      <button
                        type="button"
                        disabled={exitingId === pos.position_id}
                        onClick={() => handleSquareOff(pos)}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 text-[10px] font-semibold transition-colors cursor-pointer"
                      >
                        <XCircle className="w-2.5 h-2.5" />
                        {exitingId === pos.position_id ? '…' : 'Exit'}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
