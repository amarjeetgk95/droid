'use client';

import { useState, Fragment } from 'react';
import { VirtualOrder } from '@/lib/types';
import { ListOrdered, AlertCircle, RotateCcw, ChevronDown } from 'lucide-react';

export function OrderBookTable({
  orders,
  onRetry,
}: {
  orders: VirtualOrder[];
  onRetry?: (order: VirtualOrder) => void;
}) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
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
                <Fragment key={o.order_id}>
                  <tr className="hover:bg-accent/30 transition-colors">
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
                      {o.status === 'REJECTED' && (
                        <button
                          type="button"
                          onClick={() => setExpandedId(expandedId === o.order_id ? null : o.order_id)}
                          className="ml-1 inline-flex items-center gap-0.5 text-[10px] font-sans font-semibold text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                          aria-expanded={expandedId === o.order_id}
                          aria-label={expandedId === o.order_id ? 'Hide rejection reason' : 'Show rejection reason'}
                        >
                          <AlertCircle className="w-3 h-3 text-destructive" />
                          Why?
                          <ChevronDown className={`w-3 h-3 transition-transform ${expandedId === o.order_id ? 'rotate-180' : ''}`} />
                        </button>
                      )}
                    </td>
                  </tr>
                  {o.status === 'REJECTED' && expandedId === o.order_id && (
                    <tr className="bg-destructive/5">
                      <td colSpan={8} className="py-2 px-2">
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 rounded-lg border border-destructive/20 bg-background/60 px-3 py-2 font-sans">
                          <span className="text-[11px] text-destructive font-semibold">
                            {o.rejection_reason || 'Order was rejected by risk checks.'}
                          </span>
                          {onRetry && (
                            <button
                              type="button"
                              onClick={() => onRetry(o)}
                              className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-secondary hover:bg-secondary/80 text-foreground border border-border text-[11px] font-bold transition-all cursor-pointer shrink-0"
                            >
                              <RotateCcw className="w-3 h-3" />
                              Retry with lower qty
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
