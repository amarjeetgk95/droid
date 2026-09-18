'use client';

import React, { useEffect, useState } from 'react';
import { useAsyncAction } from '@/hooks/useAsyncAction';
import { api } from '@/lib/api';
import { toNumber, pickFirst } from '@/lib/coerce';
import type { BadgeVariant } from '@/components/ui/badge';
import { ageLabel } from '@/lib/feedState';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

interface ReconStatus {
  discrepancies: number | null;
  ordersMatched: number | null;
  positionsMatched: number | null;
  engineState: string | null;
  lastReconciled: number;
}

function toTimestamp(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value) {
    const ms = new Date(value).getTime();
    if (Number.isFinite(ms)) return ms;
  }
  return null;
}

function engineVariant(state: string | null): BadgeVariant {
  if (!state) return 'neutral';
  const normalized = state.toUpperCase();
  if (normalized.includes('SYNCHRON') || normalized === 'OK' || normalized === 'HEALTHY') return 'success';
  if (
    normalized.includes('MISMATCH') ||
    normalized.includes('DIVERG') ||
    normalized.includes('STALE') ||
    normalized.includes('FAIL')
  ) {
    return 'danger';
  }
  return 'neutral';
}

export const ReconciliationPanel: React.FC = () => {
  const [status, setStatus] = useState<ReconStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const action = useAsyncAction({
    errorFallback: 'Unknown reconciliation error',
    busyMessage: 'A reconciliation run is already in progress. Wait for it to finish.',
  });

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const handleRunReconciliation = async () => {
    setError(null);

    const outcome = await action.run(async () => {
      const res = await api.runAlgoReconciliation();
      const data = res?.data;
      if (!data) throw new Error('Reconciliation endpoint returned no result.');

      const meta = (res as { meta?: { timestamp?: string } }).meta;
      const lastReconciled =
        toTimestamp(data.last_reconciled) ??
        toTimestamp(data.reconciled_at) ??
        toTimestamp(meta?.timestamp) ??
        Date.now();

      setStatus({
        discrepancies: toNumber(pickFirst(data.discrepancies, data.discrepancy_count)),
        ordersMatched: toNumber(pickFirst(data.matched_orders, data.orders_matched)),
        positionsMatched: toNumber(pickFirst(data.matched_positions, data.positions_matched)),
        engineState:
          typeof data.engine_state === 'string'
            ? data.engine_state
            : typeof data.status === 'string'
              ? data.status
              : null,
        lastReconciled,
      });
      return true;
    });

    if (!outcome.ok) {
      setError(outcome.message);
    }
  };

  const lastAge = status ? ageLabel(status.lastReconciled, now) : null;
  const discrepancies = status?.discrepancies ?? null;

  return (
    <Card
      title="BROKER RECONCILIATION & RECOVERY"
      subtitle="Authoritative matching between local state and broker gateway"
      headerAction={
        <button
          type="button"
          onClick={handleRunReconciliation}
          disabled={action.isPending}
          className="px-2.5 py-1 rounded bg-muted hover:bg-muted-strong border border-border text-primary font-mono text-xs font-semibold disabled:opacity-50"
        >
          {action.isPending ? 'Reconciling…' : 'Run Audit Now'}
        </button>
      }
    >
      <div className="space-y-2 font-mono text-xs">
        {error && (
          <div
            role="alert"
            className="rounded border border-down-line bg-down-wash px-2.5 py-1.5 text-down-strong"
          >
            Reconciliation failed: {error}
            {status && lastAge ? ` Showing last known result (${lastAge}).` : ''}
          </div>
        )}

        {status === null ? (
          <div className="p-2.5 rounded-lg bg-surface-subtle border border-border text-ink-3">
            Reconciliation has not been run in this session — results are UNKNOWN until an audit completes.
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <div className="p-2.5 rounded-lg bg-surface-subtle border border-border">
              <div className="text-[10px] text-ink-3 uppercase">Engine Status</div>
              <Badge variant={engineVariant(status.engineState)} size="xs" dot={true} className="mt-1">
                {status.engineState ?? 'UNKNOWN'}
              </Badge>
            </div>

            <div className="p-2.5 rounded-lg bg-surface-subtle border border-border">
              <div className="text-[10px] text-ink-3 uppercase">Discrepancies</div>
              <div
                className={`text-sm font-bold mt-0.5 ${
                  discrepancies === null
                    ? 'text-ink-3'
                    : discrepancies > 0
                      ? 'text-down-strong'
                      : 'text-up-strong'
                }`}
              >
                {discrepancies ?? '—'}
              </div>
            </div>

            <div className="p-2.5 rounded-lg bg-surface-subtle border border-border">
              <div className="text-[10px] text-ink-3 uppercase">Orders Matched</div>
              <div className="text-sm font-bold text-ink mt-0.5">{status.ordersMatched ?? '—'}</div>
            </div>

            <div className="p-2.5 rounded-lg bg-surface-subtle border border-border">
              <div className="text-[10px] text-ink-3 uppercase">Positions Matched</div>
              <div className="text-sm font-bold text-ink mt-0.5">{status.positionsMatched ?? '—'}</div>
            </div>

            <div className="col-span-2 sm:col-span-4 text-[10px] text-ink-3">
              Last reconciled: {lastAge ?? 'timestamp unavailable'} ·{' '}
              {new Date(status.lastReconciled).toLocaleTimeString('en-IN')}
            </div>
          </div>
        )}
      </div>
    </Card>
  );
};
