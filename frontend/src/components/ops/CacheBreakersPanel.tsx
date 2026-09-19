'use client';

/* Cache & breakers tab. Mutations (clear / reset / trip) sit behind
   ConfirmDialog — trip requires typing TRIP — with toast results. */

import { useState } from 'react';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { useToast } from '@/components/ui/toast';
import type { OpsActionResult, OpsConsole } from '@/hooks/useOpsConsole';
import {
  fmtCell,
  summarizeBreaker,
  summarizeCache,
  toneForBreaker,
} from '@/lib/opsDesk';
import { KvList, OpsCard, ToneBadge } from './OpsBits';

export function CacheBreakersPanel({ ops }: { ops: OpsConsole }) {
  const { push } = useToast();
  const [confirmClear, setConfirmClear] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [confirmTrip, setConfirmTrip] = useState(false);

  const cache = summarizeCache(ops.cacheStats);
  const breaker = summarizeBreaker(ops.breaker);

  const finish = (result: OpsActionResult, close: () => void) => {
    push(result.ok ? 'success' : 'error', result.message);
    close();
  };

  return (
    <div className="flex flex-col gap-3">
      {ops.infraErrors.cache ? <p className="sg-err">{ops.infraErrors.cache}</p> : null}
      {ops.infraErrors.breaker ? <p className="sg-err">{ops.infraErrors.breaker}</p> : null}

      <OpsCard
        title="Cache"
        meta={cache.backend ?? 'GET /api/v1/cache/stats'}
        action={
          <button type="button" className="btn" disabled={ops.mutating} onClick={() => setConfirmClear(true)}>
            Clear cache
          </button>
        }
      >
        {ops.infraLoading ? (
          <p className="sg-empty">Loading cache stats…</p>
        ) : ops.cacheStats ? (
          <>
            <div className="stat-chips">
              <span className="stat-chip">
                items <b>{cache.items === null ? '—' : cache.items.toLocaleString('en-IN')}</b>
              </span>
              <span className="stat-chip">
                hit ratio <b>{cache.hitRatio === null ? '—' : `${cache.hitRatio}%`}</b>
              </span>
              <span className="stat-chip">
                evictions <b>{cache.evictions === null ? '—' : cache.evictions}</b>
              </span>
            </div>
            <KvList obj={ops.cacheStats} limit={12} />
          </>
        ) : (
          <p className="sg-empty">No cache stats reported.</p>
        )}
      </OpsCard>

      <OpsCard
        title="Circuit breaker"
        meta={breaker.name ? `${breaker.name} · GET /api/v1/circuit-breaker/status` : 'GET /api/v1/circuit-breaker/status'}
        action={
          <span className="sg-actions">
            <button type="button" className="btn" disabled={ops.mutating} onClick={() => setConfirmReset(true)}>
              Reset
            </button>
            <button type="button" className="btn btn-sell" disabled={ops.mutating} onClick={() => setConfirmTrip(true)}>
              Trip
            </button>
          </span>
        }
      >
        {ops.infraLoading ? (
          <p className="sg-empty">Loading breaker status…</p>
        ) : ops.breaker ? (
          <>
            <div className="stat-chips">
              <ToneBadge
                tone={toneForBreaker(breaker.state)}
                label={fmtCell(breaker.state)}
                title="Breaker state machine: CLOSED is healthy"
              />
              <span className="stat-chip">
                failures <b>{fmtCell(breaker.failures)}/{fmtCell(breaker.threshold)}</b>
              </span>
              <span className="stat-chip">
                trips <b>{fmtCell(breaker.tripped)}</b>
              </span>
            </div>
            <KvList obj={ops.breaker} limit={12} />
          </>
        ) : (
          <p className="sg-empty">No breaker status reported.</p>
        )}
        <p className="sg-note">
          Reset returns the breaker to CLOSED; trip forces OPEN for isolation testing. Both act on the
          shared backend feed breaker — use only when you intend to affect live quoting.
        </p>
      </OpsCard>

      <ConfirmDialog
        open={confirmClear}
        onOpenChange={(open) => {
          if (!open) setConfirmClear(false);
        }}
        tone="danger"
        confirmLabel="Clear cache"
        busy={ops.mutating}
        title="Clear all backend caches?"
        description="Flushes every cached entry. Downstream reads will re-fetch from providers."
        onConfirm={() => ops.clearCache().then((result) => finish(result, () => setConfirmClear(false)))}
      />

      <ConfirmDialog
        open={confirmReset}
        onOpenChange={(open) => {
          if (!open) setConfirmReset(false);
        }}
        tone="primary"
        confirmLabel="Reset breaker"
        busy={ops.mutating}
        title={`Reset the ${breaker.name ?? 'feed'} circuit breaker?`}
        description="Returns the breaker to CLOSED and resumes provider calls."
        onConfirm={() => ops.resetBreaker().then((result) => finish(result, () => setConfirmReset(false)))}
      />

      <ConfirmDialog
        open={confirmTrip}
        onOpenChange={(open) => {
          if (!open) setConfirmTrip(false);
        }}
        tone="danger"
        confirmLabel="Trip breaker"
        busy={ops.mutating}
        requireTypedConfirmation="TRIP"
        title={`Trip the ${breaker.name ?? 'feed'} circuit breaker?`}
        description="Forces the breaker OPEN — provider calls halt until reset. Affects live quoting."
        onConfirm={() => ops.tripBreaker().then((result) => finish(result, () => setConfirmTrip(false)))}
      />
    </div>
  );
}
