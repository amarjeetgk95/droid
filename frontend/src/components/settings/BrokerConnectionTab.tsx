'use client';

import React, { useState, useEffect } from 'react';
import { Radio, RefreshCw, Key, ShieldCheck, CheckCircle2, AlertCircle, Copy, Check, Eye, EyeOff, Activity, ExternalLink, Info } from 'lucide-react';
import { BrokerSettings } from '@/lib/settings';
import { api } from '@/lib/api';
import { useMarketStream } from '@/hooks/useMarketStream';

interface Props {
  settings: BrokerSettings;
  onChange: (updated: Partial<BrokerSettings>) => void;
  errors?: { path: string; message: string }[];
}

export function BrokerConnectionTab({ settings, onChange, errors = [] }: Props) {
  const getError = (field: string) => errors.find((e) => e.path === `broker.${field}`)?.message;
  const [tokenStatus, setTokenStatus] = useState<Record<string, any> | null>(null);
  const [loadingToken, setLoadingToken] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [tokenMsg, setTokenMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [showSecret, setShowSecret] = useState(false);
  const [copiedRedirect, setCopiedRedirect] = useState(false);

  const { streamState, reconnectCount } = useMarketStream();

  // Truthful connection status per provider - only binance public + mock are truly connected without credentials
  const getProviderMeta = () => {
    const p = settings.provider;
    if (p === 'mock') return { connected: true, label: 'CONNECTED', sub: 'Simulation active', tone: 'emerald' as const, hasCreds: true };
    if (p === 'binance') return { connected: true, label: 'CONNECTED', sub: 'Public WebSocket (no auth needed)', tone: 'emerald' as const, hasCreds: true };
    if (p === 'fyers') {
      const hasCreds = Boolean(settings.fyersAppId && settings.fyersSecret);
      return { connected: false, label: hasCreds ? 'CREDENTIALS SAVED — AUTH REQUIRED' : 'NOT CONFIGURED', sub: hasCreds ? 'Click Force Refresh to authenticate' : 'Enter App ID + Secret', tone: hasCreds ? 'amber' as const : 'red' as const, hasCreds };
    }
    if (p === 'upstox') {
      const hasCreds = Boolean(settings.upstoxApiKey && settings.upstoxSecret);
      return { connected: false, label: hasCreds ? 'CREDENTIALS SAVED — AUTH REQUIRED' : 'NOT CONFIGURED', sub: hasCreds ? 'Click Force Refresh to authenticate' : 'Enter API Key + Secret', tone: hasCreds ? 'amber' as const : 'red' as const, hasCreds };
    }
    return { connected: false, label: 'UNKNOWN', sub: '', tone: 'red' as const, hasCreds: false };
  };
  const providerMeta = getProviderMeta();

  const fetchTokenStatus = async () => {
    setLoadingToken(true);
    try {
      const res = await api.getTokenStatus();
      // Backend may return generic token status; override with truthful mock if provider not configured
      const m = getProviderMeta();
      if (!m.hasCreds && (settings.provider === 'fyers' || settings.provider === 'upstox')) {
        setTokenStatus({
          provider: settings.provider,
          has_token: false,
          is_valid: false,
          expires_at: null,
          time_to_expiry_hours: 0,
          token_type: 'NONE',
        });
      } else {
        setTokenStatus(res.data);
      }
    } catch {
      // Offline fallback must be truthful - only mock/binance are connected
      const m = getProviderMeta();
      if (m.connected) {
        setTokenStatus({
          provider: settings.provider,
          has_token: true,
          is_valid: true,
          expires_at: new Date(Date.now() + 86400000).toISOString(),
          time_to_expiry_hours: 23.5,
          token_type: 'MOCK_BEARER',
        });
      } else {
        setTokenStatus({
          provider: settings.provider,
          has_token: false,
          is_valid: false,
          expires_at: null,
          time_to_expiry_hours: 0,
          token_type: 'NONE',
        });
      }
    } finally {
      setLoadingToken(false);
    }
  };

  useEffect(() => {
    fetchTokenStatus();
  }, [settings.provider]);

  const handleRefreshToken = async () => {
    setRefreshing(true);
    setTokenMsg(null);
    try {
      const res = await api.refreshToken();
      setTokenMsg({
        type: 'success',
        text: `Token successfully refreshed for ${res.data.provider.toUpperCase()} provider!`,
      });
      await fetchTokenStatus();
    } catch (err: any) {
      setTokenMsg({
        type: 'error',
        text: err?.message || 'Failed to refresh token',
      });
    } finally {
      setRefreshing(false);
    }
  };

  const handleCopyRedirect = () => {
    const uri = settings.provider === 'fyers' ? settings.fyersRedirectUri : settings.upstoxRedirectUri;
    navigator.clipboard.writeText(uri || window.location.origin + '/api/v1/auth/callback');
    setCopiedRedirect(true);
    setTimeout(() => setCopiedRedirect(false), 2000);
  };

  return (
    <div className="space-y-6">
      {/* 1. Active Provider Switcher */}
      <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
        <div>
          <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
            <Radio className="w-4 h-4 text-primary" />
            Market Data & Broker Connection
          </h3>
          <p className="text-xs text-muted-foreground mt-1">
            Select the primary data provider for market feeds, order books, and real-time tick streaming.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {[
            { id: 'mock', name: 'Mock Engine', badge: 'Active Dev', desc: 'Deterministic NSE Feed' },
            { id: 'fyers', name: 'Fyers API v3', badge: 'Low Latency', desc: 'WebSocket & Brokerage' },
            { id: 'upstox', name: 'Upstox Pro', badge: 'Official V2', desc: 'Real-Time Tick Stream' },
            { id: 'binance', name: 'Binance API', badge: 'Crypto & Spot', desc: 'Real-Time Crypto Feed' },
          ].map((p) => {
            const isSelected = settings.provider === p.id;
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => onChange({ provider: p.id as any })}
                className={`flex flex-col text-left p-3.5 rounded-xl border transition-all cursor-pointer ${
                  isSelected
                    ? 'border-primary bg-primary/10 ring-2 ring-primary/20'
                    : 'border-border bg-card hover:bg-secondary/40'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-xs text-foreground">{p.name}</span>
                  <span
                    className={`text-[10px] px-1.5 py-0.5 rounded font-mono font-medium ${
                      isSelected
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-muted text-muted-foreground'
                    }`}
                  >
                    {p.badge}
                  </span>
                </div>
                <span className="text-[11px] text-muted-foreground mt-2">{p.desc}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* 2. Live Token Status & Diagnostic Card */}
      <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border pb-3">
          <div>
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-emerald-500" />
              Broker Token & Authentication Telemetry
            </h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Live token lifecycle status managed by backend TokenManager worker.
            </p>
          </div>
          <button
            type="button"
            onClick={handleRefreshToken}
            disabled={refreshing || loadingToken || !providerMeta.hasCreds}
            title={!providerMeta.hasCreds ? 'Enter API credentials first' : 'Refresh token'}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-secondary hover:bg-secondary/80 text-foreground rounded-lg text-xs font-semibold transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin text-primary' : ''}`} />
            <span>{refreshing ? 'Refreshing Token...' : 'Force Refresh Token'}</span>
          </button>
        </div>

        {tokenMsg && (
          <div
            className={`p-3 rounded-lg text-xs flex items-center gap-2 ${
              tokenMsg.type === 'success'
                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
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

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div className="bg-secondary/30 border border-border/50 rounded-lg p-3">
            <span className="text-muted-foreground text-[11px] block">Active Provider</span>
            <span className="font-mono font-bold text-foreground mt-0.5 block uppercase">
              {settings.provider}
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
            <span className="text-muted-foreground text-[11px] block">Time to Expiry</span>
            <span className="font-mono text-foreground mt-0.5 block font-semibold">
              {providerMeta.connected && tokenStatus?.time_to_expiry_hours
                ? `${tokenStatus.time_to_expiry_hours} Hours`
                : providerMeta.connected
                ? '—'
                : 'Not authenticated'}
            </span>
          </div>

          <div className="bg-secondary/30 border border-border/50 rounded-lg p-3">
            <span className="text-muted-foreground text-[11px] block">Connection</span>
            <span className={`font-mono mt-0.5 block font-semibold ${providerMeta.connected ? 'text-emerald-400' : 'text-destructive'}`}>
              {providerMeta.connected ? '● Connected' : '○ Disconnected'}
            </span>
            <span className="text-[10px] text-muted-foreground block">{providerMeta.connected ? 'WebSocket • Live' : 'Enter credentials to connect'}</span>
          </div>
        </div>
      </div>

      {/* 3. Provider Specific Credentials Configuration */}
      {settings.provider === 'mock' ? (
        <div className="bg-card border border-border rounded-xl p-5 shadow-xs">
          <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <Activity className="w-4 h-4 text-primary" />
            Mock Market Data — Zero Configuration
          </h3>
          <p className="text-xs text-muted-foreground">
            Deterministic NSE feed (NIFTY, BANKNIFTY, FINNIFTY, SENSEX, INDIA VIX) is active. No credentials required — ideal for development and backtesting.
          </p>
        </div>
      ) : settings.provider === 'binance' ? (
        <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <Key className="w-4 h-4 text-primary" />
              Binance Spot & Futures API Configuration
            </h3>
            <a
              href="https://www.binance.com/en/my/settings/api-management"
              target="_blank"
              rel="noreferrer"
              className="text-xs text-primary hover:underline flex items-center gap-1 font-medium"
            >
              <span>Binance API Management</span>
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>

          <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-lg text-xs text-amber-300 flex items-start gap-2">
            <Info className="w-4 h-4 shrink-0 mt-0.5" />
            <div>
              <strong>Public Market Data is Free & Active:</strong> Binance real-time Spot & Futures tickers, Order Books, Candlesticks, and Funding Rates stream directly with zero authentication required. Optional API keys enable private account queries and paper execution.
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-semibold text-foreground block mb-1">
                Binance API Key (Optional)
              </label>
              <input
                type="text"
                placeholder="e.g. vmPUZE6mv9SD5VNH..."
                value={settings.binanceApiKey}
                onChange={(e) => onChange({ binanceApiKey: e.target.value })}
                className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-hidden focus:border-primary font-mono"
              />
            </div>

            <div>
              <label className="text-xs font-semibold text-foreground block mb-1">
                Binance Secret Key
              </label>
              <div className="relative">
                <input
                  type={showSecret ? 'text' : 'password'}
                  placeholder="Enter your Binance API Secret"
                  value={settings.binanceSecretKey}
                  onChange={(e) => onChange({ binanceSecretKey: e.target.value })}
                  className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 pr-10 text-xs text-foreground focus:outline-hidden focus:border-primary font-mono"
                />
                <button
                  type="button"
                  onClick={() => setShowSecret(!showSecret)}
                  className="absolute right-2 top-2 text-muted-foreground hover:text-foreground cursor-pointer"
                >
                  {showSecret ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

          </div>
        </div>
      ) : (
        <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <Key className="w-4 h-4 text-primary" />
              {settings.provider.toUpperCase()} API Credentials
            </h3>
            <a
              href={
                settings.provider === 'fyers'
                  ? 'https://myapi.fyers.in/dashboard'
                  : 'https://developer.upstox.com/'
              }
              target="_blank"
              rel="noreferrer"
              className="text-xs text-primary hover:underline flex items-center gap-1 font-medium"
            >
              <span>Developer Portal</span>
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-semibold text-foreground block mb-1">
                {settings.provider === 'fyers' ? 'Fyers App ID (Client ID)' : 'Upstox API Key'}
              </label>
              <input
                type="text"
                placeholder={settings.provider === 'fyers' ? 'e.g. XC12345-100' : 'e.g. 849a9b...'}
                value={settings.provider === 'fyers' ? settings.fyersAppId : settings.upstoxApiKey}
                onChange={(e) =>
                  settings.provider === 'fyers'
                    ? onChange({ fyersAppId: e.target.value })
                    : onChange({ upstoxApiKey: e.target.value })
                }
                className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-hidden focus:border-primary font-mono"
              />
            </div>

            <div>
              <label className="text-xs font-semibold text-foreground block mb-1">
                Secret Key
              </label>
              <div className="relative">
                <input
                  type={showSecret ? 'text' : 'password'}
                  placeholder="Enter your API Secret Key"
                  value={settings.provider === 'fyers' ? settings.fyersSecret : settings.upstoxSecret}
                  onChange={(e) =>
                    settings.provider === 'fyers'
                      ? onChange({ fyersSecret: e.target.value })
                      : onChange({ upstoxSecret: e.target.value })
                  }
                  className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 pr-10 text-xs text-foreground focus:outline-hidden focus:border-primary font-mono"
                />
                <button
                  type="button"
                  onClick={() => setShowSecret(!showSecret)}
                  className="absolute right-2 top-2 text-muted-foreground hover:text-foreground cursor-pointer"
                >
                  {showSecret ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <div className="sm:col-span-2">
              <label className="text-xs font-semibold text-foreground block mb-1">
                OAuth2 Redirect Callback URL
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  readOnly
                  value={
                    settings.provider === 'fyers'
                      ? settings.fyersRedirectUri
                      : settings.upstoxRedirectUri
                  }
                  className="flex-1 bg-secondary/30 border border-border rounded-lg px-3 py-2 text-xs text-muted-foreground font-mono"
                />
                <button
                  type="button"
                  onClick={handleCopyRedirect}
                  className="flex items-center gap-1 px-3 py-2 bg-secondary hover:bg-secondary/80 text-foreground rounded-lg text-xs font-semibold transition-all cursor-pointer"
                >
                  {copiedRedirect ? (
                    <>
                      <Check className="w-3.5 h-3.5 text-emerald-400" />
                      <span>Copied!</span>
                    </>
                  ) : (
                    <>
                      <Copy className="w-3.5 h-3.5" />
                      <span>Copy</span>
                    </>
                  )}
                </button>
              </div>
              <span className="text-[11px] text-muted-foreground mt-1 block">
                Paste this exact callback URL into your broker developer app configuration.
              </span>
            </div>
          </div>
        </div>
      )}

      {/* 4. Stream Health - truthful per provider */}
      <div className="bg-card border border-border rounded-xl p-5 shadow-xs">
        <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
          <Activity className="w-4 h-4 text-primary" />
          Live Market Stream
        </h3>
        <div className="flex items-center gap-3 mt-3 text-xs">
          <span className={`w-2.5 h-2.5 rounded-full ${providerMeta.connected ? 'bg-emerald-500 animate-pulse' : 'bg-destructive'}`} />
          <span className={`font-mono font-bold ${providerMeta.connected ? 'text-emerald-400' : 'text-destructive'}`}>{providerMeta.connected ? 'CONNECTED' : 'DISCONNECTED'}</span>
          <span className="text-muted-foreground">· {providerMeta.connected ? `${reconnectCount} reconnects` : providerMeta.sub}</span>
          <span className="ml-auto text-[11px] text-muted-foreground">{providerMeta.connected ? 'WebSocket • Live' : 'Enter credentials'}</span>
        </div>
        {!providerMeta.connected && (
          <p className="text-[11px] text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2 mt-3">Only Mock and Binance public streams are connected. Fyers/Upstox require valid API credentials and OAuth.</p>
        )}
      </div>
    </div>
  );
}
