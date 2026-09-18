'use client';

import React, { useCallback, useState } from 'react';
import { api } from '@/lib/api';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
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

interface TelegramBinding {
  linked: boolean;
  telegram_chat_id: string | null;
  linked_at: number | null;
  status: string;
}

interface TelegramStatusPayload {
  bot_configured: boolean;
  bot_username: string | null;
  webhook_configured: boolean;
  binding: TelegramBinding;
  environment: string;
  queue_stats: Record<string, unknown>;
}

interface ActionOutcome {
  ok: boolean;
  text: string;
  at: number;
}

async function fetchTelegramStatus(): Promise<TelegramStatusPayload> {
  const res = await api.getTelegramStatus();
  if (!res || typeof res !== 'object') {
    throw new Error('Telegram status payload missing from response.');
  }
  return res;
}

/** `binding.linked_at` is epoch seconds; render it without inventing a time. */
function linkedAtLabel(value: number | null | undefined): string | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null;
  const ms = value < 1e12 ? value * 1000 : value;
  return formatStamp(ms);
}

function queueStatusLabel(queue: Record<string, unknown> | undefined): string | null {
  const statuses = queue?.statuses;
  if (!statuses || typeof statuses !== 'object') return null;
  const parts = Object.entries(statuses as Record<string, unknown>)
    .map(([key, value]) => {
      const n = asNumber(value);
      return n !== null ? `${key} ${n}` : null;
    })
    .filter((part): part is string => part !== null);
  return parts.length > 0 ? parts.join(' · ') : null;
}

export const TelegramIntegration: React.FC = () => {
  const resource = usePanelResource(fetchTelegramStatus, POLL_MS, () => null);
  const status = resource.data;

  const [testBusy, setTestBusy] = useState(false);
  const [testOutcome, setTestOutcome] = useState<ActionOutcome | null>(null);
  const [confirmRevoke, setConfirmRevoke] = useState(false);
  const [revokeBusy, setRevokeBusy] = useState(false);
  const [revokeOutcome, setRevokeOutcome] = useState<ActionOutcome | null>(null);

  const binding = status?.binding;
  const linked = binding?.linked === true;
  const username = asString(status?.bot_username);
  const queue = status?.queue_stats;
  const queued = asNumber(queue?.queued);
  const total = asNumber(queue?.total);
  const deadLetter = asNumber(queue?.dead_letter);
  const statusBreakdown = queueStatusLabel(queue);

  const handleSendTest = useCallback(async () => {
    setTestBusy(true);
    setTestOutcome(null);
    try {
      const res = await api.sendTelegramTestMessage();
      setTestOutcome({
        ok: true,
        text: `Test alert enqueued (ID ${res.notification_id ?? res.status ?? 'unknown'}). Delivery is confirmed through the queue audit trail and may retry.`,
        at: Date.now(),
      });
      resource.refresh();
    } catch (err) {
      setTestOutcome({ ok: false, text: toErrorMessage(err), at: Date.now() });
    } finally {
      setTestBusy(false);
    }
  }, [resource]);

  const handleRevoke = useCallback(async () => {
    setRevokeBusy(true);
    try {
      const res = await api.revokeTelegramLink();
      const ok = res.status === 'revoked';
      setRevokeOutcome({
        ok,
        text: ok
          ? 'Telegram link revoked — no notifications will be delivered until the account is relinked.'
          : `Link revoke returned status "${res.status ?? 'unknown'}".`,
        at: Date.now(),
      });
      resource.refresh();
    } catch (err) {
      setRevokeOutcome({ ok: false, text: toErrorMessage(err), at: Date.now() });
    } finally {
      setRevokeBusy(false);
      setConfirmRevoke(false);
    }
  }, [resource]);

  return (
    <Card
      title="Telegram Bot & Push Dispatcher"
      subtitle="Bot configuration, webhook state, linked account and notification queue"
      headerAction={
        <button
          type="button"
          className="btn"
          onClick={handleSendTest}
          disabled={testBusy}
          aria-label="Send Telegram test alert"
        >
          {testBusy ? 'Sending…' : 'Send Test Ping'}
        </button>
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
          label="Telegram status"
          error={resource.error}
          hasData={status !== null}
          updatedAt={resource.updatedAt}
          onRetry={resource.refresh}
        />

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
          <TelemetryTile
            label="Telegram Bot"
            value={
              <Badge
                variant={status === null ? 'neutral' : status.bot_configured ? 'success' : 'neutral'}
                size="xs"
                dot={status !== null}
              >
                {status === null ? 'UNAVAILABLE' : status.bot_configured ? 'CONFIGURED' : 'NOT CONFIGURED'}
              </Badge>
            }
            sub={username ?? 'bot username not reported'}
          />

          <TelemetryTile
            label="Webhook"
            value={
              status === null ? (
                'UNAVAILABLE'
              ) : (
                <Badge variant={status.webhook_configured ? 'success' : 'neutral'} size="xs">
                  {status.webhook_configured ? 'CONFIGURED' : 'NOT CONFIGURED'}
                </Badge>
              )
            }
            sub="secret-verified inbound updates"
          />

          <TelemetryTile
            label="Account Link"
            value={
              <Badge
                variant={status === null ? 'neutral' : linked ? 'success' : 'danger'}
                size="xs"
                dot={status !== null}
              >
                {status === null ? 'UNAVAILABLE' : linked ? 'LINKED' : 'NOT LINKED'}
              </Badge>
            }
            sub={
              linked
                ? `since ${linkedAtLabel(binding?.linked_at) ?? 'time not reported'}`
                : 'link from Settings → Telegram Alerts'
            }
          />

          <TelemetryTile
            label="Chat ID"
            value={linked ? (asString(binding?.telegram_chat_id) ?? 'NOT REPORTED') : '—'}
            sub={
              linked
                ? `binding status ${asString(binding?.status) ?? 'unknown'}`
                : 'no linked chat'
            }
          />
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
          <TelemetryTile
            label="Environment"
            value={asString(status?.environment) ?? 'UNKNOWN'}
            sub="backend app environment"
          />

          <TelemetryTile
            label="Queued"
            value={queued !== null ? String(queued) : 'UNKNOWN'}
            sub="jobs awaiting dispatch"
          />

          <TelemetryTile
            label="Audit Records"
            value={total !== null ? String(total) : 'UNKNOWN'}
            sub={statusBreakdown ?? 'no delivery statuses recorded'}
          />

          <TelemetryTile
            label="Dead Letter"
            value={deadLetter !== null ? String(deadLetter) : 'UNKNOWN'}
            sub={deadLetter !== null && deadLetter > 0 ? 'delivery failures exhausted retries' : 'no failed deliveries parked'}
          />
        </div>

        <div className="pt-1 border-t border-border-subtle flex items-center justify-between gap-2">
          <span className="text-[10px] text-ink-3">
            Notification filters are managed in Settings → Telegram Alerts.
          </span>
          <button
            type="button"
            className="btn"
            onClick={() => setConfirmRevoke(true)}
            disabled={!linked || revokeBusy}
            aria-label="Revoke Telegram account link"
            title={linked ? undefined : 'No linked Telegram account to revoke'}
          >
            {revokeBusy ? 'Revoking…' : 'Unlink Telegram'}
          </button>
        </div>

        {testOutcome ? (
          <div
            className={`notice ${testOutcome.ok ? 'notice--up' : 'notice--down'}`}
            role="status"
            aria-live="polite"
          >
            <span>
              <strong className="font-semibold">
                {testOutcome.ok ? 'Test alert accepted' : 'Test alert failed'}
              </strong>{' '}
              — {testOutcome.text}
            </span>
          </div>
        ) : null}

        {revokeOutcome ? (
          <div
            className={`notice ${revokeOutcome.ok ? 'notice--warn' : 'notice--down'}`}
            role="status"
            aria-live="polite"
          >
            <span>
              <strong className="font-semibold">
                {revokeOutcome.ok ? 'Telegram unlinked' : 'Unlink failed'}
              </strong>{' '}
              — {revokeOutcome.text}
            </span>
          </div>
        ) : null}
      </div>

      <ConfirmDialog
        isOpen={confirmRevoke}
        onClose={() => setConfirmRevoke(false)}
        onConfirm={handleRevoke}
        title="Revoke Telegram link"
        message={
          <span>
            This removes the stored chat binding for your account. Signal, execution and result
            notifications will stop until you relink the bot from Settings. Preference filters are
            not changed.
          </span>
        }
        confirmLabel="Revoke link"
        destructive
      />
    </Card>
  );
};
