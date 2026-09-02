'use client';
import React, { useEffect, useState } from 'react';
import { ShieldCheck, CheckCircle2, AlertCircle, Activity, RefreshCw, Info, Landmark, Bitcoin } from 'lucide-react';
import type { BrokerSettings, AppSettings } from '@/lib/settings';
import { api } from '@/lib/api';
import { useSettings } from '@/components/settings/SettingsProvider';
import { getProviderMeta } from './constants';

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

  // Try to get full settings from context if not passed as prop
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
        setTokenMsg({ type: 'success', text: `Token successfully refreshed for ${(res.data as unknown as { provider: string }).provider.toUpperCase()} provider!` });
      } else {
        setTokenMsg({ type: 'error', text: (res as unknown as { error?: string }).error || `Token refresh failed.` });
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
    <div className="bg-card border border-border rounded-xl p-4 space-y-3 shadow-sm">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border pb-3">
        <div>
          <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-emerald-500" />
            Live Telemetry &amp; Connection Status
          </h3>
          <p className="text-xs text-muted-foreground mt-0.5">Monitored by Render backend TokenManager.</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleTestConnection}
            disabled={testing}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/30 rounded-lg text-xs font-semibold transition-all cursor-pointer disabled:opacity-50"
          >
            <Activity className={`w-3.5 h-3.5 ${testing ? 'animate-spin' : ''}`} />
            <span>{testing ? 'Testing Live...' : 'Test Connection'}</span>
          </button>
          <button
            type="button"
            onClick={handleRefreshToken}
            disabled={refreshing || loadingToken}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-secondary hover:bg-secondary/80 text-foreground rounded-lg text-xs font-semibold transition-all cursor-pointer disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin text-primary' : ''}`} />
            <span>{refreshing ? 'Refreshing...' : 'Force Refresh'}</span>
          </button>
        </div>
      </div>

      {testResult && (
        <div className={`p-4 rounded-xl border text-xs space-y-2 ${testResult.success ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300' : 'bg-destructive/10 border-destructive/30 text-destructive'}`}>
          <div className="flex items-center justify-between font-semibold">
            <div className="flex items-center gap-2">
              {testResult.success ? <CheckCircle2 className="w-4 h-4 text-emerald-400" /> : <AlertCircle className="w-4 h-4 text-destructive" />}
              <span>{testResult.success ? `Connection Verified for ${testResult.provider.toUpperCase()}` : `Connection Failed for ${testResult.provider.toUpperCase()}`}</span>
            </div>
            <span className="font-mono text-[11px] bg-background/50 px-2 py-0.5 rounded">Latency: {testResult.latency_ms}ms</span>
          </div>
          {testResult.quote && (
            <div className="p-2.5 bg-background/40 rounded-lg border border-border/40 font-mono text-[11px] flex items-center justify-between text-foreground">
              <span>Sample Probe: <strong>{testResult.quote.symbol}</strong></span>
              <span className="text-emerald-400 font-bold">₹{testResult.quote.ltp.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
            </div>
          )}
          {testResult.error && (
            <div className="text-[11px] bg-destructive/20 p-2.5 rounded-lg border border-destructive/30 space-y-1.5">
              <div><strong>Error Details:</strong> {testResult.error}</div>
              {testResult.error.toLowerCase().includes('token') && (
                <div className="text-amber-300 flex items-center gap-2 pt-1 border-t border-destructive/20">
                  <Info className="w-3.5 h-3.5 shrink-0" />
                  <span>Click <strong>&quot;Login &amp; Authorize&quot;</strong> above to generate and activate your daily session.</span>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {tokenMsg && (
        <div className={`p-3 rounded-lg text-xs flex items-center gap-2 ${tokenMsg.type === 'success' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-destructive/10 text-destructive border border-destructive/20'}`}>
          {tokenMsg.type === 'success' ? <CheckCircle2 className="w-4 h-4 shrink-0" /> : <AlertCircle className="w-4 h-4 shrink-0" />}
          <span>{tokenMsg.text}</span>
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
        <div className="bg-secondary/30 border border-border/50 rounded-lg p-3">
          <span className="text-muted-foreground text-[11px] block">Active Provider</span>
          <span className="font-mono font-bold text-foreground mt-0.5 block uppercase">{settings.provider}</span>
        </div>
        <div className="bg-secondary/30 border border-border/50 rounded-lg p-3">
          <span className="text-muted-foreground text-[11px] block">API Universe</span>
          <span className="font-semibold mt-0.5 flex items-center gap-1 text-foreground">
            {settings.apiType === 'crypto' ? <Bitcoin className="w-3 h-3 text-amber-400" /> : <Landmark className="w-3 h-3 text-sky-400" />}
            {settings.apiType.toUpperCase()}
          </span>
        </div>
        <div className="bg-secondary/30 border border-border/50 rounded-lg p-3">
          <span className="text-muted-foreground text-[11px] block">Auth Status</span>
          <span className={`font-semibold mt-0.5 flex items-center gap-1 ${providerMeta.tone === 'emerald' ? 'text-emerald-400' : providerMeta.tone === 'amber' ? 'text-amber-400' : 'text-destructive'}`}>
            <span className={`w-2 h-2 rounded-full ${providerMeta.tone === 'emerald' ? 'bg-emerald-500 animate-pulse' : providerMeta.tone === 'amber' ? 'bg-amber-500' : 'bg-destructive'}`} />
            {providerMeta.label}
          </span>
          <span className="text-[10px] text-muted-foreground block mt-0.5 truncate">{providerMeta.sub}</span>
        </div>
        <div className="bg-secondary/30 border border-border/50 rounded-lg p-3">
          <span className="text-muted-foreground text-[11px] block">Connection</span>
          <span className={`font-mono mt-0.5 block font-semibold ${providerMeta.connected ? 'text-emerald-400' : 'text-destructive'}`}>
            {providerMeta.connected ? '● Connected' : '○ Disconnected'}
          </span>
          <span className="text-[10px] text-muted-foreground block">{providerMeta.connected ? 'WebSocket • Live' : 'Daily Auth Required'}</span>
        </div>
      </div>
    </div>
  );
}
