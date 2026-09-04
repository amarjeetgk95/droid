'use client';

import React, { useEffect, useState } from 'react';
import {
  Activity,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Landmark,
  Bitcoin,
} from 'lucide-react';
import type { BrokerSettings, AppSettings } from '@/lib/settings';
import { api } from '@/lib/api';
import { useSettings } from '@/components/settings/SettingsProvider';
import { getProviderMeta } from './constants';
import { SettingSection } from '../ui/SettingPrimitives';

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
          : settings.provider === 'flattrade'
            ? (settings as unknown as { flattrade: Record<string, unknown> }).flattrade
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
      title="Session Telemetry &amp; Gateway Health"
      description="Real-time token lifecycle and gateway heartbeat monitored by Render TokenManager."
      icon={Activity}
      action={
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleTestConnection}
            disabled={testing}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-secondary hover:bg-secondary/80 text-foreground border border-border/60 rounded-md text-xs font-medium transition-colors cursor-pointer disabled:opacity-50"
          >
            <Activity className={`w-3.5 h-3.5 text-muted-foreground ${testing ? 'animate-spin' : ''}`} />
            <span>{testing ? 'Probing...' : 'Test Probe'}</span>
          </button>
          <button
            type="button"
            onClick={handleRefreshToken}
            disabled={refreshing || loadingToken}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-secondary hover:bg-secondary/80 text-foreground border border-border/60 rounded-md text-xs font-medium transition-colors cursor-pointer disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-muted-foreground ${refreshing ? 'animate-spin' : ''}`} />
            <span>{refreshing ? 'Refreshing...' : 'Refresh Token'}</span>
          </button>
        </div>
      }
    >
      <div className="p-5 space-y-4">
        {testResult && (
          <div
            className={`p-3.5 rounded-lg border text-xs space-y-1.5 ${
              testResult.success
                ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-600'
                : 'bg-destructive/10 border-destructive/20 text-destructive'
            }`}
          >
            <div className="flex items-center justify-between font-medium">
              <div className="flex items-center gap-2">
                {testResult.success ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                ) : (
                  <AlertCircle className="w-4 h-4 text-destructive shrink-0" />
                )}
                <span>
                  {testResult.success
                    ? `Gateway connected for ${testResult.provider.toUpperCase()}`
                    : `Connection failed for ${testResult.provider.toUpperCase()}`}
                </span>
              </div>
              <span className="font-mono text-[11px]">Latency: {testResult.latency_ms}ms</span>
            </div>
            {testResult.quote && (
              <div className="text-[11px] font-mono text-muted-foreground flex items-center justify-between pt-1">
                <span>Sample Probe: {testResult.quote.symbol}</span>
                <span className="font-semibold text-foreground">
                  ₹{testResult.quote.ltp.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </span>
              </div>
            )}
            {testResult.error && (
              <p className="text-[11px] text-destructive/90 pt-1 leading-normal">
                {testResult.error}
              </p>
            )}
          </div>
        )}

        {tokenMsg && (
          <div
            className={`p-3 rounded-lg text-xs flex items-center gap-2 ${
              tokenMsg.type === 'success'
                ? 'bg-emerald-500/10 text-emerald-600 border border-emerald-500/20'
                : 'bg-destructive/10 text-destructive border border-destructive/20'
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

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="bg-secondary/30 border border-border/40 rounded-lg p-3">
            <span className="text-muted-foreground text-[10px] uppercase font-medium tracking-wide block">
              Active Provider
            </span>
            <span className="font-mono font-bold text-sm text-foreground mt-1 block uppercase">
              {settings.provider}
            </span>
          </div>

          <div className="bg-secondary/30 border border-border/40 rounded-lg p-3">
            <span className="text-muted-foreground text-[10px] uppercase font-medium tracking-wide block">
              Universe
            </span>
            <span className="font-semibold text-sm mt-1 flex items-center gap-1.5 text-foreground">
              {settings.apiType === 'crypto' ? (
                <Bitcoin className="w-3.5 h-3.5 text-muted-foreground" />
              ) : (
                <Landmark className="w-3.5 h-3.5 text-muted-foreground" />
              )}
              {settings.apiType.toUpperCase()}
            </span>
          </div>

          <div className="bg-secondary/30 border border-border/40 rounded-lg p-3">
            <span className="text-muted-foreground text-[10px] uppercase font-medium tracking-wide block">
              Auth State
            </span>
            <div className="flex items-center gap-1.5 mt-1">
              <span
                className={`w-2 h-2 rounded-full ${
                  providerMeta.tone === 'emerald'
                    ? 'bg-emerald-500'
                    : providerMeta.tone === 'amber'
                      ? 'bg-amber-500'
                      : 'bg-destructive'
                }`}
              />
              <span className="text-xs font-semibold text-foreground truncate">
                {providerMeta.label}
              </span>
            </div>
            <span className="text-[10px] text-muted-foreground block truncate mt-0.5">
              {providerMeta.sub}
            </span>
          </div>

          <div className="bg-secondary/30 border border-border/40 rounded-lg p-3">
            <span className="text-muted-foreground text-[10px] uppercase font-medium tracking-wide block">
              Stream Health
            </span>
            <span
              className={`font-mono text-xs font-semibold mt-1 block ${
                providerMeta.connected ? 'text-emerald-600' : 'text-muted-foreground'
              }`}
            >
              {providerMeta.connected ? 'Connected' : 'Offline'}
            </span>
            <span className="text-[10px] text-muted-foreground block truncate mt-0.5">
              {providerMeta.connected ? 'WebSocket Stream Live' : 'Auth Required'}
            </span>
          </div>
        </div>
      </div>
    </SettingSection>
  );
}
