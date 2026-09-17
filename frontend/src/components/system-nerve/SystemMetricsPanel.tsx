'use client';

import React from 'react';
import { api } from '@/lib/api';
import type { MarketHealthStatus } from '@/lib/types';
import { Card } from '../shared/Card';
import { Badge, type BadgeVariant } from '../shared/Badge';
import { StatusDot, type StatusDotState } from '../shared/StatusDot';
import {
  PanelFreshness,
  PanelStateBanner,
  TelemetryTile,
  asNumber,
  asString,
  formatDuration,
  formatStamp,
  toErrorMessage,
  usePanelResource,
} from './PanelState';

const POLL_MS = 10_000;

interface SubsystemsPayload {
  status?: string;
  elements?: Record<string, unknown>;
  timestamp?: string;
}

interface DatabaseHealthPayload {
  status?: string;
  connected?: boolean;
  error?: string;
  configured?: boolean;
  database?: string | null;
  user?: string | null;
  counts?: Record<string, number | null>;
}

interface CircuitBreakerStatus {
  state?: string;
  failure_count?: number;
  failure_threshold?: number;
  tripped_count?: number;
  last_state_change_at?: string;
}

interface Leg<T> {
  value: T | null;
  error: string | null;
}

interface RuntimeSnapshot {
  subsystems: Leg<SubsystemsPayload>;
  database: Leg<DatabaseHealthPayload>;
  breaker: Leg<CircuitBreakerStatus>;
  market: Leg<MarketHealthStatus>;
}

function toLeg<T>(result: PromiseSettledResult<T>): Leg<T> {
  return result.status === 'fulfilled'
    ? { value: result.value, error: null }
    : { value: null, error: toErrorMessage(result.reason) };
}

/**
 * One snapshot from every real runtime endpoint this backend exposes.
 * There is deliberately no CPU/RAM leg: no such endpoint exists, so the UI
 * renders those as unavailable instead of inventing numbers.
 */
async function fetchRuntimeSnapshot(): Promise<RuntimeSnapshot> {
  const [subsystems, database, breaker, market] = await Promise.allSettled([
    api.request<SubsystemsPayload>('/health/subsystems'),
    api.request<DatabaseHealthPayload>('/api/v1/health/database'),
    api.getCircuitBreakerStatus().then((res) => {
      if (res.error) throw new Error(res.error);
      return (res.data ?? {}) as CircuitBreakerStatus;
    }),
    api.getMarketHealth(),
  ]);

  const snapshot: RuntimeSnapshot = {
    subsystems: toLeg(subsystems),
    database: toLeg(database),
    breaker: toLeg(breaker),
    market: toLeg(market),
  };

  const hasAnyValue =
    snapshot.subsystems.value !== null ||
    snapshot.database.value !== null ||
    snapshot.breaker.value !== null ||
    snapshot.market.value !== null;
  if (!hasAnyValue) {
    throw new Error(
      snapshot.subsystems.error ??
        snapshot.database.error ??
        snapshot.breaker.error ??
        snapshot.market.error ??
        'all telemetry endpoints failed',
    );
  }

  return snapshot;
}

function boolState(value: unknown): { label: string; variant: BadgeVariant; dot: StatusDotState } {
  if (value === true) return { label: 'RUNNING', variant: 'success', dot: 'healthy' };
  if (value === false) return { label: 'HALTED', variant: 'danger', dot: 'error' };
  return { label: 'UNKNOWN', variant: 'neutral', dot: 'offline' };
}

function marketTone(status: string | null): { variant: BadgeVariant; dot: StatusDotState } {
  switch ((status ?? '').toUpperCase()) {
    case 'HEALTHY':
      return { variant: 'success', dot: 'healthy' };
    case 'DEGRADED':
      return { variant: 'warning', dot: 'degraded' };
    case 'UNHEALTHY':
      return { variant: 'danger', dot: 'error' };
    default:
      return { variant: 'neutral', dot: 'offline' };
  }
}

function breakerTone(state: string | null): BadgeVariant {
  switch ((state ?? '').toUpperCase()) {
    case 'CLOSED':
      return 'success';
    case 'HALF_OPEN':
      return 'warning';
    case 'OPEN':
      return 'danger';
    default:
      return 'neutral';
  }
}

function countsLabel(counts?: Record<string, number | null>): string | null {
  if (!counts) return null;
  const parts: string[] = [];
  if (typeof counts.executed_signals === 'number') {
    parts.push(`executed ${counts.executed_signals}`);
  }
  if (typeof counts.algo_signals === 'number') {
    parts.push(`algo ${counts.algo_signals}`);
  }
  return parts.length > 0 ? parts.join(' · ') : null;
}

const WORKER_KEYS = [
  'signal_worker',
  'morning_briefing',
  'forecast_scheduler',
  'flow_scheduler',
] as const;

export const SystemMetricsPanel: React.FC = () => {
  const resource = usePanelResource(fetchRuntimeSnapshot, POLL_MS, (snap) => {
    return snap.subsystems.value?.timestamp ?? null;
  });

  const snapshot = resource.data;
  const elements = snapshot?.subsystems.value?.elements ?? null;

  const market = snapshot?.market.value ?? null;
  const marketState = asString(market?.status);
  const marketToneResult = marketTone(marketState);

  const centralFeed = boolState(elements?.central_feed);

  const database = snapshot?.database.value ?? null;
  const databaseError = snapshot?.database.error ?? null;

  const breaker = snapshot?.breaker.value ?? null;
  const breakerState = asString(breaker?.state);

  const workers = WORKER_KEYS.map((key) => ({ key, raw: elements?.[key] }));
  const workersRunning = workers.filter((w) => w.raw === true).length;
  const workersKnown = workers.filter((w) => typeof w.raw === 'boolean').length;
  const workersUnknown = workers.length - workersKnown;
  const workersHalted = workers.filter((w) => w.raw === false).map((w) => w.key);

  const chainStatus = asString(elements?.chain_status);
  const chainStrikes = asNumber(elements?.chain_strikes);
  const chainAgeMs = asNumber(elements?.chain_age_ms);
  const markStatus = asString(elements?.chain_mark_status);
  const sanityRejections = asNumber(elements?.tick_sanity_rejections);

  const chainTone: BadgeVariant =
    chainStatus === 'FRESH' ? 'success' : chainStatus === 'STALE' ? 'warning' : 'neutral';
  const markTone: BadgeVariant =
    markStatus === 'LIVE' ? 'success' : markStatus === 'MODEL_ONLY' ? 'warning' : 'neutral';

  return (
    <Card
      title="System Runtime Telemetry"
      subtitle="Live backend subsystems, database connectivity, circuit breaker and market-data health"
      headerAction={
        <button
          type="button"
          className="btn"
          onClick={resource.refresh}
          disabled={resource.fetching}
          aria-label="Refresh system telemetry"
        >
          {resource.fetching ? 'Refreshing…' : 'Refresh'}
        </button>
      }
      footer={
        <PanelFreshness
          error={resource.error}
          hasData={snapshot !== null}
          updatedAt={resource.updatedAt}
          generatedAt={resource.generatedAt}
          intervalMs={POLL_MS}
        />
      }
    >
      <div className="space-y-4 font-mono text-xs">
        <PanelStateBanner
          label="System telemetry"
          error={resource.error}
          hasData={snapshot !== null}
          updatedAt={resource.updatedAt}
          onRetry={resource.refresh}
        />

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
          <TelemetryTile
            label="Market Data Feed"
            value={
              <Badge variant={marketToneResult.variant} size="xs" dot={market !== null}>
                {marketState ?? 'UNAVAILABLE'}
              </Badge>
            }
            sub={
              market
                ? `mode ${market.mode ?? 'unknown'} · data age ${
                    formatDuration(market.data_age_seconds) ?? 'not reported'
                  }`
                : (snapshot?.market.error ?? 'market-data health endpoint unavailable')
            }
          />

          <TelemetryTile
            label="Central Feed Worker"
            value={
              <>
                <StatusDot status={centralFeed.dot} pulse={false} />
                <Badge variant={centralFeed.variant} size="xs">
                  {centralFeed.label}
                </Badge>
              </>
            }
            sub={
              elements
                ? `chain ${
                    chainStrikes !== null ? `${chainStrikes} strikes` : 'strike count not reported'
                  }`
                : 'subsystems endpoint unavailable'
            }
          />

          <TelemetryTile
            label="PostgreSQL"
            value={
              <Badge
                variant={
                  database === null ? 'neutral' : database.connected === true ? 'success' : 'danger'
                }
                size="xs"
                dot={database !== null}
              >
                {database === null
                  ? 'UNAVAILABLE'
                  : database.connected === true
                    ? 'CONNECTED'
                    : 'DISCONNECTED'}
              </Badge>
            }
            sub={
              database
                ? (countsLabel(database.counts) ??
                  database.database ??
                  'no row counts reported')
                : (databaseError ?? 'database health endpoint unavailable')
            }
          />

          <TelemetryTile
            label="Circuit Breaker"
            value={
              <Badge
                variant={breakerTone(breakerState)}
                size="xs"
                dot={breaker !== null}
              >
                {breakerState ?? 'UNKNOWN'}
              </Badge>
            }
            sub={
              breaker
                ? `failures ${asNumber(breaker.failure_count) ?? '?'} / ${
                    asNumber(breaker.failure_threshold) ?? '?'
                  } · tripped ${asNumber(breaker.tripped_count) ?? '?'}`
                : (snapshot?.breaker.error ?? 'circuit-breaker endpoint unavailable')
            }
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <TelemetryTile
            label="Background Workers"
            value={`${workersKnown > 0 ? `${workersRunning}/${workersKnown} running` : 'UNKNOWN'}${
              workersUnknown > 0 ? ` · ${workersUnknown} unknown` : ''
            }`}
            sub={
              workersHalted.length > 0
                ? `halted: ${workersHalted.join(', ')}`
                : workersKnown === workers.length
                  ? 'all scheduled workers reported running'
                  : 'worker states not fully reported by backend'
            }
          />

          <TelemetryTile
            label="Options Chain Provenance"
            value={
              <>
                <Badge variant={chainTone} size="xs">
                  CHAIN {chainStatus ?? 'UNKNOWN'}
                </Badge>
                <Badge variant={markTone} size="xs">
                  MARKS {markStatus ?? 'UNKNOWN'}
                </Badge>
              </>
            }
            sub={
              elements
                ? `chain age ${
                    chainAgeMs !== null ? `${Math.round(chainAgeMs / 1000)}s` : 'not reported'
                  } · tick sanity rejections ${sanityRejections ?? 'not reported'}`
                : 'subsystems endpoint unavailable'
            }
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="p-2.5 rounded-md bg-surface-subtle border border-border-subtle">
            <div className="micro-label">Backend CPU Load</div>
            <div className="text-xs text-ink-2 mt-1">
              UNAVAILABLE — this backend exposes no CPU telemetry endpoint. No value is invented.
            </div>
          </div>
          <div className="p-2.5 rounded-md bg-surface-subtle border border-border-subtle">
            <div className="micro-label">RAM Utilization</div>
            <div className="text-xs text-ink-2 mt-1">
              UNAVAILABLE — this backend exposes no memory telemetry endpoint. No value is invented.
            </div>
          </div>
        </div>

        {elements?.broker_provider_status || elements?.token_status ? (
          <div className="text-[10px] text-ink-3">
            {elements?.broker_provider_status
              ? `Broker provider policy: ${String(elements.broker_provider_status)}`
              : null}
            {elements?.broker_provider_status && elements?.token_status ? ' · ' : ''}
            {elements?.token_status ? `Broker token: ${String(elements.token_status)}` : null}
            {snapshot?.subsystems.value?.timestamp
              ? ` · subsystems generated ${formatStamp(snapshot.subsystems.value.timestamp) ?? 'unknown'}`
              : ''}
          </div>
        ) : null}
      </div>
    </Card>
  );
};
