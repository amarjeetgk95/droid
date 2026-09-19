'use client';

/* Ops Console — operator surface for backend internals.
   Tabs: Overview · Cache & Breakers · Pipeline · Health.
   Overview + health poll at 30s while the market is open, 5min when closed
   (useOpsConsole); infra refreshes on demand. Mutations sit behind
   ConfirmDialog with toast results. Never fabricates data. */

import { useMemo, useState } from 'react';
import { useCommandSection } from '@/context/AppStreamContext';
import { narrowFeedHealth } from '@/components/dashboard/sections';
import { useOpsConsole } from '@/hooks/useOpsConsole';
import {
  badgeClass,
  circuitStates,
  countOpenCircuits,
  fmtCell,
  summarizeBreaker,
  summarizeCache,
  toneForSession,
} from '@/lib/opsDesk';
import { OverviewPanel } from './OverviewPanel';
import { CacheBreakersPanel } from './CacheBreakersPanel';
import { PipelinePanel } from './PipelinePanel';
import { OpsHealthPanel } from './OpsHealthPanel';

type OpsTab = 'overview' | 'cache' | 'pipeline' | 'health';

const TABS: Array<{ id: OpsTab; label: string }> = [
  { id: 'overview', label: 'Overview' },
  { id: 'cache', label: 'Cache & Breakers' },
  { id: 'pipeline', label: 'Pipeline' },
  { id: 'health', label: 'Health' },
];

export function OpsModule() {
  const [tab, setTab] = useState<OpsTab>('overview');
  const ops = useOpsConsole();

  const feedSection = useCommandSection('feed_health');
  const feed = useMemo(() => narrowFeedHealth(feedSection?.value), [feedSection?.value]);
  const streamStates = useMemo(() => circuitStates(feed), [feed]);
  const restStates = useMemo(() => circuitStates(ops.probes.feed.data), [ops.probes.feed.data]);
  const states = streamStates.length > 0 ? streamStates : restStates;
  const openCircuits = countOpenCircuits(states);

  const session = typeof ops.marketStatus?.session === 'string' ? ops.marketStatus.session : null;
  const sessionTone = toneForSession(session ?? (ops.isOpen ? 'OPEN' : 'CLOSED'));
  const breakerSummary = summarizeBreaker(ops.breaker);
  const cacheSummary = summarizeCache(ops.cacheStats);

  const busy = ops.overviewRefreshing || ops.infraRefreshing;

  return (
    <div className="flex flex-col gap-3">
      <section className="ds-commandbar" aria-label="Ops console controls" aria-busy={busy}>
        <div className="ds-title">
          <h2>Ops Console</h2>
          <span className={`badge ${badgeClass(sessionTone)}`} title="Market session from /api/v1/markets/status">
            {session ?? (ops.isOpen ? 'OPEN' : 'CLOSED')}
          </span>
          <span
            className={`badge ${badgeClass(openCircuits === 0 ? 'bull' : 'warn')}`}
            title={states.length === 0 ? 'No feed circuit data yet' : 'Feed circuits (stream first, REST fallback)'}
          >
            {states.length === 0 ? 'FEED NO DATA' : `FEED ${states.length - openCircuits}/${states.length} OK`}
          </span>
          <span className="card-meta num">
            {ops.overviewUpdatedAt
              ? `overview ${new Date(ops.overviewUpdatedAt).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`
              : 'overview syncing…'}
          </span>
        </div>
        <div className="stat-chips">
          <span className="stat-chip">
            quotes <b>{ops.quotes.length}</b>
          </span>
          <span className="stat-chip" title="Circuit breaker state">
            breaker <b>{fmtCell(breakerSummary.state).toLowerCase()}</b>
          </span>
          <span className="stat-chip" title="Cache hit ratio">
            cache hit <b>{cacheSummary.hitRatio === null ? '—' : `${cacheSummary.hitRatio}%`}</b>
          </span>
          <span className="stat-chip" title="Execution state-machine orders">
            orders <b>{ops.orders.length}</b>
          </span>
          <span className="stat-chip">{ops.isOpen ? 'market open · 30s poll' : 'market closed · 5m poll'}</span>
        </div>
        <div className="ds-filters">
          <button type="button" className="btn" disabled={busy} onClick={() => void ops.refreshAll()}>
            {busy ? 'Refreshing…' : 'Refresh all'}
          </button>
        </div>
      </section>

      <section className="tabbar w-fit" role="tablist" aria-label="Ops console sections">
        {TABS.map((entry) => (
          <button
            key={entry.id}
            type="button"
            role="tab"
            aria-selected={tab === entry.id}
            className={`tab ${tab === entry.id ? 'is-active' : ''}`}
            onClick={() => setTab(entry.id)}
          >
            {entry.label}
            {entry.id === 'health' && ops.healthLoading ? <span className="n">…</span> : null}
          </button>
        ))}
      </section>

      {tab === 'overview' ? <OverviewPanel ops={ops} /> : null}
      {tab === 'cache' ? <CacheBreakersPanel ops={ops} /> : null}
      {tab === 'pipeline' ? <PipelinePanel ops={ops} /> : null}
      {tab === 'health' ? <OpsHealthPanel ops={ops} /> : null}
    </div>
  );
}
