'use client';

import React, { useEffect, useState } from 'react';
import {
  Activity,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
} from 'lucide-react';
import type { BrokerSettings, AppSettings } from '@/lib/settings';
import { api } from '@/lib/api';
import { useSettings } from '@/components/settings/SettingsProvider';
import { getProviderMeta } from './constants';
import { SettingSection, StatTile } from '../ui/SettingPrimitives';

interface Props {
  settings: BrokerSettings;
  fullSettings?: AppSettings;
}

export function TelemetryCard({ settings, fullSettings: propFullSettings }: Props) {
  const [tokenStatus, setTokenStatus] = useState<Record<string, unknown> | null>(null);
  const [loadingToken, setLoadingToken] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [tokenMsg, setTokenMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{
    success: boolean;
    provider: string;
    latency_ms: number;
    token_valid: boolean;
    quote?: { symbol: string; ltp: number };
    error?: string | null;
  } | null>(null);

  let contextFullSettings: AppSettings | null = null;
  try {
    contextFullSettings = (useSettings() as unknown as { settings: AppSettings })?.settings ?? null;
  } catch {
    contextFullSettings = null;
  }
  const fullSettings = propFullSettings || contextFullSettings;

  const providerMeta = getProviderMeta(settings.provider, settings.apiType, tokenStatus);

  const fetchTokenStatus = async () => {
    setLoadingToken(true);
    try {
      const res = await api.getTokenStatus();
      setTokenStatus(res.data as Record<string, unknown>);
    } catch {
      setTokenStatus({ provider: settings.provider, has_token: false, is_valid: false, expires_at: null });
    } finally {
      setLoadingToken(false);
    }
  };

  useEffect(() => {
    fetchTokenStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings.provider, settings.apiType, tokenMsg]);

  const handleRefreshToken = async () => {
    setRefreshing(true);
    setTokenMsg(null);
    try {
      const payload = fullSettings ? { app_settings: fullSettings } : { app_settings: { broker: settings } };
      const res = await api.refreshToken(payload as Record<string, unknown>);
      if ((res.data as unknown as { refreshed: boolean }).refreshed) {
        setTokenMsg({
          type: 'success',
          text: `Token successfully refreshed for ${(res.data as unknown as { provider: string }).provider.toUpperCase()}.`,
        });
      } else {
        setTokenMsg({
          type: 'error',
          text: (res as unknown as { error?: string }).error || 'Token refresh failed.',
        });
      }
      await fetchTokenStatus();
    } catch (err: unknown) {
      setTokenMsg({ type: 'error', text: err instanceof Error ? err.message : 'Failed to refresh token' });
    } finally {
      setRefreshing(false);
    }
  };

  const handleTestConnection = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const creds =
        settings.provider === 'fyers'
          ? settings.fyers
          : (settings as unknown as Record<string, unknown>)[settings.provider] || {};
      const res = await api.testBrokerConnection({ provider: settings.provider, credentials: creds as Record<string, unknown> });
      setTestResult(res.data as unknown as typeof testResult);
    } catch (err: unknown) {
      setTestResult({
        success: false,
        provider: settings.provider,
        latency_ms: 0,
        token_valid: false,
        error: err instanceof Error ? err.message : 'Connection test probe failed',
      });
    } finally {
      setTesting(false);
    }
  };

  return (
    <SettingSection
      title="Session Telemetry & Gateway Health"
      description="Token lifecycle and gateway heartbeat monitored by Render TokenManager."
      icon={Activity}
      action={
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleTestConnection}
            disabled={testing}
            className="btn btn-sm flex items-center gap-1.5"
          >
            <Activity className={`w-3.5 h-3.5 muted ${testing ? 'animate-spin' : ''}`} />
            <span>{testing ? 'Probing...' : 'Test Connection'}</span>
          </button>
          <button
            type="button"
            onClick={handleRefreshToken}
            disabled={refreshing || loadingToken}
            className="btn btn-sm flex items-center gap-1.5"
          >
            <RefreshCw className={`w-3.5 h-3.5 muted ${refreshing ? 'animate-spin' : ''}`} />
            <span>{refreshing ? 'Refreshing...' : 'Refresh Token'}</span>
          </button>
        </div>
      }
    >
      <div className="card-pad space-y-4">
        {testResult && (
          <div
            className={`card card-pad text-xs space-y-1.5 ${
              testResult.success
                ? 'border-[var(--ds-bull)]/30 bg-[var(--ds-bull-wash)] text-[var(--ds-bull-strong)]'
                : 'border-[var(--ds-bear)]/30 bg-[var(--ds-bear-wash)] text-[var(--ds-bear-strong)]'
            }`}
          >
            <div className="flex items-center justify-between font-medium">
              <div className="flex items-center gap-2">
                {testResult.success ? (
                  <CheckCircle2 className="w-4 h-4 text-[var(--ds-bull)] shrink-0" />
                ) : (
                  <AlertCircle className="w-4 h-4 text-[var(--ds-bear)] shrink-0" />
                )}
                <span>
                  {testResult.success
                    ? `Gateway verified for ${testResult.provider.toUpperCase()}`
                    : `Gateway verification failed for ${testResult.provider.toUpperCase()}`}
                </span>
              </div>
              <span className="mono text-[11px]">Latency: {testResult.latency_ms}ms</span>
            </div>
            {testResult.quote && (
              <div className="text-[11px] mono muted flex items-center justify-between pt-1">
                <span>Sample Probe: {testResult.quote.symbol}</span>
                <span className="font-semibold text-[var(--ds-ink)]">
                  ₹{testResult.quote.ltp.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </span>
              </div>
            )}
            {testResult.error && (
              <p className="text-[11px] text-[var(--ds-bear-strong)] pt-1 leading-normal">
                {testResult.error}
              </p>
            )}
          </div>
        )}

        {tokenMsg && (
          <div
            className={`card card-pad text-xs flex items-center gap-2 ${
              tokenMsg.type === 'success'
                ? 'border-[var(--ds-bull)]/30 bg-[var(--ds-bull-wash)] text-[var(--ds-bull-strong)]'
                : 'border-[var(--ds-bear)]/30 bg-[var(--ds-bear-wash)] text-[var(--ds-bear-strong)]'
            }`}
          >
            {tokenMsg.type === 'success' ? (
              <CheckCircle2 className="w-4 h-4 shrink-0" />
            ) : (
              <AlertCircle className="w-4 h-4 shrink-0" />
            )}
            <span>{tokenMsg.text}</span>
          </div>
        )}

        <div className="stat-grid grid-cols-2 sm:grid-cols-4">
          <StatTile label="Active provider" value={settings.provider.toUpperCase()} />
          <StatTile
            label="Universe"
            value={settings.apiType.toUpperCase()}
          />
          <StatTile
            label="Auth state"
            value={
              <span className="flex items-center gap-1.5">
                <span
                  className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                    providerMeta.tone === 'emerald'
                      ? 'bg-[var(--ds-bull)]'
                      : providerMeta.tone === 'amber'
                        ? 'bg-[var(--ds-warn)]'
                        : 'bg-[var(--ds-bear)]'
                  }`}
                />
                <span className="truncate">{providerMeta.label}</span>
              </span>
            }
            sub={providerMeta.sub}
          />
          <StatTile
            label="Stream health"
            value={providerMeta.connected ? 'Connected' : 'Offline'}
            tone={providerMeta.connected ? 'positive' : 'default'}
            sub={providerMeta.connected ? 'WebSocket live' : 'Auth required'}
          />
        </div>
      </div>
    </SettingSection>
  );
}
