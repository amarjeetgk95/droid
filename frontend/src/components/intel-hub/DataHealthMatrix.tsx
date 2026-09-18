'use client';

import React, { useCallback, useMemo, useRef, useState } from 'react';
import { usePolling } from '@/hooks/usePolling';
import { api } from '@/lib/api';
import { asNumber, asRecord, asString, errorMessage } from './IntelHubData';
import { PanelNotice, formatAge, formatIstTime } from './IntelHubUi';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { StatusDot, type StatusDotState } from '@/components/ui/status-dot';
import { DataTable, type Column } from '@/components/ui/data-table';

const DATA_HEALTH_POLL_MS = 15_000;
const FRESHNESS_STALE_MS = 30_000;

interface HealthRow {
  id: string;
  status: string | null;
  feed: string | null;
}

interface HealthSnapshot {
  rows: HealthRow[];
  overall: Record<string, string>;
  generatedAtMs: number | null;
}

function parseHealth(raw: Record<string, unknown>): HealthSnapshot {
  const map = asRecord(raw.data_health) ?? {};
  const rows: HealthRow[] = Object.entries(map).map(([id, value]) => {
    const rec = asRecord(value);
    return { id, status: asString(rec?.status), feed: asString(rec?.feed) };
  });
  const overallRaw = asRecord(raw.overall) ?? {};
  const overall: Record<string, string> = {};
  for (const [key, value] of Object.entries(overallRaw)) {
    const text = asString(value);
    if (text !== null) overall[key] = text;
  }
  return { rows, overall, generatedAtMs: asNumber(raw.generated_at_ms) };
}

function statusBadgeVariant(status: string | null, feed: string | null): 'success' | 'warning' | 'danger' | 'neutral' {
  const s = (status ?? '').toUpperCase();
  const f = (feed ?? '').toUpperCase();
  if (s === 'LIVE' && f !== 'FEED_DEGRADED') return 'success';
  if (s === 'FEED_DEGRADED' || s === 'DISCONNECTED' || f === 'FEED_DEGRADED') return 'danger';
  if (s === 'STALE' || s === 'RECENT') return 'warning';
  return 'neutral';
}

function overallDotState(value: string | null): StatusDotState {
  const s = (value ?? '').toUpperCase();
  if (s === 'VALID') return 'healthy';
  if (s === 'DEGRADED' || s === 'UNKNOWN') return 'warning';
  if (s === 'INVALID' || s === 'MISSING') return 'error';
  return 'offline';
}

const OVERALL_LABELS: Record<string, string> = {
  clock_sync: 'Clock sync',
  sequence: 'Sequence',
  snapshot: 'Snapshot',
  contracts: 'Contracts',
};

export const DataHealthMatrix: React.FC = () => {
  const [snapshot, setSnapshot] = useState<{ data: HealthSnapshot; fetchedAt: number } | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const seqRef = useRef(0);

  const load = useCallback(async () => {
    const seq = ++seqRef.current;
    try {
      const raw = await api.getInstitutionalDataHealthDashboard();
      if (seq !== seqRef.current) return;
      setSnapshot({ data: parseHealth(raw), fetchedAt: Date.now() });
      setError(null);
    } catch (err) {
      if (seq !== seqRef.current) return;
      setError(errorMessage(err));
    }
  }, []);

  usePolling(load, DATA_HEALTH_POLL_MS);

  const runAction = useCallback(
    async (id: string, action: () => Promise<unknown>) => {
      setPendingId(id);
      setActionError(null);
      try {
        await action();
        await load();
      } catch (err) {
        setActionError(`${id}: ${errorMessage(err)}`);
      } finally {
        setPendingId(null);
      }
    },
    [load],
  );

  const generatedAtMs = snapshot?.data.generatedAtMs ?? null;
  const ageAtFetchMs =
    snapshot && generatedAtMs !== null ? Math.max(0, snapshot.fetchedAt - generatedAtMs) : null;
  const freshnessTone =
    ageAtFetchMs !== null && ageAtFetchMs > FRESHNESS_STALE_MS ? 'warn' : 'neutral';
  const age = formatAge(generatedAtMs, snapshot?.fetchedAt ?? 0);
  const ist = formatIstTime(generatedAtMs);

  const columns = useMemo<Column<HealthRow>[]>(
    () => [
      {
        key: 'id',
        header: 'Instrument',
        sortable: true,
        render: (row) => <span className="font-bold text-ink">{row.id}</span>,
      },
      {
        key: 'status',
        header: 'Data Status',
        sortable: true,
        sortValue: (row) => row.status ?? null,
        render: (row) => (
          <Badge variant={statusBadgeVariant(row.status, row.feed)} size="xs">
            {row.status ?? 'UNKNOWN'}
          </Badge>
        ),
      },
      {
        key: 'feed',
        header: 'Feed Circuit',
        sortable: true,
        sortValue: (row) => row.feed ?? null,
        render: (row) => <span className="text-ink-2">{row.feed ?? '—'}</span>,
      },
      {
        key: 'actions',
        header: 'Actions',
        align: 'right',
        render: (row) => (
          <span className="inline-flex gap-2">
            <button
              type="button"
              onClick={() => void runAction(row.id, () => api.tripFeedCircuit(row.id))}
              disabled={pendingId === row.id}
              className="rounded border border-down-line bg-down-wash px-2 py-0.5 text-[10px] font-semibold text-down-strong hover:opacity-80 disabled:opacity-50"
            >
              Trip circuit
            </button>
            <button
              type="button"
              onClick={() => void runAction(row.id, () => api.resyncFeedCircuit(row.id))}
              disabled={pendingId === row.id}
              className="rounded border border-up-line bg-up-wash px-2 py-0.5 text-[10px] font-semibold text-up-strong hover:opacity-80 disabled:opacity-50"
            >
              Resync
            </button>
          </span>
        ),
      },
    ],
    [pendingId, runAction],
  );

  return (
    <Card
      title="DATA INTEGRITY & FEED CIRCUIT MATRIX"
      subtitle="Per-instrument feed state from the institutional data-health dashboard"
    >
      <div className="space-y-3 font-mono text-xs">
        {error ? (
          <PanelNotice tone="down" role="alert">
            Data health unavailable — {error}
          </PanelNotice>
        ) : null}
        {actionError ? (
          <PanelNotice tone="down" role="alert">
            Circuit action failed — {actionError}
          </PanelNotice>
        ) : null}
        {!snapshot && !error ? (
          <PanelNotice role="status">Waiting for data-health dashboard…</PanelNotice>
        ) : null}

        {snapshot ? (
          <>
            {/* Freshness */}
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className={freshnessTone === 'warn' ? 'text-warn-strong' : 'text-ink-3'}>
                {ist ? `Generated ${ist}` : 'Generation time unavailable'}
                {age ? ` · age at fetch ${age}` : ''}
                {freshnessTone === 'warn' ? ' · stale snapshot' : ''}
              </span>
            </div>

            {/* Overall integrity strip */}
            <div className="flex flex-wrap items-center gap-4 rounded-lg border border-border bg-surface-subtle p-2.5">
              {Object.entries(OVERALL_LABELS).map(([key, label]) => {
                const value = snapshot.data.overall[key] ?? null;
                return (
                  <StatusDot
                    key={key}
                    status={overallDotState(value)}
                    pulse={false}
                    label={`${label}: ${value ?? 'UNKNOWN'}`}
                  />
                );
              })}
            </div>

            {snapshot.data.rows.length === 0 ? (
              <PanelNotice>No instrument data-health rows were returned.</PanelNotice>
            ) : (
              <DataTable
                data={snapshot.data.rows}
                columns={columns}
                keyExtractor={(row) => row.id}
                paginate={false}
                emptyMessage="No instrument data-health rows were returned."
              />
            )}
          </>
        ) : null}
      </div>
    </Card>
  );
};
