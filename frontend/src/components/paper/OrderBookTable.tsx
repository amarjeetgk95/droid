'use client';

import { VirtualOrder } from '@/lib/types';
import { ListOrdered } from 'lucide-react';

export function OrderBookTable({
  orders,
}: {
  orders: VirtualOrder[];
}) {
  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-3 shadow-xs">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ListOrdered className="w-4 h-4 text-primary" />
          <h3 className="font-bold text-sm text-foreground">
            Virtual Order Book ({orders.length})
          </h3>
        </div>
      </div>

      {orders.length === 0 ? (
        <div className="p-8 text-center bg-secondary/30 rounded-lg border border-border text-muted-foreground text-xs">
          No orders placed yet.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left border-collapse">
            <thead>
              <tr className="border-b border-border text-muted-foreground font-semibold">
                <th className="py-2 px-2">Order ID / Time</th>
                <th className="py-2 px-2">Symbol</th>
                <th className="py-2 px-2">Side</th>
                <th className="py-2 px-2">Product</th>
                <th className="py-2 px-2 text-right">Qty</th>
                <th className="py-2 px-2 text-right">Price</th>
                <th className="py-2 px-2 text-right">Fill Price</th>
                <th className="py-2 px-2 text-center">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40 font-mono">
              {orders.map((o) => (
                <tr key={o.order_id} className="hover:bg-accent/30 transition-colors">
                  <td className="py-2.5 px-2">
                    <span className="text-foreground font-medium block">{o.order_id}</span>
                    <span className="text-[10px] text-muted-foreground">{new Date(o.timestamp).toLocaleTimeString('en-IN')}</span>
                  </td>
                  <td className="py-2.5 px-2 font-sans font-bold text-foreground">
                    {o.symbol}
                  </td>
                  <td className="py-2.5 px-2">
                    <span className={`text-[10px] px-2 py-0.5 rounded font-bold ${
                      o.side === 'BUY'
                        ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                        : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                    }`}>
                      {o.side}
                    </span>
                  </td>
                  <td className="py-2.5 px-2 text-muted-foreground text-[11px] font-sans">
                    {o.product}
                  </td>
                  <td className="py-2.5 px-2 text-right text-foreground font-bold">
                    {o.quantity}
                  </td>
                  <td className="py-2.5 px-2 text-right text-muted-foreground">
                    {o.price > 0 ? `₹${o.price}` : 'MKT'}
                  </td>
                  <td className="py-2.5 px-2 text-right text-foreground font-bold">
                    {o.fill_price ? `₹${o.fill_price}` : '---'}
                  </td>
                  <td className="py-2.5 px-2 text-center">
                    <span className={`text-[10px] px-2 py-0.5 rounded font-bold border ${
                      o.status === 'FILLED'
                        ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                        : o.status === 'REJECTED'
                        ? 'bg-destructive/20 text-destructive border-destructive/30'
                        : 'bg-warning/20 text-warning border-warning/30'
                    }`}>
                      {o.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
