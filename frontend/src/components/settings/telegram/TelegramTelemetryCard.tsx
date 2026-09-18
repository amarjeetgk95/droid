'use client';

import React from 'react';
import { RefreshCw } from 'lucide-react';
import { SettingSection, StatTile } from '../ui/SettingPrimitives';
import { DataTable, type Column } from '@/components/ui/data-table';
import type { TelegramAuditRecord } from '@/lib/types';
import type { useTelegram } from './useTelegram';

interface Props {
  tg: ReturnType<typeof useTelegram>;
}

const auditColumns: Column<TelegramAuditRecord>[] = [
  {
    key: 'created_at_utc',
    header: 'Time',
    className: 'font-mono',
    render: (r) => (
      <span className="text-[var(--ds-ink-3)] whitespace-nowrap">
        {new Date(r.created_at_utc).toLocaleTimeString()}
      </span>
    ),
  },
  {
    key: 'event_type',
    header: 'Event',
    className: 'font-mono',
    render: (r) => (
      <div className="truncate max-w-[160px]">
        <span className="text-[var(--ds-ink)]">{r.event_type}</span>
        <div className="text-[10px] text-[var(--ds-ink-3)] truncate">{r.signal_id}</div>
      </div>
    ),
  },
  {
    key: 'delivery_status',
    header: 'Status',
    className: 'font-mono',
    render: (r) => (
      <span
        className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
          r.delivery_status === 'SENT'
            ? 'bg-[var(--ds-bull-wash)] text-[var(--ds-bull-strong)]'
            : r.delivery_status === 'FAILED'
              ? 'bg-[var(--ds-bear-wash)] text-[var(--ds-bear-strong)]'
              : 'bg-[var(--ds-inset)] text-[var(--ds-ink-3)]'
        }`}
      >
        {r.delivery_status}
      </span>
    ),
  },
  {
    key: 'attempt_count',
    header: 'Attempts',
    align: 'right',
    className: 'font-mono',
    render: (r) => <span className="text-[var(--ds-ink-3)]">{r.attempt_count}</span>,
  },
];

/** Dispatcher queue health + recent delivery audit log. */
export function TelegramTelemetryCard({ tg }: Props) {
  const statuses = tg.queueStats?.statuses as Record<string, number> | undefined;
  const deadLetter =
    tg.queueStats?.dead_letter != null ? String(tg.queueStats.dead_letter) : '—';

  return (
    <SettingSection
      title="Delivery telemetry & recent audit"
      description="Background dispatcher queue health and delivery logs."
      icon={RefreshCw}
      action={
        <button
          type="button"
          onClick={tg.refreshAll}
          disabled={tg.auditLoading}
          className="flex items-center gap-1 px-2.5 py-1 text-xs text-[var(--ds-ink-3)] hover:text-[var(--ds-ink)] rounded transition-colors cursor-pointer disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${tg.auditLoading ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
      }
    >
      <div className="p-5 space-y-4">
        {tg.statsError ? (
          <div className="p-2.5 rounded border border-[var(--ds-bear-line)] bg-[var(--ds-bear-wash)] text-xs text-[var(--ds-bear-strong)]">
            Queue telemetry unavailable — {tg.statsError}
          </div>
        ) : null}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatTile
            label="Queued"
            value={tg.queueStats?.queued != null ? String(tg.queueStats.queued) : '—'}
          />
          <StatTile
            label="Dead letter"
            value={deadLetter}
            tone={deadLetter !== '0' && deadLetter !== '—' ? 'negative' : 'default'}
          />
          <StatTile
            label="Total audited"
            value={tg.queueStats?.total != null ? String(tg.queueStats.total) : '—'}
          />
          <StatTile
            label="Status counts"
            value={
              statuses
                ? String(Object.values(statuses).reduce((a: number, b) => a + Number(b), 0))
                : '—'
            }
            sub={
              statuses ? (
                <span className="flex flex-wrap gap-1">
                  {Object.entries(statuses).map(([k, v]) => (
                    <span key={k} className="font-mono">
                      {k}: {String(v)}
                    </span>
                  ))}
                </span>
              ) : undefined
            }
          />
        </div>

        {tg.audit.length > 0 ? (
          <div className="rounded-lg border border-[var(--ds-border-subtle)] overflow-hidden">
            <DataTable
              data={tg.audit}
              columns={auditColumns}
              keyExtractor={(r) => r.notification_id}
              paginate={false}
              emptyMessage="No delivery logs recorded yet. Send a test probe to verify."
            />
          </div>
        ) : tg.auditError ? (
          <p className="text-xs text-[var(--ds-bear-strong)] text-center py-6 border border-[var(--ds-bear-line)] bg-[var(--ds-bear-wash)] rounded-lg">
            Delivery audit unavailable — {tg.auditError}
          </p>
        ) : (
          <p className="text-xs text-[var(--ds-ink-3)] text-center py-6 border border-dashed border-[var(--ds-border-strong)] rounded-lg">
            No delivery logs recorded yet. Send a test probe to verify.
          </p>
        )}
      </div>
    </SettingSection>
  );
}
