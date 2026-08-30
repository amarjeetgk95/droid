'use client';

import { BacktestTradeModel } from '@/lib/types';
import { ListFilter } from 'lucide-react';

export function TradeLogTable({
  trades,
}: {
  trades: BacktestTradeModel[];
}) {
  if (!trades || trades.length === 0) return null;

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'TARGET_HIT':
        return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40';
      case 'STOP_LOSS_HIT':
        return 'bg-rose-500/20 text-rose-400 border-rose-500/40';
      default:
        return 'bg-primary/20 text-primary border-primary/40';
    }
  };

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-3 shadow-xs">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ListFilter className="w-4 h-4 text-primary" />
          <h3 className="font-bold text-sm text-foreground">Executed Trade Log ({trades.length})</h3>
        </div>
        <span className="text-xs text-muted-foreground">Post-Tax Audit Trail</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs text-left border-collapse">
          <thead>
            <tr className="border-b border-border text-muted-foreground font-semibold">
              <th className="py-2 px-2">ID / Date</th>
              <th className="py-2 px-2">Strategy & Legs</th>
              <th className="py-2 px-2 text-right">Entry (₹)</th>
              <th className="py-2 px-2 text-right">Exit (₹)</th>
              <th className="py-2 px-2 text-right">Qty</th>
              <th className="py-2 px-2 text-right">Gross P&L</th>
              <th className="py-2 px-2 text-right">Taxes & Charges</th>
              <th className="py-2 px-2 text-right">Net P&L (₹)</th>
              <th className="py-2 px-2 text-center">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/40 font-mono">
            {trades.map((t) => {
              const isPos = t.net_pnl >= 0;
              return (
                <tr key={t.trade_id} className="hover:bg-accent/30 transition-colors">
                  <td className="py-2 px-2 font-medium">
                    <span className="text-foreground block">{t.trade_id}</span>
                    <span className="text-[10px] text-muted-foreground">{t.entry_date}</span>
                  </td>
                  <td className="py-2 px-2 font-sans">
                    <span className="font-bold text-foreground block">{t.strategy_name}</span>
                    <span className="text-[10px] text-muted-foreground">{t.legs_description}</span>
                  </td>
                  <td className="py-2 px-2 text-right text-foreground">₹{t.entry_price}</td>
                  <td className="py-2 px-2 text-right text-foreground">₹{t.exit_price}</td>
                  <td className="py-2 px-2 text-right text-muted-foreground">{t.quantity}</td>
                  <td className={`py-2 px-2 text-right font-bold ${t.gross_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {t.gross_pnl >= 0 ? '+' : ''}₹{t.gross_pnl.toLocaleString('en-IN')}
                  </td>
                  <td className="py-2 px-2 text-right text-muted-foreground">
                    -₹{t.total_charges.toLocaleString('en-IN')}
                  </td>
                  <td className={`py-2 px-2 text-right font-black ${isPos ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {isPos ? '+' : ''}₹{t.net_pnl.toLocaleString('en-IN')}
                  </td>
                  <td className="py-2 px-2 text-center">
                    <span className={`text-[9px] px-2 py-0.5 rounded-full font-bold border ${getStatusBadge(t.status)}`}>
                      {t.status.replace(/_/g, ' ')}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
