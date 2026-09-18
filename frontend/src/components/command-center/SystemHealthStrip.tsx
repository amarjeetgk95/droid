'use client';

import React, { useCallback, useRef, useState } from 'react';
import { usePolling } from '@/hooks/usePolling';
import { useMarketSession } from '@/hooks/useMarketSession';
import { api } from '@/lib/api';
import { toNumber } from '@/lib/coerce';
import { StatusDot, type StatusDotState } from '@/components/ui/status-dot';
import { Badge, type BadgeVariant } from '@/components/ui/badge';
import { FreshnessClock } from '@/components/common/FreshnessClock';

interface FeedCircuit {
  id: string;
  health: string;
  reason: string | null;
}

interface KillSwitchState {
  active: boolean;
  reason: string | null;
}

interface BrokerTokenState {
  isTokenValid: boolean;
  provider: string;
  state: string | null;
  dataLagSeconds: number | null;
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

export const SystemHealthStrip: React.FC = () => {
  const { isOpen } = useMarketSession();
  const [feeds, setFeeds] = useState<FeedCircuit[] | null>(null);
  const [killSwitch, setKillSwitch] = useState<KillSwitchState | null>(null);
  const [token, setToken] = useState<BrokerTokenState | null>(null);
  const [legErrors, setLegErrors] = useState<string[]>([]);
  const [lastAt, setLastAt] = useState<Date | null>(null);
  const hasDataRef = useRef(false);

  const load = useCallback(async () => {
    const [feedRes, killRes, tokenRes] = await Promise.allSettled([
      api.getSignalsFeedHealth(),
      api.getSignalsKillSwitch(),
      api.getBrokerTokenStatus(),
    ]);

    const failures: string[] = [];

    if (feedRes.status === 'fulfilled') {
      const rawStates = (feedRes.value as { states?: unknown })?.states;
      if (rawStates && typeof rawStates === 'object') {
        setFeeds(
          Object.entries(rawStates as Record<string, unknown>).map(([id, state]) =>
            parseFeed(id, state),
          ),
        );
      } else {
        setFeeds(null);
        failures.push('feed circuits');
      }
    } else {
      setFeeds(null);
      failures.push('feed circuits');
    }

    if (killRes.status === 'fulfilled' && typeof killRes.value?.active === 'boolean') {
      setKillSwitch({
        active: killRes.value.active,
        reason: typeof killRes.value.reason === 'string' ? killRes.value.reason : null,
      });
    } else {
      setKillSwitch(null);
      failures.push('kill switch');
    }

    if (tokenRes.status === 'fulfilled' && tokenRes.value?.data) {
      const d = tokenRes.value.data as unknown as Record<string, unknown>;
      setToken({
        isTokenValid: d.is_token_valid === true,
        provider: str(d.provider) ?? '—',
        state: str(d.state),
        dataLagSeconds: num(d.data_lag_seconds),
      });
    } else {
      setToken(null);
      failures.push('broker token');
    }

    setLegErrors(failures);
    if (failures.length < 3) {
      setLastAt(new Date());
      hasDataRef.current = true;
    }
  }, []);

  usePolling(() => {
    if (!isOpen && hasDataRef.current) return;
    return load();
  }, 5000);

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
            variant={killSwitch === null ? 'neutral' : killSwitch.active ? 'danger' : 'success'}
            size="xs"
            dot={killSwitch !== null}
          >
            {killSwitch === null ? 'UNAVAILABLE' : killSwitch.active ? 'HALTED' : 'STANDBY'}
          </Badge>
        </div>

        <div className="flex items-center gap-1.5">
          <span className="text-ink-3 font-semibold">BROKER:</span>
          <Badge variant={brokerVariant} size="xs" dot={token !== null}>
            {token === null
              ? 'UNAVAILABLE'
              : token.isTokenValid
                ? `${token.provider.toUpperCase()} ACTIVE`
                : 'REAUTH REQD'}
          </Badge>
        </div>

        <div className="text-ink-3 font-semibold">
          DATA LAG:{' '}
          <strong className="text-foreground">
            {token?.dataLagSeconds !== null && token?.dataLagSeconds !== undefined
              ? `${Math.round(token.dataLagSeconds)}s`
              : 'unavailable'}
          </strong>
        </div>

        <FreshnessClock
          lastAt={lastAt}
          marketClosed={!isOpen}
          dataQuality={legErrors.length > 0 ? 'DEGRADED' : null}
          sourceLabel="REST · 5s poll"
          note={legErrors.length > 0 ? `missing: ${legErrors.join(', ')}` : undefined}
        />
      </div>
    </div>
  );
};
