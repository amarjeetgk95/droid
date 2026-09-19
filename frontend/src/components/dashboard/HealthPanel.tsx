'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { errorMessage } from '@/lib/errors';
import { Panel } from '@/components/ui/Panel';
import type { FeedHealthSectionValue } from './sections';

type ForecastHealth = Awaited<ReturnType<typeof api.getForecastHealth>>;

function MetricGrid({ data, limit = 8 }: { data: Record<string, unknown> | null | undefined; limit?: number }) {
  if (!data) return null;
  const entries = Object.entries(data).filter(([, value]) => {
    const type = typeof value;
    return type === 'number' || type === 'string' || type === 'boolean';
  });
  if (entries.length === 0) return null;
  return (
    <div className="grid grid-cols-2 gap-x-4">
      {entries.slice(0, limit).map(([key, value]) => (
        <div key={key} className="sg-kv">
          <span className="l">{key.replace(/_/g, ' ')}</span>
          <span className="v">{typeof value === 'number' ? Math.round(value * 1000) / 1000 : String(value)}</span>
        </div>
      ))}
    </div>
  );
}

function circuitSummary(feed: FeedHealthSectionValue | null): { open: number; total: number; states: Array<[string, string]> } {
  const circuits = feed?.feed_circuits;
  const statesRaw = circuits?.states ?? circuits;
  if (!statesRaw || typeof statesRaw !== 'object') return { open: 0, total: 0, states: [] };
  const states = Object.entries(statesRaw as Record<string, unknown>)
    .filter(([, value]) => typeof value === 'string')
    .map(([key, value]) => [key, value as string] as [string, string]);
  const open = states.filter(([, state]) => !/CLOSED|OK|HEALTHY|NORMAL/i.test(state)).length;
  return { open, total: states.length, states };
}

export function HealthPanel({ feed }: { feed: FeedHealthSectionValue | null }) {
  const [health, setHealth] = useState<ForecastHealth | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const result = await api.getForecastHealth();
        if (!cancelled) {
          setHealth(result);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) setError(errorMessage(err, 'Forecast health unavailable'));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const circuits = circuitSummary(feed);
  const subsystemsStatus =
    feed?.subsystems && typeof feed.subsystems === 'object'
      ? String((feed.subsystems as Record<string, unknown>).status ?? 'unknown')
      : 'unknown';

  return (
    <Panel title="Engine & Feed Health" meta={health ? health.status.toUpperCase() : undefined}>
      {health ? (
        <>
          {health.degraded ? (
            <ul className="sg-list mt-0">
              {health.reasons.slice(0, 3).map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          ) : (
            <p className="m-0 text-[13px] text-ink-2">Forecast engine reporting healthy.</p>
          )}
          <div className="mt-2">
            <MetricGrid data={health.metrics} />
          </div>
        </>
      ) : (
        <p className="m-0 text-[13px] text-ink-2">
          {error ?? 'Forecast health loading…'}
        </p>
      )}

      <div className="mt-3 border-t border-border-subtle pt-3">
        <div className="flex items-center justify-between">
          <span className="stat-l">Feed circuits</span>
          <span className={`badge ${circuits.open === 0 ? 'b-bull' : 'b-warn'}`}>
            {circuits.total === 0 ? 'NO DATA' : `${circuits.total - circuits.open}/${circuits.total} OK`}
          </span>
        </div>
        {circuits.states.length > 0 ? (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {circuits.states.slice(0, 8).map(([symbol, state]) => (
              <span
                key={symbol}
                className={`sg-tag ${/CLOSED|OK|HEALTHY|NORMAL/i.test(state) ? 'bull' : 'warn'}`}
                title={state}
              >
                {symbol} {state}
              </span>
            ))}
          </div>
        ) : null}
        <div className="mt-2">
          <span className="sg-meta">
            subsystems: {subsystemsStatus}
          </span>
        </div>
      </div>
    </Panel>
  );
}
