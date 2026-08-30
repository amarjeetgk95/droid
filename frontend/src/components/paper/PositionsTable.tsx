'use client';

import { VirtualPosition } from '@/lib/types';
import { Layers, XCircle, TrendingUp, TrendingDown } from 'lucide-react';

export function PositionsTable({
  positions,
  onSquareOff,
}: {
  positions: VirtualPosition[];
  onSquareOff: (positionId: string) => void;
}) {
  const openPositions = positions.filter((p) => p.is_open);
  const closedPositions = positions.filter((p) => !p.is_open);

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-4 shadow-xs">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-primary" />
          <h3 className="font-bold text-sm text-foreground">
            Active Positions ({openPositions.length})
          </h3>
        </div>
      </div>

      {openPositions.length === 0 ? (
        <div className="p-8 text-center bg-secondary/30 rounded-lg border border-border text-muted-foreground text-xs">
          No open positions. Place an order or execute a strategy basket to begin paper trading.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left border-collapse">
            <thead>
              <tr className="border-b border-border text-muted-foreground font-semibold">
                <th className="py-2 px-2">Instrument</th>
                <th className="py-2 px-2">Side</th>
                <th className="py-2 px-2">Product</th>
                <th className="py-2 px-2 text-right">Qty</th>
                <th className="py-2 px-2 text-right">Avg (₹)</th>
                <th className="py-2 px-2 text-right">LTP (₹)</th>
                <th className="py-2 px-2 text-right">MTM P&L (₹)</th>
                <th className="py-2 px-2 text-right">Margin (₹)</th>
                <th className="py-2 px-2 text-center">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40 font-mono">
              {openPositions.map((pos) => {
                const isPos = pos.unrealized_pnl >= 0;
                return (
                  <tr key={pos.position_id} className="hover:bg-accent/30 transition-colors">
                    <td className="py-2.5 px-2 font-sans font-bold text-foreground">
                      {pos.symbol}
                    </td>
                    <td className="py-2.5 px-2">
                      <span className={`text-[10px] px-2 py-0.5 rounded font-bold ${
                        pos.side === 'BUY'
                          ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                          : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                      }`}>
                        {pos.side}
                      </span>
                    </td>
                    <td className="py-2.5 px-2 text-muted-foreground text-[11px] font-sans">
                      {pos.product}
                    </td>
                    <td className="py-2.5 px-2 text-right font-bold text-foreground">
                      {pos.quantity}
                    </td>
                    <td className="py-2.5 px-2 text-right text-foreground">
                      ₹{pos.average_price}
                    </td>
                    <td className="py-2.5 px-2 text-right text-foreground font-bold">
                      ₹{pos.ltp}
                    </td>
                    <td className={`py-2.5 px-2 text-right font-black flex items-center justify-end gap-1 ${
                      isPos ? 'text-emerald-400' : 'text-rose-400'
                    }`}>
                      {isPos ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                      {isPos ? '+' : ''}₹{pos.unrealized_pnl.toLocaleString('en-IN')}
                    </td>
                    <td className="py-2.5 px-2 text-right text-muted-foreground text-[11px]">
                      ₹{pos.used_margin.toLocaleString('en-IN')}
                    </td>
                    <td className="py-2.5 px-2 text-center">
                      <button
                        onClick={() => onSquareOff(pos.position_id)}
                        className="px-2 py-1 bg-destructive/10 hover:bg-destructive text-destructive hover:text-destructive-foreground border border-destructive/30 rounded text-[10px] font-bold transition-all cursor-pointer flex items-center gap-1 mx-auto"
                      >
                        <XCircle className="w-3 h-3" />
                        <span>Exit</span>
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Closed Positions Section */}
      {closedPositions.length > 0 && (
        <div className="pt-2 space-y-2">
          <h4 className="text-xs font-semibold text-muted-foreground">
            Closed Positions ({closedPositions.length})
          </h4>
          <div className="divide-y divide-border/30 font-mono text-[11px]">
            {closedPositions.map((pos) => (
              <div key={pos.position_id} className="py-1.5 flex items-center justify-between">
                <span className="text-foreground font-sans font-medium">{pos.symbol} ({pos.side})</span>
                <span className={`font-bold ${pos.realized_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                  Realized: {pos.realized_pnl >= 0 ? '+' : ''}₹{pos.realized_pnl.toLocaleString('en-IN')}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
