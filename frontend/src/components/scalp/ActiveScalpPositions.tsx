'use client';

import { useState, useEffect, useCallback } from 'react';
import { ShieldAlert, RefreshCw, XCircle, AlertOctagon } from 'lucide-react';
import { api } from '@/lib/api';
import { VirtualPosition } from '@/lib/types';
import { useToast } from '@/components/ui/toast';

interface ActiveScalpPositionsProps {
  onPositionsUpdated?: () => void;
  refreshTrigger?: number;
}

export function ActiveScalpPositions({
  onPositionsUpdated,
  refreshTrigger,
}: ActiveScalpPositionsProps) {
  const toast = useToast();
  const [positions, setPositions] = useState<VirtualPosition[]>([]);
  const [loading, setLoading] = useState(false);
  const [exitingId, setExitingId] = useState<string | null>(null);
  const [panicExiting, setPanicExiting] = useState(false);

  const fetchPositions = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.getPaperPositions();
      const raw = (res.data || []) as VirtualPosition[];
      const open = raw.filter((p) => p.is_open);
      setPositions(open);
    } catch {
      // ignore poll error
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPositions();
    const interval = setInterval(fetchPositions, 2500); // 2.5s fast position poll
    return () => clearInterval(interval);
  }, [fetchPositions, refreshTrigger]);

  const handleSquareOffSingle = async (pos: VirtualPosition) => {
    try {
      setExitingId(pos.position_id);
      await api.squareOffPosition(pos.position_id);
      toast.success(`Position squared off: ${pos.symbol}`);
      await fetchPositions();
      onPositionsUpdated?.();
    } catch (err: unknown) {
      toast.error(`Square off failed: ${(err as Error)?.message || 'Unknown error'}`);
    } finally {
      setExitingId(null);
    }
  };

  const handlePanicSquareOffAll = async () => {
    if (positions.length === 0) {
      toast.info('No open positions to square off');
      return;
    }
    try {
      setPanicExiting(true);
      await api.squareOffAllPositions();
      toast.success('🚨 EMERGENCY SQUARE-OFF COMPLETE: All active positions closed at market');
      await fetchPositions();
      onPositionsUpdated?.();
    } catch (err: unknown) {
      toast.error(`Emergency exit failed: ${(err as Error)?.message || 'Unknown error'}`);
    } finally {
      setPanicExiting(false);
    }
  };

  // Keyboard shortcut listener: Shift + Escape to trigger panic square-off
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.shiftKey && e.key === 'Escape') {
        e.preventDefault();
        handlePanicSquareOffAll();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [positions]);

  const totalUnrealized = positions.reduce((acc, p) => acc + (p.unrealized_pnl || 0), 0);

  return (
    <div className="flex flex-col bg-card border border-border rounded-lg p-3 text-xs select-none gap-2">
      {/* Header with Panic Exit Button */}
      <div className="flex items-center justify-between border-b border-border/60 pb-2">
        <div className="flex items-center gap-2">
          <span className="font-bold text-foreground flex items-center gap-1.5">
            <ShieldAlert className="w-4 h-4 text-amber-500" />
            Active Scalp Positions ({positions.length})
          </span>
          <span
            className={`font-mono font-bold px-2 py-0.5 rounded text-xs ${
              totalUnrealized > 0
                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                : totalUnrealized < 0
                  ? 'bg-rose-500/10 text-rose-400 border border-rose-500/30'
                  : 'bg-secondary text-muted-foreground'
            }`}
          >
            Live MTM: {totalUnrealized >= 0 ? '+' : ''}₹{totalUnrealized.toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={fetchPositions}
            disabled={loading}
            className="p-1 hover:bg-secondary rounded text-muted-foreground hover:text-foreground transition-colors"
            title="Refresh positions"
          >
            <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
          </button>

          {/* Prominent Emergency Square-Off All Button */}
          <button
            type="button"
            disabled={panicExiting || positions.length === 0}
            onClick={handlePanicSquareOffAll}
            className="flex items-center gap-1.5 px-3 py-1 rounded bg-rose-600 hover:bg-rose-500 active:scale-95 text-white font-bold text-[11px] shadow-sm shadow-rose-950/30 transition-all disabled:opacity-40 cursor-pointer"
            title="Emergency exit all open positions (Shortcut: Shift + Esc)"
          >
            <AlertOctagon className="w-3.5 h-3.5" />
            <span>PANIC SQUARE OFF ALL</span>
            <kbd className="hidden sm:inline-block font-mono text-[9px] bg-rose-800 px-1 rounded opacity-80">
              Shift+Esc
            </kbd>
          </button>
        </div>
      </div>

      {/* Positions Table */}
      {positions.length === 0 ? (
        <div className="flex items-center justify-center h-16 text-center text-muted-foreground text-[11px] border border-dashed border-border/60 rounded">
          No open scalp positions · Ready for execution
        </div>
      ) : (
        <div className="overflow-x-auto">
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
              {positions.map((pos) => {
                const pnl = pos.unrealized_pnl || 0;
                const pnlPct = pos.average_price > 0 ? (pnl / (pos.average_price * pos.quantity)) * 100 : 0;
                const isProfit = pnl >= 0;

                return (
                  <tr
                    key={pos.position_id}
                    className="border-b border-border/30 hover:bg-secondary/20 transition-colors"
                  >
                    <td className="py-1.5 px-2 font-bold text-foreground">
                      {pos.symbol}
                    </td>
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
                    <td className="py-1.5 px-2 text-foreground font-semibold">
                      {pos.quantity}
                    </td>
                    <td className="py-1.5 px-2 text-muted-foreground">
                      ₹{pos.average_price.toFixed(1)}
                    </td>
                    <td className="py-1.5 px-2 text-foreground font-semibold">
                      ₹{pos.ltp.toFixed(1)}
                    </td>
                    <td className={`py-1.5 px-2 font-bold ${isProfit ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {isProfit ? '+' : ''}₹{pnl.toFixed(1)} ({isProfit ? '+' : ''}{pnlPct.toFixed(1)}%)
                    </td>
                    <td className="py-1.5 px-2 text-right">
                      <button
                        type="button"
                        disabled={exitingId === pos.position_id}
                        onClick={() => handleSquareOffSingle(pos)}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 text-[10px] font-semibold transition-colors cursor-pointer"
                      >
                        <XCircle className="w-2.5 h-2.5" />
                        Exit
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
