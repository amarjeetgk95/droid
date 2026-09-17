'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { usePolling } from '@/hooks/usePolling';
import { useAsyncAction } from '@/hooks/useAsyncAction';
import { api } from '@/lib/api';
import { errorMessage } from '@/lib/errors';
import type { AlgoOrder } from '@/lib/api/algo';
import type { BadgeVariant } from '../shared/Badge';
import { ageLabel } from '@/lib/feedState';
import { Card } from '../shared/Card';
import { Badge } from '../shared/Badge';
import { ConfirmDialog } from '../shared/ConfirmDialog';

const CANCELLABLE_STATUSES = new Set(['PENDING', 'OPEN', 'PARTIALLY_FILLED', 'PARTIAL', 'TRIGGER_PENDING']);

const statusVariants: Record<string, BadgeVariant> = {
  FILLED: 'success',
  PENDING: 'warning',
  OPEN: 'warning',
  PARTIALLY_FILLED: 'warning',
  PARTIAL: 'warning',
  TRIGGER_PENDING: 'warning',
  CANCELLED: 'neutral',
  CANCELED: 'neutral',
  REJECTED: 'danger',
};

const priceLabel = (order: AlgoOrder): string => {
  const price = typeof order.price === 'number' && Number.isFinite(order.price) ? order.price : null;
  return price === null ? '—' : `₹${price.toLocaleString('en-IN')}`;
};

export const OrderBook: React.FC = () => {
  const [orders, setOrders] = useState<AlgoOrder[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);
  const [announcement, setAnnouncement] = useState('');
  const [cancelTarget, setCancelTarget] = useState<AlgoOrder | null>(null);
  const [cancellingId, setCancellingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  const action = useAsyncAction({
    errorFallback: 'Unknown order error',
    busyMessage: 'A cancellation is already in progress. Wait for it to finish.',
  });
  const previousStatusesRef = useRef<Map<string, string>>(new Map());

  const refresh = useCallback(async () => {
    try {
      const res = await api.getAlgoOrders();
      if (!Array.isArray(res?.data)) {
        throw new Error('Backend returned an invalid order-book payload.');
      }
      setOrders(res.data);
      setLoaded(true);
      setLastUpdated(Date.now());
      setLoadError(null);
    } catch (err) {
      setLoadError(errorMessage(err, 'Unknown order error'));
    }
  }, []);

  usePolling(refresh, 4000);

  useEffect(() => {
    if (!loaded) return;
    const next = new Map<string, string>();
    const changes: string[] = [];
    orders.forEach((order) => {
      const status = order.status ?? 'UNKNOWN';
      next.set(order.client_order_id, status);
      const previous = previousStatusesRef.current.get(order.client_order_id);
      if (previous !== undefined && previous !== status) {
        changes.push(`${order.client_order_id} is now ${status}`);
      }
    });
    previousStatusesRef.current = next;
    if (changes.length > 0) setAnnouncement(changes.join('; '));
  }, [orders, loaded]);

  const handleCancelConfirm = async () => {
    const target = cancelTarget;
    if (!target) return;
    setActionError(null);
    setActionNotice(null);
    setCancellingId(target.client_order_id);

    const outcome = await action.run(async () => {
      const res = await api.cancelAlgoOrder(target.client_order_id);
      const data = res?.data as { cancelled?: boolean } | undefined;
      if (data?.cancelled !== true) {
        throw new Error(
          `Broker did not confirm cancellation of ${target.client_order_id} (cancelled: ${String(
            data?.cancelled,
          )}). The order may still be live.`,
        );
      }
      return true;
    });

    setCancellingId(null);
    if (!outcome.ok) {
      setActionError(outcome.message);
      throw new Error(outcome.message);
    }

    await refresh();
    setActionNotice(`Cancellation confirmed for ${target.client_order_id}.`);
  };

  const lastAge = lastUpdated === null ? null : ageLabel(lastUpdated);

  return (
    <Card
      title={`ORDER BOOK (${orders.length})`}
      subtitle="Complete lifecycle order registry with broker acknowledgement"
    >
      <div aria-live="polite" className="sr-only">
        {announcement}
      </div>

      {(loadError || actionError || actionNotice) && (
        <div className="mb-2 space-y-1.5 font-mono text-[11px]">
          {actionError && (
            <div
              role="alert"
              className="rounded border border-down-line bg-down-wash px-2.5 py-1.5 text-down-strong"
            >
              {actionError}
            </div>
          )}
          {actionNotice && (
            <div
              role="status"
              className="rounded border border-up-line bg-up-wash px-2.5 py-1.5 text-up-strong"
            >
              {actionNotice}
            </div>
          )}
          {loadError && (
            <div className="rounded border border-warn-line bg-warn-wash px-2.5 py-1.5 text-warn-strong">
              Order book refresh failed
              {lastAge ? ` — showing last known rows (${lastAge})` : ''}: {loadError}
            </div>
          )}
        </div>
      )}

      <div className="overflow-x-auto w-full font-mono text-xs">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-border bg-surface-subtle text-ink-3 text-[10px] uppercase">
              <th className="py-2.5 px-3">Order ID</th>
              <th className="py-2.5 px-3">Contract</th>
              <th className="py-2.5 px-3">Side</th>
              <th className="py-2.5 px-3">Type</th>
              <th className="py-2.5 px-3">Qty</th>
              <th className="py-2.5 px-3">Price</th>
              <th className="py-2.5 px-3">Status</th>
              <th className="py-2.5 px-3 text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle">
            {!loaded ? (
              <tr>
                <td colSpan={8} className="py-8 text-center text-ink-3">
                  Loading order book…
                </td>
              </tr>
            ) : orders.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-8 text-center text-ink-3">
                  {loadError ? 'Order book unavailable.' : 'No orders in the book.'}
                </td>
              </tr>
            ) : (
              orders.map((ord) => {
                const status = ord.status ?? 'UNKNOWN';
                const cancellable = CANCELLABLE_STATUSES.has(status);

                return (
                  <tr key={ord.client_order_id} className="hover:bg-muted transition-colors">
                    <td className="py-2 px-3 text-ink-2 font-semibold">{ord.client_order_id}</td>
                    <td className="py-2 px-3 font-bold text-ink">{ord.symbol}</td>
                    <td className="py-2 px-3">
                      <Badge variant={ord.side === 'BUY' ? 'bull' : 'bear'} size="xs">
                        {ord.side}
                      </Badge>
                    </td>
                    <td className="py-2 px-3 text-ink-2">{ord.order_type || '—'}</td>
                    <td className="py-2 px-3 text-ink-2">
                      {ord.filled_quantity ?? 0}/{ord.quantity}
                    </td>
                    <td className="py-2 px-3 text-ink font-semibold">{priceLabel(ord)}</td>
                    <td className="py-2 px-3">
                      <Badge variant={statusVariants[status] ?? 'neutral'} size="xs" dot={true}>
                        {status}
                      </Badge>
                    </td>
                    <td className="py-2 px-3 text-right">
                      {cancellable ? (
                        <button
                          type="button"
                          onClick={() => {
                            setActionError(null);
                            setActionNotice(null);
                            setCancelTarget(ord);
                          }}
                          disabled={action.isPending || cancellingId === ord.client_order_id}
                          className="px-2 py-0.5 rounded bg-down-wash hover:opacity-80 border border-down-line text-down-strong text-[10px] font-semibold disabled:opacity-50"
                        >
                          {cancellingId === ord.client_order_id ? 'Cancelling…' : 'Cancel'}
                        </button>
                      ) : (
                        <span className="text-ink-4">—</span>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <ConfirmDialog
        isOpen={cancelTarget !== null}
        onClose={() => setCancelTarget(null)}
        onConfirm={handleCancelConfirm}
        title={cancelTarget ? `CANCEL ORDER — ${cancelTarget.client_order_id}` : 'CANCEL ORDER'}
        message={
          cancelTarget ? (
            <div className="space-y-2 font-mono text-xs">
              <p>
                Send a cancel request for this{' '}
                <span className="font-bold text-ink">{cancelTarget.status ?? 'UNKNOWN'}</span> order?
              </p>
              <dl className="rounded border border-border bg-surface-subtle p-2.5 space-y-1">
                <div className="flex justify-between gap-3">
                  <dt className="text-ink-3">Order ID</dt>
                  <dd className="text-ink-2">{cancelTarget.client_order_id}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-ink-3">Instrument</dt>
                  <dd className="font-semibold text-ink">{cancelTarget.symbol}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-ink-3">Side / Qty</dt>
                  <dd className="text-ink-2">
                    {cancelTarget.side} · {cancelTarget.filled_quantity ?? 0}/{cancelTarget.quantity} filled
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-ink-3">Limit price</dt>
                  <dd className="text-ink-2">{priceLabel(cancelTarget)}</dd>
                </div>
              </dl>
              <p className="text-ink-3">
                Cancellation is only reported as successful once the broker acknowledges it.
              </p>
            </div>
          ) : null
        }
        confirmLabel="CONFIRM CANCEL"
        destructive={true}
      />
    </Card>
  );
};
