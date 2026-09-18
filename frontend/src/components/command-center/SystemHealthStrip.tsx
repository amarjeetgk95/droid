'use client';

import React from 'react';
import { useCommandSection, useStreamStatus } from '@/context/AppStreamContext';
import { useMarketSession } from '@/hooks/useMarketSession';
import { toNumber } from '@/lib/coerce';
import { StatusDot, type StatusDotState } from '@/components/ui/status-dot';
import { Badge, type BadgeVariant } from '@/components/ui/badge';
import { FreshnessClock } from '@/components/common/FreshnessClock';

interface FeedCircuit {
  id: string;
  health: string;
  reason: string | null;
}

interface BrokerTokenState {
  isTokenValid: boolean;
  provider: string | null;
}

function asRecord(v: unknown): Record<string, unknown> | null {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
}

function num(v: unknown): number | null {
  return toNumber(v);
}

function str(v: unknown): string | null {
  return typeof v === 'string' && v.trim().length > 0 ? v : null;
}

function parseFeed(id: string, raw: unknown): FeedCircuit {
  if (typeof raw === 'string') return { id, health: raw, reason: null };
  if (raw && typeof raw === 'object') {
    const o = raw as Record<string, unknown>;
    return {
      id,
      health: str(o.health) ?? str(o.state) ?? 'UNKNOWN',
      reason: str(o.reason),
    };
  }
  return { id, health: 'UNKNOWN', reason: null };
}

function feedTone(health: string): { dot: StatusDotState; text: string } {
  switch (health.toUpperCase()) {
    case 'HEALTHY':
      return { dot: 'healthy', text: 'text-up-strong' };
    case 'FEED_DEGRADED':
      return { dot: 'error', text: 'text-down-strong' };
    case 'RECOVERING':
      return { dot: 'warning', text: 'text-warn-strong' };
    default:
      return { dot: 'offline', text: 'text-ink-3' };
  }
}

/** `/health/subsystems` posture: "ok:fyers" → "fyers"; otherwise no active provider. */
function providerFromPolicy(raw: unknown): string | null {
  const policy = str(raw);
  if (!policy) return null;
  const separator = policy.indexOf(':');
  if (separator === -1) return null;
  const kind = policy.slice(0, separator).toLowerCase();
  const name = policy.slice(separator + 1).trim();
  return kind === 'ok' && name.length > 0 ? name : null;
}

/**
 * System health strip — pure consumer of the unified command stream.
 *
 * Feed circuits come verbatim from `feed_health.value.feed_circuits` (the
 * `/signals/feed-health` payload), broker/token posture from
 * `feed_health.value.subsystems.elements` (`/health/subsystems`), and the kill
 * switch from `kill_switch.value`. Nothing here polls: a section that has not
 * arrived and a leg the backend reports as null both render as unavailable —
 * never as a fabricated value.
 */
export const SystemHealthStrip: React.FC = () => {
  const { isOpen } = useMarketSession();
  const status = useStreamStatus();
  const feedHealthSection = useCommandSection('feed_health');
  const killSwitchSection = useCommandSection('kill_switch');

  const feedHealthValue = asRecord(feedHealthSection?.value);
  const feedCircuits = asRecord(feedHealthValue?.feed_circuits);
  const rawStates = asRecord(feedCircuits?.states);
  const feeds: FeedCircuit[] | null = rawStates
    ? Object.entries(rawStates).map(([id, state]) => parseFeed(id, state))
    : null;

  const killSwitchValue = asRecord(killSwitchSection?.value);
  const killSwitchActive =
    killSwitchValue && typeof killSwitchValue.active === 'boolean' ? killSwitchValue.active : null;

  const subsystems = asRecord(feedHealthValue?.subsystems);
  const elements = asRecord(subsystems?.elements);
  const tokenStatus = str(elements?.token_status);
  const brokerLeg = asRecord(feedCircuits?.broker);
  const spotFeed = asRecord(feedCircuits?.spot_feed);
  const dataLagSeconds = num(spotFeed?.tick_age_seconds);

  const token: BrokerTokenState | null =
    elements === null || tokenStatus === null
      ? null
      : {
          isTokenValid: tokenStatus === 'present',
          provider:
            providerFromPolicy(elements.broker_provider_status) ?? str(brokerLeg?.provider),
        };

  const legErrors: string[] = [];
  if (feedHealthSection !== null && feeds === null) legErrors.push('feed circuits');
  if (killSwitchSection !== null && killSwitchActive === null) legErrors.push('kill switch');
  if (feedHealthSection !== null && token === null) legErrors.push('broker token');

  const degraded =
    legErrors.length > 0 ||
    feedHealthSection?.degraded === true ||
    killSwitchSection?.degraded === true;

  const lastAt = status.lastEventAt !== null ? new Date(status.lastEventAt) : null;

  const brokerVariant: BadgeVariant =
    token === null ? 'neutral' : token.isTokenValid ? 'success' : 'danger';

  return (
    <div className="p-3 rounded-xl border border-border bg-card shadow-xs flex flex-wrap items-center justify-between gap-3 text-xs font-mono">
      <div className="flex items-center gap-3">
        <span className="text-ink-3 font-semibold">FEED CIRCUITS:</span>
        <div className="flex flex-wrap items-center gap-2">
          {feeds === null ? (
            <span className="text-ink-4 px-2 py-0.5">unavailable</span>
          ) : feeds.length === 0 ? (
            <span className="text-ink-4 px-2 py-0.5">no feeds reported</span>
          ) : (
            feeds.map((feed) => {
              const tone = feedTone(feed.health);
              return (
                <div
                  key={feed.id}
                  className="flex items-center gap-1 bg-surface-subtle px-2 py-0.5 rounded border border-border"
                  title={feed.reason ?? undefined}
                >
                  <StatusDot status={tone.dot} pulse={feed.health.toUpperCase() !== 'HEALTHY'} />
                  <span className="text-ink-2 font-medium">{feed.id}:</span>
                  <span className={`${tone.text} font-semibold`}>{feed.health.toUpperCase()}</span>
                </div>
              );
            })
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1.5">
          <span className="text-ink-3 font-semibold">KILL SWITCH:</span>
          <Badge
            variant={killSwitchActive === null ? 'neutral' : killSwitchActive ? 'danger' : 'success'}
            size="xs"
            dot={killSwitchActive !== null}
          >
            {killSwitchActive === null ? 'UNAVAILABLE' : killSwitchActive ? 'HALTED' : 'STANDBY'}
          </Badge>
        </div>

        <div className="flex items-center gap-1.5">
          <span className="text-ink-3 font-semibold">BROKER:</span>
          <Badge variant={brokerVariant} size="xs" dot={token !== null}>
            {token === null
              ? 'UNAVAILABLE'
              : token.isTokenValid
                ? `${(token.provider ?? '—').toUpperCase()} ACTIVE`
                : 'REAUTH REQD'}
          </Badge>
        </div>

        <div className="text-ink-3 font-semibold">
          DATA LAG:{' '}
          <strong className="text-foreground">
            {dataLagSeconds !== null ? `${Math.round(dataLagSeconds)}s` : 'unavailable'}
          </strong>
        </div>

        <FreshnessClock
          lastAt={lastAt}
          marketClosed={!isOpen}
          dataQuality={degraded ? 'DEGRADED' : null}
          sourceLabel={status.source === 'sse' ? 'SSE · command stream' : 'REST · command view'}
          note={legErrors.length > 0 ? `missing: ${legErrors.join(', ')}` : undefined}
        />
      </div>
    </div>
  );
};
