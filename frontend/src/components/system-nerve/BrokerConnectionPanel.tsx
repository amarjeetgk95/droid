'use client';

import React, { useCallback, useState } from 'react';
import { api } from '@/lib/api';
import type { BrokerTokenStatus } from '@/lib/api/tokens';
import { Card } from '@/components/ui/card';
import { Badge, type BadgeVariant } from '@/components/ui/badge';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
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

const POLL_MS = 8_000;

interface ActionOutcome {
  ok: boolean;
  text: string;
  at: number;
}

async function fetchTokenStatus(): Promise<BrokerTokenStatus> {
  const res = await api.getBrokerTokenStatus();
  if (res.error) throw new Error(res.error);
  if (!res.data) throw new Error('Token status payload missing from response.');
  return res.data;
}

function stateTone(state: string | null): BadgeVariant {
  switch ((state ?? '').toUpperCase()) {
    case 'CONNECTED':
      return 'success';
    case 'CONNECTING':
    case 'AUTHENTICATING':
    case 'RECONNECTING':
      return 'warning';
    case 'AUTH_EXPIRED':
    case 'RATE_LIMITED':
    case 'PROVIDER_ERROR':
      return 'danger';
    default:
      return 'neutral';
  }
}

export const BrokerConnectionPanel: React.FC = () => {
  const resource = usePanelResource(fetchTokenStatus, POLL_MS, () => null);
  const status = resource.data;

  const [diagBusy, setDiagBusy] = useState(false);
  const [diagnostics, setDiagnostics] = useState<ActionOutcome | null>(null);
  const [confirmRefresh, setConfirmRefresh] = useState(false);
  const [refreshBusy, setRefreshBusy] = useState(false);
  const [outcome, setOutcome] = useState<ActionOutcome | null>(null);

  const provider = asString(status?.provider) ?? 'UNAVAILABLE';
  const state = asString(status?.state);
  const tokenValid = typeof status?.is_token_valid === 'boolean' ? status.is_token_valid : null;
  const uptime = formatDuration(asNumber(status?.uptime_seconds));
  const dataLag = formatDuration(asNumber(status?.data_lag_seconds));
  const reconnectCount = asNumber(status?.reconnect_count);
  const subscriptionCount = asNumber(status?.subscription_count);
  const lastMessage = formatStamp(status?.last_message_at);
  const lastHeartbeat = formatStamp(status?.last_heartbeat_at);
  const lastError = asString(status?.last_error);

  const handleDiagnostics = useCallback(async () => {
    setDiagBusy(true);
    setDiagnostics(null);
    try {
      const res = await api.runTokenDiagnostics();
      const data = res.data;
      if (res.error) {
        setDiagnostics({
          ok: false,
          text: `Diagnostics completed without a new token: ${res.error}`,
          at: Date.now(),
        });
        return;
      }
      const diag = data?.diagnostics ?? {};
      const diagState = asString(diag.state) ?? 'unknown';
      const diagValid =
        typeof diag.is_token_valid === 'boolean'
          ? diag.is_token_valid
            ? 'valid'
            : 'expired/invalid'
          : 'unknown';
      const diagLag = formatDuration(asNumber(diag.data_lag_seconds));
      setDiagnostics({
        ok: data?.refreshed === true,
        text: `${data?.provider ?? 'broker'} diagnostics: credentials ${
          data?.refreshed === true ? 'refreshed' : 'not refreshed'
        }; session ${diagState}; token ${diagValid}${
          diagLag !== null ? `; data lag ${diagLag}` : ''
        }. This endpoint reports no round-trip latency or trading-permission verdict.`,
        at: Date.now(),
      });
    } catch (err) {
      setDiagnostics({ ok: false, text: toErrorMessage(err), at: Date.now() });
    } finally {
      setDiagBusy(false);
    }
  }, []);

  const handleRefresh = useCallback(async () => {
    setRefreshBusy(true);
    try {
      const res = await api.refreshBrokerToken();
      const data = res.data;
      if (res.error) {
        setOutcome({ ok: false, text: `Token refresh failed: ${res.error}`, at: Date.now() });
        return;
      }
      if (data?.refreshed) {
        setOutcome({
          ok: true,
          text: `Token refreshed for ${data.provider ?? 'broker'}${
            data.auth_method ? ` via ${data.auth_method}` : ''
          } at ${formatStamp(Date.now()) ?? 'now'}. Reloading status…`,
          at: Date.now(),
        });
        resource.refresh();
        return;
      }
      setOutcome({
        ok: false,
        text: `No new token was issued${
          data?.auth_method ? ` (auth method: ${data.auth_method})` : ''
        }${data?.state ? ` — session state ${data.state}` : ''}.`,
        at: Date.now(),
      });
    } catch (err) {
      setOutcome({ ok: false, text: toErrorMessage(err), at: Date.now() });
    } finally {
      setRefreshBusy(false);
      setConfirmRefresh(false);
    }
  }, [resource]);

  return (
    <Card
      title="Broker Gateway & Token Lifecycle"
      subtitle="FYERS session state, stream telemetry and credential diagnostics"
      headerAction={
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="btn"
            onClick={handleDiagnostics}
            disabled={diagBusy}
            aria-label="Run broker token diagnostics"
          >
            {diagBusy ? 'Diagnosing…' : 'Diagnostics'}
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => setConfirmRefresh(true)}
            disabled={refreshBusy}
            aria-label="Re-authenticate broker token"
          >
            {refreshBusy ? 'Refreshing…' : 'Refresh Token'}
          </button>
        </div>
      }
      footer={
        <PanelFreshness
          error={resource.error}
          hasData={status !== null}
          updatedAt={resource.updatedAt}
          generatedAt={resource.generatedAt}
          intervalMs={POLL_MS}
        />
      }
    >
      <div className="space-y-4 font-mono text-xs">
        <PanelStateBanner
          label="Broker token status"
          error={resource.error}
          hasData={status !== null}
          updatedAt={resource.updatedAt}
          onRetry={resource.refresh}
        />

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
          <TelemetryTile label="Broker Gateway" value={provider} sub="provider adapter" />

          <TelemetryTile
            label="Connection State"
            value={
              <Badge variant={stateTone(state)} size="xs" dot={status !== null}>
                {state ?? 'UNKNOWN'}
              </Badge>
            }
            sub={status === null ? 'status endpoint unavailable' : 'reported by token manager'}
          />

          <TelemetryTile
            label="Token Validity"
            value={
              <Badge
                variant={tokenValid === null ? 'neutral' : tokenValid ? 'success' : 'danger'}
                size="xs"
              >
                {tokenValid === null ? 'UNKNOWN' : tokenValid ? 'VALID' : 'EXPIRED'}
              </Badge>
            }
            sub="OAuth access token expiry check"
          />

          <TelemetryTile
            label="Session Uptime"
            value={uptime ?? 'NOT REPORTED'}
            sub={uptime === null ? 'reported only while CONNECTED' : 'since last CONNECTED transition'}
          />
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
          <TelemetryTile
            label="Data Lag"
            value={dataLag ?? 'UNAVAILABLE'}
            sub={
              dataLag === null
                ? 'no tick observed yet'
                : `last message ${lastMessage ?? 'time not reported'}`
            }
          />

          <TelemetryTile
            label="Last Heartbeat"
            value={lastHeartbeat ?? 'NOT REPORTED'}
            sub="provider heartbeat"
          />

          <TelemetryTile
            label="Reconnects"
            value={reconnectCount !== null ? String(reconnectCount) : 'UNKNOWN'}
            sub="cumulative reconnect attempts"
          />

          <TelemetryTile
            label="Subscriptions"
            value={subscriptionCount !== null ? String(subscriptionCount) : 'UNKNOWN'}
            sub="active stream subscriptions"
          />
        </div>

        {lastError ? (
          <div className="notice notice--down" role="alert">
            <span>
              <strong className="font-semibold">Last broker error:</strong> {lastError}
            </span>
          </div>
        ) : null}

        {diagnostics ? (
          <div
            className={`notice ${diagnostics.ok ? 'notice--up' : 'notice--warn'}`}
            role="status"
            aria-live="polite"
          >
            <span>
              <strong className="font-semibold">
                {diagnostics.ok ? 'Diagnostics refreshed credentials' : 'Diagnostics result'}
              </strong>{' '}
              — {diagnostics.text}
            </span>
          </div>
        ) : null}

        {outcome ? (
          <div
            className={`notice ${outcome.ok ? 'notice--up' : 'notice--down'}`}
            role="status"
            aria-live="polite"
          >
            <span>
              <strong className="font-semibold">
                {outcome.ok ? 'Token refresh succeeded' : 'Token refresh did not complete'}
              </strong>{' '}
              — {outcome.text}
            </span>
          </div>
        ) : null}
      </div>

      <ConfirmDialog
        isOpen={confirmRefresh}
        onClose={() => setConfirmRefresh(false)}
        onConfirm={handleRefresh}
        title="Re-authenticate broker token"
        message={
          <span>
            This requests a fresh FYERS access token and restarts the live provider stream. Open
            orders are not touched, but market data may pause briefly while the session
            reconnects.
          </span>
        }
        confirmLabel="Re-authenticate"
        destructive
      />
    </Card>
  );
};
