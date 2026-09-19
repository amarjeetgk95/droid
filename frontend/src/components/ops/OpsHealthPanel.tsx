'use client';

/* Health tab: one card per probe — /health, /health/live, /health/ready,
   /health/subsystems, market-data, database, signals feed-health,
   monitoring forecast-config. Honest per-probe error states, no invented
   data. */

import { useMemo } from 'react';
import type { OpsConsole } from '@/hooks/useOpsConsole';
import { getObj, pickStr } from '@/lib/signalsNormalize';
import {
  circuitStates,
  countOpenCircuits,
  fmtCell,
  subsystemEntries,
  toneForStatus,
} from '@/lib/opsDesk';
import { CircuitTags, KvList, OpsCard, ToneBadge } from './OpsBits';

function ProbeCard({
  title,
  path,
  data,
  error,
  loading,
  children,
}: {
  title: string;
  path: string;
  data: unknown;
  error: string | null;
  loading: boolean;
  children?: React.ReactNode;
}) {
  const status = pickStr(getObj(data) ?? {}, 'status');
  return (
    <OpsCard
      title={title}
      meta={path}
      action={
        status ? <ToneBadge tone={toneForStatus(status)} label={status} /> : undefined
      }
    >
      {loading ? <p className="sg-empty">Probing…</p> : null}
      {!loading && error ? <p className="sg-err">{error}</p> : null}
      {!loading && !error && data === null ? <p className="sg-empty">No response recorded.</p> : null}
      {!loading && !error && data !== null ? (children ?? <KvList obj={data} limit={10} />) : null}
    </OpsCard>
  );
}

export function OpsHealthPanel({ ops }: { ops: OpsConsole }) {
  const subsystems = useMemo(() => subsystemEntries(ops.probes.subsystems.data), [ops.probes.subsystems.data]);
  const feedStates = useMemo(() => circuitStates(ops.probes.feed.data), [ops.probes.feed.data]);
  const feedOpen = countOpenCircuits(feedStates);
  const feedStatus = pickStr(getObj(ops.probes.feed.data) ?? {}, 'status');
  const dbObj = getObj(ops.probes.database.data);
  const dbCounts = getObj(dbObj?.counts);
  const forecastBundle = getObj(getObj(ops.probes.forecastConfig.data)?.bundle);
  const readyChecks = getObj(getObj(ops.probes.ready.data)?.checks);

  return (
    <div className="flex flex-col gap-3">
      <div className="pnl-strip">
        <span className="ps">
          probes <b>{Object.values(ops.probes).filter((p) => p.data !== null).length}/{Object.keys(ops.probes).length} responding</b>
        </span>
        <span className="ps">
          feed circuits <b>{feedStates.length === 0 ? '—' : `${feedStates.length - feedOpen}/${feedStates.length} OK`}</b>
        </span>
        <span className="ps">
          subsystems <b>{subsystems.length === 0 ? '—' : `${subsystems.length} reported`}</b>
        </span>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <ProbeCard title="Liveness" path="GET /health/live" data={ops.probes.live.data} error={ops.probes.live.error} loading={ops.healthLoading} />
        <ProbeCard title="Readiness" path="GET /health/ready" data={ops.probes.ready.data} error={ops.probes.ready.error} loading={ops.healthLoading}>
          {readyChecks ? <KvList obj={readyChecks} limit={8} /> : <KvList obj={ops.probes.ready.data} limit={8} />}
        </ProbeCard>
      </div>

      <ProbeCard
        title="Subsystems"
        path="GET /health/subsystems"
        data={ops.probes.subsystems.data}
        error={ops.probes.subsystems.error}
        loading={ops.healthLoading}
      >
        {subsystems.length === 0 ? (
          <p className="sg-empty">No subsystem elements reported.</p>
        ) : (
          <div className="tbl-scroll">
            <table className="sg-table">
              <thead>
                <tr>
                  <th>Element</th>
                  <th>State</th>
                </tr>
              </thead>
              <tbody>
                {subsystems.map(([name, label, tone]) => (
                  <tr key={name}>
                    <td>{name}</td>
                    <td>
                      <ToneBadge tone={tone} label={label} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </ProbeCard>

      <div className="grid gap-3 sm:grid-cols-2">
        <ProbeCard
          title="Market data"
          path="GET /api/v1/health/market-data"
          data={ops.probes.marketData.data}
          error={ops.probes.marketData.error}
          loading={ops.healthLoading}
        />
        <ProbeCard
          title="Database"
          path="GET /api/v1/health/database"
          data={ops.probes.database.data}
          error={ops.probes.database.error}
          loading={ops.healthLoading}
        >
          {dbObj ? (
            <>
              <div className="stat-chips">
                <span className="stat-chip">
                  connected <b>{fmtCell(dbObj.connected).toLowerCase()}</b>
                </span>
                <span className="stat-chip">
                  db <b>{fmtCell(dbObj.database)}</b>
                </span>
              </div>
              {dbCounts ? <KvList obj={dbCounts} limit={8} /> : <KvList obj={dbObj} limit={8} />}
            </>
          ) : null}
        </ProbeCard>
      </div>

      <ProbeCard
        title="Signals feed health"
        path="GET /api/v1/signals/feed-health"
        data={ops.probes.feed.data}
        error={ops.probes.feed.error}
        loading={ops.healthLoading}
      >
        {feedStatus ? (
          <p className="sg-note">{fmtCell(getObj(ops.probes.feed.data)?.message)}</p>
        ) : null}
        <CircuitTags states={feedStates} />
        <KvList obj={ops.probes.feed.data} limit={8} />
      </ProbeCard>

      <ProbeCard
        title="Forecast config"
        path="GET /api/v1/monitoring/forecast-config"
        data={ops.probes.forecastConfig.data}
        error={ops.probes.forecastConfig.error}
        loading={ops.healthLoading}
      >
        {forecastBundle && Object.keys(forecastBundle).length > 0 ? (
          <div className="tbl-scroll">
            <table className="sg-table">
              <thead>
                <tr>
                  <th>Bundle section</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(forecastBundle).map(([section, detail]) => (
                  <tr key={section}>
                    <td>
                      <span className="sg-sym">{section}</span>
                    </td>
                    <td className="mono">{fmtCell(detail)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="sg-empty">No release bundle reported.</p>
        )}
      </ProbeCard>
    </div>
  );
}
