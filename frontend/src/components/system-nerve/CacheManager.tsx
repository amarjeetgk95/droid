'use client';

import React, { useCallback, useState } from 'react';
import { api } from '@/lib/api';
import { Card } from '../shared/Card';
import { Gauge } from '../shared/Gauge';
import { ConfirmDialog } from '../shared/ConfirmDialog';
import {
  PanelFreshness,
  PanelStateBanner,
  TelemetryTile,
  asNumber,
  asString,
  formatStamp,
  toErrorMessage,
  usePanelResource,
} from './PanelState';

const POLL_MS = 15_000;

interface CacheSnapshot {
  stats: Record<string, unknown>;
  timestamp: string | null;
}

interface Outcome {
  ok: boolean;
  text: string;
  at: number;
}

async function fetchCacheStats(): Promise<CacheSnapshot> {
  const res = await api.getCacheStats();
  if (res.error) throw new Error(res.error);
  return { stats: res.data ?? {}, timestamp: asString(res.meta?.timestamp) };
}

export const CacheManager: React.FC = () => {
  const resource = usePanelResource(fetchCacheStats, POLL_MS, (snap) => snap.timestamp);
  const stats = resource.data?.stats;

  const [confirmClear, setConfirmClear] = useState(false);
  const [clearBusy, setClearBusy] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);

  const backend = asString(stats?.backend);
  const items = asNumber(stats?.items_count);
  const capacity = asNumber(stats?.max_capacity);
  const hits = asNumber(stats?.hit_count);
  const misses = asNumber(stats?.miss_count);
  const total = asNumber(stats?.total_requests);
  const hitRatio = asNumber(stats?.hit_ratio_percent);
  const evictions = asNumber(stats?.eviction_count);
  const expired = asNumber(stats?.expired_count);

  const handleClear = useCallback(async () => {
    setClearBusy(true);
    try {
      const res = await api.clearCache();
      if (res.error) {
        setOutcome({ ok: false, text: `Cache flush failed: ${res.error}`, at: Date.now() });
        return;
      }
      if (res.data?.cleared !== true) {
        setOutcome({
          ok: false,
          text: `Backend did not confirm the flush (cleared=${String(res.data?.cleared)}).`,
          at: Date.now(),
        });
        return;
      }
      setOutcome({
        ok: true,
        text: `Cache flushed at ${formatStamp(Date.now()) ?? 'now'}. Entries before flush: ${
          items ?? 'not reported'
        }. Hit/miss counters are cumulative server-side and are not reset by a flush.`,
        at: Date.now(),
      });
      resource.refresh();
    } catch (err) {
      setOutcome({ ok: false, text: toErrorMessage(err), at: Date.now() });
    } finally {
      setClearBusy(false);
      setConfirmClear(false);
    }
  }, [resource, items]);

  return (
    <Card
      title="In-Memory Cache Engine"
      subtitle="LRU cache statistics and invalidation — no memory figure is exposed by this backend"
      headerAction={
        <button
          type="button"
          className="btn"
          onClick={() => setConfirmClear(true)}
          disabled={clearBusy || resource.data === null}
          aria-label="Purge in-memory cache"
          title={resource.data === null ? 'Cache statistics unavailable' : undefined}
        >
          {clearBusy ? 'Flushing…' : 'Purge Cache'}
        </button>
      }
      footer={
        <PanelFreshness
          error={resource.error}
          hasData={resource.data !== null}
          updatedAt={resource.updatedAt}
          generatedAt={resource.generatedAt}
          intervalMs={POLL_MS}
        />
      }
    >
      <div className="space-y-4 font-mono text-xs">
        <PanelStateBanner
          label="Cache statistics"
          error={resource.error}
          hasData={resource.data !== null}
          updatedAt={resource.updatedAt}
          onRetry={resource.refresh}
        />

        {hitRatio !== null ? (
          <Gauge
            value={hitRatio}
            label="Cache hit ratio"
            unit="%"
            invertThresholds
            thresholds={{ warning: 70, danger: 40 }}
            sublabel={`${hits ?? '?'} hits / ${total ?? '?'} requests · backend ${backend ?? 'unknown'}`}
          />
        ) : resource.data !== null ? (
          <div className="notice notice--warn" role="status">
            <span>Hit ratio is not reported by the cache stats endpoint.</span>
          </div>
        ) : null}

        <div className="grid grid-cols-2 lg:grid-cols-3 gap-2">
          <TelemetryTile
            label="Items"
            value={
              items !== null
                ? `${items}${capacity !== null ? ` / ${capacity}` : ''}`
                : 'UNKNOWN'
            }
            sub="current entries / max capacity"
          />
          <TelemetryTile
            label="Total Hits"
            value={hits !== null ? hits.toLocaleString() : 'UNKNOWN'}
            sub="cumulative since process start"
          />
          <TelemetryTile
            label="Total Misses"
            value={misses !== null ? misses.toLocaleString() : 'UNKNOWN'}
            sub="cumulative since process start"
          />
          <TelemetryTile
            label="Evictions"
            value={evictions !== null ? evictions.toLocaleString() : 'UNKNOWN'}
            sub="LRU capacity evictions"
          />
          <TelemetryTile
            label="Expired Entries"
            value={expired !== null ? expired.toLocaleString() : 'UNKNOWN'}
            sub="dropped on TTL expiry"
          />
          <TelemetryTile label="Backend" value={backend ?? 'UNKNOWN'} sub="cache implementation" />
        </div>

        {outcome ? (
          <div
            className={`notice ${outcome.ok ? 'notice--up' : 'notice--down'}`}
            role="status"
            aria-live="polite"
          >
            <span>
              <strong className="font-semibold">
                {outcome.ok ? 'Cache purged' : 'Cache purge did not complete'}
              </strong>{' '}
              — {outcome.text}
            </span>
          </div>
        ) : null}
      </div>

      <ConfirmDialog
        isOpen={confirmClear}
        onClose={() => setConfirmClear(false)}
        onConfirm={handleClear}
        title="Purge in-memory cache"
        message={
          <span>
            All cached entries (option chains, quotes, dashboard snapshots) are dropped. The backend
            re-fetches from the broker on the next request; broker rate limits may temporarily
            throttle the first refresh.
          </span>
        }
        confirmLabel="Purge cache"
        destructive
      />
    </Card>
  );
};
