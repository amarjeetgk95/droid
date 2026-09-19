'use client';

import { RefreshCw, X } from 'lucide-react';
import { isOrderCancellable, orderStatusTone, type TradeMode, type TradeOrder } from '@/lib/tradeOps';
import { safeNum, safeTime } from '@/lib/utils';

export function OrdersPanel({
  orders,
  mode,
  loading,
  busyId,
  onCancel,
  onReconcile,
}: {
  orders: TradeOrder[];
  mode: TradeMode;
  loading: boolean;
  busyId: string | null;
  onCancel: (order: TradeOrder) => void;
  onReconcile: (order: TradeOrder) => void;
}) {
  return (
    <section className="panel">
      <header className="card-hd">
        <h3 className="card-title">Open &amp; Recent Orders</h3>
        <span className="card-meta">
          {orders.length} shown · mode {mode}
        </span>
      </header>
      {orders.length === 0 ? (
        <p className="sg-empty">
          {loading
            ? 'Loading orders…'
            : 'No algo orders on record. New working orders appear here as the strategies submit them.'}
        </p>
      ) : (
        <div className="tbl-scroll">
          <table className="sg-table">
            <thead>
              <tr>
                <th>Contract</th>
                <th>Side</th>
                <th className="r">Qty</th>
                <th className="r">Price</th>
                <th className="r">Fill</th>
                <th>Status</th>
                <th className="r">Action</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((order) => {
                const busy = busyId === order.id;
                const cancellable = isOrderCancellable(order.status);
                return (
                  <tr key={order.id}>
                    <td>
                      <div className="sg-sym">{order.symbol}</div>
                      <div className="sg-rownote">
                        {order.orderType ?? '—'} · {safeTime(order.createdMs ? new Date(order.createdMs).toISOString() : null)}
                      </div>
                    </td>
                    <td>
                      <span className={`sg-tag ${order.side === 'SELL' ? 'bear' : order.side === 'BUY' ? 'bull' : 'neut'}`}>
                        {order.side ?? '—'}
                      </span>
                    </td>
                    <td className="r mono">{order.quantity ?? '—'}</td>
                    <td className="r mono">{safeNum(order.price)}</td>
                    <td className="r mono">{safeNum(order.fillPrice)}</td>
                    <td>
                      <span className={`sg-tag ${orderStatusTone(order.status)}`}>{order.status}</span>
                      {order.rejectionReason ? (
                        <div className="sg-rownote">{order.rejectionReason}</div>
                      ) : null}
                    </td>
                    <td>
                      <div className="sg-actions">
                        <button
                          type="button"
                          className="sg-ibtn"
                          title="Reconcile this order with the broker (polls latest state)"
                          disabled={busy}
                          onClick={() => onReconcile(order)}
                        >
                          <RefreshCw size={12} />
                        </button>
                        <button
                          type="button"
                          className="sg-ibtn danger"
                          title={cancellable ? 'Cancel this working order' : `Cannot cancel an order in ${order.status}`}
                          disabled={busy || !cancellable}
                          onClick={() => onCancel(order)}
                        >
                          <X size={12} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
