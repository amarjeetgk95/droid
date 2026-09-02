'use client';

import React, { useState, useEffect } from 'react';
import {
  Radio,
  RefreshCw,
  Key,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  Copy,
  Check,
  Eye,
  EyeOff,
  Activity,
  ExternalLink,
  Info,
  Bitcoin,
  TrendingUp,
  Landmark,
  Globe,
  HelpCircle,
  Lock,
  Layers,
} from 'lucide-react';
import { BrokerSettings, ApiType, BrokerProviderId, AppSettings } from '@/lib/settings';
import { api } from '@/lib/api';
import { useMarketStream } from '@/hooks/useMarketStream';
import { useSettings } from '@/components/settings/SettingsProvider';

interface Props {
  settings: BrokerSettings;
  fullSettings?: AppSettings;
  onChange: (updated: Partial<BrokerSettings>) => void;
  errors?: { path: string; message: string }[];
}

const REDIRECT_BASE = 'https://droid-backend-emeq.onrender.com/api/v1/tokens';

type ProviderCard = {
  id: BrokerProviderId;
  name: string;
  badge: string;
  desc: string;
  apiType: ApiType;
  icon: React.ComponentType<{ className?: string }>;
  portalUrl: string;
};

const INDIAN_PROVIDERS: ProviderCard[] = [
  {
    id: 'fyers',
    name: 'Fyers API v3',
    badge: 'Low Latency',
    desc: 'Official REST & WebSocket Feed',
    apiType: 'indian',
    icon: TrendingUp,
    portalUrl: 'https://myapi.fyers.in/dashboard',
  },
  {
    id: 'flattrade',
    name: 'Flattrade PiConnect',
    badge: 'Zero Brokerage',
    desc: 'WallConnect / PiConnect API & WebSocket',
    apiType: 'indian',
    icon: Landmark,
    portalUrl: 'https://wallconnect.flattrade.in/',
  },
];

const CRYPTO_PROVIDERS: ProviderCard[] = [
  {
    id: 'binance',
    name: 'Binance API',
    badge: 'Crypto & Spot',
    desc: 'Public Spot & Futures',
    apiType: 'crypto',
    icon: Bitcoin,
    portalUrl: 'https://www.binance.com/en/my/settings/api-management',
  },
];

export function BrokerConnectionTab({
  settings,
  fullSettings: propFullSettings,
  onChange,
  errors = [],
}: Props) {
  const [tokenStatus, setTokenStatus] = useState<Record<string, any> | null>(null);
  const [loadingToken, setLoadingToken] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [tokenMsg, setTokenMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [showSecret, setShowSecret] = useState(false);
  const [showAccessToken, setShowAccessToken] = useState(false);
  const [copiedRedirect, setCopiedRedirect] = useState(false);
  const [testing, setTesting] = useState(false);
  const [showSetupGuide, setShowSetupGuide] = useState(false);
  const [testResult, setTestResult] = useState<{
    success: boolean;
    provider: string;
    latency_ms: number;
    token_valid: boolean;
    token_prefix?: string;
    quote?: { symbol: string; ltp: number; high?: number; low?: number; status?: string };
    raw_response?: unknown;
    error?: string | null;
  } | null>(null);

  // Ensure flattrade object is initialized
  const flattradeCreds = settings.flattrade || {
    userId: '',
    apiKey: '',
    apiSecret: '',
    redirectUri: `${REDIRECT_BASE}/flattrade/callback`,
    token: '',
  };

  const handleTestConnection = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      let creds: Record<string, any> = {};
      if (settings.provider === 'fyers') {
        creds = settings.fyers;
      } else if (settings.provider === 'flattrade') {
        creds = flattradeCreds;
      } else {
        creds = (settings as any)[settings.provider] || {};
      }

      const res = await api.testBrokerConnection({
        provider: settings.provider,
        credentials: creds,
      });
      setTestResult(res.data);
    } catch (err: any) {
      setTestResult({
        success: false,
        provider: settings.provider,
        latency_ms: 0,
        token_valid: false,
        error: err?.message || 'Connection test probe failed to reach backend',
      });
    } finally {
      setTesting(false);
    }
  };

  const { streamState, reconnectCount } = useMarketStream();

  let contextFullSettings: any = null;
  try {
    // eslint-disable-next-line react-hooks/rules-of-hooks
    contextFullSettings = (useSettings() as any)?.settings ?? null;
  } catch {
    contextFullSettings = null;
  }
  const fullSettings = propFullSettings || contextFullSettings;

  const visibleProviders = settings.apiType === 'crypto' ? CRYPTO_PROVIDERS : INDIAN_PROVIDERS;

  const getProviderMeta = () => {
    const p = settings.provider;
    if (p === 'binance') {
      const hasCreds = Boolean(settings.binance.apiKey);
      return {
        connected: true,
        label: 'CONNECTED',
        sub: 'Public WebSocket (no auth needed)',
        tone: 'emerald' as const,
        hasCreds,
      };
    }
    const tokenConnected = tokenStatus?.is_token_valid === true;
    if (p === 'fyers') {
      const hasCreds = Boolean(settings.fyers.appId && settings.fyers.secret);
      if (tokenConnected) {
        return {
          connected: true,
          label: 'CONNECTED',
          sub: 'WebSocket • Live Feed Active',
          tone: 'emerald' as const,
          hasCreds,
        };
      }
      return {
        connected: false,
        label: hasCreds
          ? tokenStatus?.state === 'AUTH_EXPIRED'
            ? 'AUTH EXPIRED'
            : 'CREDENTIALS SAVED — AUTH REQUIRED'
          : 'NOT CONFIGURED',
        sub: hasCreds
          ? tokenStatus?.last_error || 'Log in with Fyers to generate daily token'
          : 'Enter App ID + Secret',
        tone: hasCreds
          ? tokenStatus?.state === 'AUTH_EXPIRED'
            ? ('red' as const)
            : ('amber' as const)
          : ('red' as const),
        hasCreds,
      };
    }
    if (p === 'flattrade') {
      const hasCreds = Boolean(flattradeCreds.apiKey && flattradeCreds.apiSecret);
      if (tokenConnected || Boolean(flattradeCreds.token)) {
        return {
          connected: true,
          label: 'CONNECTED',
          sub: 'PiConnect • Live Stream Active',
          tone: 'emerald' as const,
          hasCreds,
        };
      }
      return {
        connected: false,
        label: hasCreds
          ? tokenStatus?.state === 'AUTH_EXPIRED'
            ? 'AUTH EXPIRED'
            : 'CREDENTIALS SAVED — AUTH REQUIRED'
          : 'NOT CONFIGURED',
        sub: hasCreds
          ? tokenStatus?.last_error || 'Log in with Flattrade to generate session token'
          : 'Enter Client Code, API Key + Secret',
        tone: hasCreds
          ? tokenStatus?.state === 'AUTH_EXPIRED'
            ? ('red' as const)
            : ('amber' as const)
          : ('red' as const),
        hasCreds,
      };
    }
    return { connected: false, label: 'UNKNOWN', sub: '', tone: 'red' as const, hasCreds: false };
  };

  const providerMeta = getProviderMeta();

  const fetchTokenStatus = async () => {
    setLoadingToken(true);
    try {
      const res = await api.getTokenStatus();
      const m = getProviderMeta();
      if (!m.hasCreds && settings.provider !== 'binance') {
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
      const m = getProviderMeta();
      if (m.connected) {
        setTokenStatus({
          provider: settings.provider,
          has_token: true,
          is_valid: true,
          expires_at: new Date(Date.now() + 86400000).toISOString(),
          time_to_expiry_hours: 23.5,
          token_type: 'PUBLIC_WS',
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
  }, [settings.provider, settings.apiType, tokenMsg]);

  const handleRefreshToken = async () => {
    setRefreshing(true);
    setTokenMsg(null);
    try {
      let payload: Record<string, unknown> | undefined = undefined;
      if (fullSettings) {
        payload = { app_settings: fullSettings };
      } else {
        payload = { app_settings: { broker: settings } };
      }
      const res = await api.refreshToken(payload);
      if (res.data.refreshed) {
        setTokenMsg({
          type: 'success',
          text: `Token successfully refreshed for ${res.data.provider.toUpperCase()} provider!`,
        });
      } else {
        setTokenMsg({
          type: 'error',
          text:
            res.error ||
            `Token refresh failed for ${res.data.provider.toUpperCase()}. Please authorize via OAuth.`,
        });
      }
      await fetchTokenStatus();
    } catch (err: any) {
      setTokenMsg({ type: 'error', text: err?.message || 'Failed to refresh token' });
    } finally {
      setRefreshing(false);
    }
  };

  const handleCopyRedirect = (provider: 'fyers' | 'flattrade') => {
    const uri =
      provider === 'fyers'
        ? settings.fyers.redirectUri || `${REDIRECT_BASE}/fyers/callback`
        : flattradeCreds.redirectUri || `${REDIRECT_BASE}/flattrade/callback`;
    navigator.clipboard.writeText(uri);
    setCopiedRedirect(true);
    setTimeout(() => setCopiedRedirect(false), 2000);
  };

  const handleApiTypeChange = (next: ApiType) => {
    const defaultProvider: BrokerProviderId = next === 'crypto' ? 'binance' : 'fyers';
    onChange({ apiType: next, provider: defaultProvider });
  };

  const handleProviderSelect = (providerId: BrokerProviderId) => {
    onChange({ provider: providerId });
  };

  const activeProviderCard = [...INDIAN_PROVIDERS, ...CRYPTO_PROVIDERS].find(
    (p) => p.id === settings.provider
  );

  const fyersLoginUrl = settings.fyers.appId
    ? `https://api-t1.fyers.in/api/v3/generate-authcode?client_id=${encodeURIComponent(
        settings.fyers.appId
      )}&redirect_uri=${encodeURIComponent(
        settings.fyers.redirectUri || `${REDIRECT_BASE}/fyers/callback`
      )}&response_type=code&state=droid_fyers`
    : undefined;

  const flattradeLoginUrl = flattradeCreds.apiKey
    ? `https://auth.flattrade.in/?app_key=${encodeURIComponent(flattradeCreds.apiKey)}`
    : undefined;

  return (
    <div className="space-y-6">
      {/* 1. API Type Selector (Indian vs Crypto) */}
      <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
        <div>
          <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
            <Globe className="w-4 h-4 text-primary" />
            Market Universe
          </h3>
          <p className="text-xs text-muted-foreground mt-1">
            Choose the asset universe you want to trade or analyze. Indian markets support FYERS and Flattrade gateways; Crypto uses Binance Spot &amp; Futures.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {[
            {
              id: 'indian' as ApiType,
              name: 'Indian Market (NSE/BSE)',
              desc: 'FYERS API v3 & Flattrade PiConnect (INR)',
              icon: Landmark,
            },
            {
              id: 'crypto' as ApiType,
              name: 'Crypto Market (Binance)',
              desc: 'Spot & Futures pairs on Binance (USDT-quoted)',
              icon: Bitcoin,
            },
          ].map((t) => {
            const isSelected = settings.apiType === t.id;
            const Icon = t.icon;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => handleApiTypeChange(t.id)}
                className={`flex items-center gap-3 text-left p-4 rounded-xl border transition-all cursor-pointer ${
                  isSelected
                    ? 'border-primary bg-primary/10 ring-2 ring-primary/20'
                    : 'border-border bg-card hover:bg-secondary/40'
                }`}
              >
                <div
                  className={`p-2 rounded-lg ${
                    isSelected ? 'bg-primary text-primary-foreground' : 'bg-secondary text-muted-foreground'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold text-foreground">{t.name}</div>
                  <div className="text-[11px] text-muted-foreground">{t.desc}</div>
                </div>
                <span
                  className={`text-[10px] px-2 py-0.5 rounded font-mono font-medium ${
                    isSelected ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'
                  }`}
                >
                  {isSelected ? 'ACTIVE' : 'SELECT'}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* 2. Broker Provider Selection Grid */}
      <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
        <div>
          <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
            <Radio className="w-4 h-4 text-primary" />
            {settings.apiType === 'crypto' ? 'Crypto Gateway' : 'Select Indian Broker Gateway'}
          </h3>
          <p className="text-xs text-muted-foreground mt-1">
            {settings.apiType === 'crypto'
              ? 'Binance provides real-time spot and futures market data.'
              : 'Switch seamlessly between FYERS and Flattrade without restarting the server. Credentials for both are preserved in Render.'}
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {visibleProviders.map((p) => {
            const isSelected = settings.provider === p.id;
            const Icon = p.icon;
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => handleProviderSelect(p.id)}
                className={`flex flex-col text-left p-4 rounded-xl border transition-all cursor-pointer ${
                  isSelected
                    ? 'border-primary bg-primary/10 ring-2 ring-primary/20'
                    : 'border-border bg-card hover:bg-secondary/40'
                }`}
              >
                <div className="flex items-center justify-between w-full">
                  <span className="font-semibold text-sm text-foreground flex items-center gap-2">
                    <Icon className="w-4 h-4 text-primary" />
                    {p.name}
                  </span>
                  <span
                    className={`text-[10px] px-2 py-0.5 rounded font-mono font-medium ${
                      isSelected
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-secondary text-muted-foreground'
                    }`}
                  >
                    {isSelected ? 'ACTIVE' : p.badge}
                  </span>
                </div>
                <span className="text-xs text-muted-foreground mt-2">{p.desc}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* 3. Live Token Status & Diagnostic Card */}
      <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border pb-3">
          <div>
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-emerald-500" />
              Broker Token &amp; Authentication Telemetry
            </h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Live token lifecycle and latency diagnostics managed by backend TokenManager.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleTestConnection}
              disabled={testing || !providerMeta.hasCreds}
              title={!providerMeta.hasCreds ? 'Enter API credentials first' : 'Test broker connection in real time'}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/30 rounded-lg text-xs font-semibold transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Activity className={`w-3.5 h-3.5 ${testing ? 'animate-spin' : ''}`} />
              <span>{testing ? 'Testing Live...' : 'Test Connection'}</span>
            </button>
            <button
              type="button"
              onClick={handleRefreshToken}
              disabled={refreshing || loadingToken || !providerMeta.hasCreds}
              title={!providerMeta.hasCreds ? 'Enter API credentials first' : 'Refresh token'}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-secondary hover:bg-secondary/80 text-foreground rounded-lg text-xs font-semibold transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin text-primary' : ''}`} />
              <span>{refreshing ? 'Refreshing...' : 'Force Refresh'}</span>
            </button>
          </div>
        </div>

        {testResult && (
          <div
            className={`p-4 rounded-xl border text-xs space-y-2 ${
              testResult.success
                ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                : 'bg-destructive/10 border-destructive/30 text-destructive'
            }`}
          >
            <div className="flex items-center justify-between font-semibold">
              <div className="flex items-center gap-2">
                {testResult.success ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                ) : (
                  <AlertCircle className="w-4 h-4 text-destructive" />
                )}
                <span>
                  {testResult.success
                    ? `Connection Verified for ${testResult.provider.toUpperCase()}`
                    : `Connection Failed for ${testResult.provider.toUpperCase()}`}
                </span>
              </div>
              <span className="font-mono text-[11px] bg-background/50 px-2 py-0.5 rounded">
                Latency: {testResult.latency_ms}ms
              </span>
            </div>

            {testResult.quote && (
              <div className="p-2.5 bg-background/40 rounded-lg border border-border/40 font-mono text-[11px] flex items-center justify-between text-foreground">
                <span>
                  Sample Probe: <strong>{testResult.quote.symbol}</strong>
                </span>
                <span className="text-emerald-400 font-bold">
                  ₹{testResult.quote.ltp.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </span>
              </div>
            )}

            {testResult.error && (
              <div className="text-[11px] bg-destructive/20 p-2.5 rounded-lg border border-destructive/30 space-y-1.5">
                <div>
                  <strong>Error Details:</strong> {testResult.error}
                </div>
                {testResult.error.toLowerCase().includes('token') && (
                  <div className="text-amber-300 flex items-center gap-2 pt-1 border-t border-destructive/20">
                    <Info className="w-3.5 h-3.5 shrink-0" />
                    <span>
                      Click <strong>&quot;Login &amp; Authorize&quot;</strong> below to authenticate and generate your session token.
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

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
            <span className="text-muted-foreground text-[11px] block">API Type</span>
            <span className="font-semibold mt-0.5 flex items-center gap-1 text-foreground">
              {settings.apiType === 'crypto' ? (
                <Bitcoin className="w-3 h-3 text-amber-400" />
              ) : (
                <Landmark className="w-3 h-3 text-sky-400" />
              )}
              {settings.apiType.toUpperCase()}
            </span>
          </div>

          <div className="bg-secondary/30 border border-border/50 rounded-lg p-3">
            <span className="text-muted-foreground text-[11px] block">Auth Status</span>
            <span
              className={`font-semibold mt-0.5 flex items-center gap-1 ${
                providerMeta.tone === 'emerald'
                  ? 'text-emerald-400'
                  : providerMeta.tone === 'amber'
                  ? 'text-amber-400'
                  : 'text-destructive'
              }`}
            >
              <span
                className={`w-2 h-2 rounded-full ${
                  providerMeta.tone === 'emerald'
                    ? 'bg-emerald-500 animate-pulse'
                    : providerMeta.tone === 'amber'
                    ? 'bg-amber-500'
                    : 'bg-destructive'
                }`}
              />
              {providerMeta.label}
            </span>
            <span className="text-[10px] text-muted-foreground block mt-0.5 truncate">
              {providerMeta.sub}
            </span>
          </div>

          <div className="bg-secondary/30 border border-border/50 rounded-lg p-3">
            <span className="text-muted-foreground text-[11px] block">Connection</span>
            <span
              className={`font-mono mt-0.5 block font-semibold ${
                providerMeta.connected ? 'text-emerald-400' : 'text-destructive'
              }`}
            >
              {providerMeta.connected ? '● Connected' : '○ Disconnected'}
            </span>
            <span className="text-[10px] text-muted-foreground block">
              {providerMeta.connected ? 'WebSocket • Live' : 'Daily Auth Required'}
            </span>
          </div>
        </div>
      </div>

      {/* 4A. FYERS API v3 Setup & Credentials */}
      {settings.provider === 'fyers' && (
        <div className="space-y-4">
          <div className="bg-card border border-sky-500/20 rounded-xl p-5 space-y-3 shadow-xs">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                <HelpCircle className="w-4 h-4 text-sky-400" />
                How to Configure FYERS API v3 (3 Simple Steps)
              </h3>
              <button
                type="button"
                onClick={() => setShowSetupGuide(!showSetupGuide)}
                className="text-xs text-sky-400 hover:underline font-medium cursor-pointer"
              >
                {showSetupGuide ? 'Hide Guide' : 'Show Instructions'}
              </button>
            </div>

            {showSetupGuide && (
              <div className="text-xs text-muted-foreground space-y-2.5 pt-2 border-t border-border/50">
                <div className="p-3 bg-secondary/40 rounded-lg border border-border/40 space-y-1.5">
                  <div className="font-semibold text-foreground flex items-center gap-1.5">
                    <span className="w-5 h-5 rounded-full bg-sky-500/20 text-sky-400 flex items-center justify-center text-[10px] font-bold">
                      1
                    </span>
                    Create an App in Fyers Developer Portal
                  </div>
                  <p className="pl-6.5 text-[11px] leading-relaxed">
                    Go to{' '}
                    <a
                      href="https://myapi.fyers.in/dashboard"
                      target="_blank"
                      rel="noreferrer"
                      className="text-sky-400 hover:underline font-medium"
                    >
                      myapi.fyers.in/dashboard
                    </a>
                    , click <strong>Create App</strong>, and copy your <strong>App ID</strong> and <strong>Secret Key</strong>.
                  </p>
                </div>

                <div className="p-3 bg-secondary/40 rounded-lg border border-border/40 space-y-1.5">
                  <div className="font-semibold text-foreground flex items-center gap-1.5">
                    <span className="w-5 h-5 rounded-full bg-sky-500/20 text-sky-400 flex items-center justify-center text-[10px] font-bold">
                      2
                    </span>
                    Set the Redirect URL in Fyers Portal
                  </div>
                  <p className="pl-6.5 text-[11px] leading-relaxed">
                    Paste this exact Render callback URL:{' '}
                    <code className="text-sky-300 bg-background/50 px-1 py-0.5 rounded">
                      {settings.fyers.redirectUri || `${REDIRECT_BASE}/fyers/callback`}
                    </code>
                  </p>
                </div>

                <div className="p-3 bg-secondary/40 rounded-lg border border-border/40 space-y-1.5">
                  <div className="font-semibold text-foreground flex items-center gap-1.5">
                    <span className="w-5 h-5 rounded-full bg-sky-500/20 text-sky-400 flex items-center justify-center text-[10px] font-bold">
                      3
                    </span>
                    Save Settings &amp; Perform Daily 2FA Login
                  </div>
                  <p className="pl-6.5 text-[11px] leading-relaxed">
                    Click <strong>&quot;Save Changes&quot;</strong>, then click{' '}
                    <strong>&quot;Login &amp; Authorize with FYERS&quot;</strong>.
                  </p>
                </div>
              </div>
            )}
          </div>

          <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                <Key className="w-4 h-4 text-primary" />
                Fyers API v3 Credentials
              </h3>
              <a
                href="https://myapi.fyers.in/dashboard"
                target="_blank"
                rel="noreferrer"
                className="text-xs text-primary hover:underline flex items-center gap-1 font-medium"
              >
                <span>Fyers Developer Portal</span>
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="text-xs font-semibold text-foreground block mb-1">
                  Fyers App ID (Client ID)
                </label>
                <input
                  type="text"
                  placeholder="e.g. HVMUH3H2LQ-100"
                  value={settings.fyers.appId}
                  onChange={(e) =>
                    onChange({ fyers: { ...settings.fyers, appId: e.target.value.trim() } })
                  }
                  className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-hidden focus:border-primary font-mono"
                />
                <span className="text-[10px] text-muted-foreground mt-1 block">
                  Must end with <code className="text-foreground">-100</code> for API apps.
                </span>
              </div>

              <div>
                <label className="text-xs font-semibold text-foreground block mb-1">Secret Key</label>
                <div className="relative">
                  <input
                    type={showSecret ? 'text' : 'password'}
                    placeholder="Enter your Fyers Secret Key"
                    value={settings.fyers.secret}
                    onChange={(e) =>
                      onChange({ fyers: { ...settings.fyers, secret: e.target.value.trim() } })
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
                  OAuth2 Redirect Callback URL (Render)
                </label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    readOnly
                    value={settings.fyers.redirectUri || `${REDIRECT_BASE}/fyers/callback`}
                    className="flex-1 bg-secondary/30 border border-border rounded-lg px-3 py-2 text-xs text-muted-foreground font-mono"
                  />
                  <button
                    type="button"
                    onClick={() => handleCopyRedirect('fyers')}
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
              </div>

              <div className="sm:col-span-2 pt-2 border-t border-border/40">
                <div className="flex items-center justify-between mb-1">
                  <label className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                    <Lock className="w-3.5 h-3.5 text-muted-foreground" />
                    Manual Access Token (Optional)
                  </label>
                  <span className="text-[10px] text-muted-foreground">For external TOTP scripts</span>
                </div>
                <div className="relative">
                  <input
                    type={showAccessToken ? 'text' : 'password'}
                    placeholder="Paste access_token if generated externally (optional)"
                    value={settings.fyers.accessToken || ''}
                    onChange={(e) =>
                      onChange({ fyers: { ...settings.fyers, accessToken: e.target.value.trim() } })
                    }
                    className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 pr-10 text-xs text-foreground focus:outline-hidden focus:border-primary font-mono"
                  />
                  <button
                    type="button"
                    onClick={() => setShowAccessToken(!showAccessToken)}
                    className="absolute right-2 top-2 text-muted-foreground hover:text-foreground cursor-pointer"
                  >
                    {showAccessToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              <div className="sm:col-span-2 pt-3 border-t border-border/50 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 bg-primary/5 p-4 rounded-xl border border-primary/20">
                <div>
                  <p className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                    <ShieldCheck className="w-4 h-4 text-primary" />
                    Daily OAuth Authorization
                  </p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    Fyers tokens expire daily per SEBI rules. Log in to generate your 24-hour token.
                  </p>
                </div>
                {fyersLoginUrl ? (
                  <a
                    href={fyersLoginUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold rounded-lg shadow-sm transition-all cursor-pointer whitespace-nowrap"
                  >
                    <span>Login &amp; Authorize with FYERS</span>
                    <ExternalLink className="w-3.5 h-3.5" />
                  </a>
                ) : (
                  <div className="text-[11px] text-amber-400 bg-amber-500/10 px-3 py-1.5 rounded-lg border border-amber-500/20">
                    Enter App ID above to enable login
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 4B. FLATTRADE Setup & Credentials */}
      {settings.provider === 'flattrade' && (
        <div className="space-y-4">
          <div className="bg-card border border-emerald-500/20 rounded-xl p-5 space-y-3 shadow-xs">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                <HelpCircle className="w-4 h-4 text-emerald-400" />
                How to Configure Flattrade PiConnect (3 Simple Steps)
              </h3>
              <button
                type="button"
                onClick={() => setShowSetupGuide(!showSetupGuide)}
                className="text-xs text-emerald-400 hover:underline font-medium cursor-pointer"
              >
                {showSetupGuide ? 'Hide Guide' : 'Show Instructions'}
              </button>
            </div>

            {showSetupGuide && (
              <div className="text-xs text-muted-foreground space-y-2.5 pt-2 border-t border-border/50">
                <div className="p-3 bg-secondary/40 rounded-lg border border-border/40 space-y-1.5">
                  <div className="font-semibold text-foreground flex items-center gap-1.5">
                    <span className="w-5 h-5 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center text-[10px] font-bold">
                      1
                    </span>
                    Create API App in Flattrade WallConnect Portal
                  </div>
                  <p className="pl-6.5 text-[11px] leading-relaxed">
                    Log in to{' '}
                    <a
                      href="https://wallconnect.flattrade.in/"
                      target="_blank"
                      rel="noreferrer"
                      className="text-emerald-400 hover:underline font-medium"
                    >
                      wallconnect.flattrade.in
                    </a>
                    , create an app, and copy your <strong>API Key (App Key)</strong> and <strong>API Secret</strong>.
                  </p>
                </div>

                <div className="p-3 bg-secondary/40 rounded-lg border border-border/40 space-y-1.5">
                  <div className="font-semibold text-foreground flex items-center gap-1.5">
                    <span className="w-5 h-5 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center text-[10px] font-bold">
                      2
                    </span>
                    Set the Redirect URL in WallConnect Portal
                  </div>
                  <p className="pl-6.5 text-[11px] leading-relaxed">
                    Paste this exact Render callback URL:{' '}
                    <code className="text-emerald-300 bg-background/50 px-1 py-0.5 rounded">
                      {flattradeCreds.redirectUri || `${REDIRECT_BASE}/flattrade/callback`}
                    </code>
                  </p>
                </div>

                <div className="p-3 bg-secondary/40 rounded-lg border border-border/40 space-y-1.5">
                  <div className="font-semibold text-foreground flex items-center gap-1.5">
                    <span className="w-5 h-5 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center text-[10px] font-bold">
                      3
                    </span>
                    Save Settings &amp; Authenticate Daily
                  </div>
                  <p className="pl-6.5 text-[11px] leading-relaxed">
                    Click <strong>&quot;Save Changes&quot;</strong>, then click{' '}
                    <strong>&quot;Login &amp; Authorize with Flattrade&quot;</strong>.
                  </p>
                </div>
              </div>
            )}
          </div>

          <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                <Key className="w-4 h-4 text-emerald-500" />
                Flattrade WallConnect Credentials
              </h3>
              <a
                href="https://wallconnect.flattrade.in/"
                target="_blank"
                rel="noreferrer"
                className="text-xs text-emerald-400 hover:underline flex items-center gap-1 font-medium"
              >
                <span>Flattrade WallConnect Portal</span>
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="text-xs font-semibold text-foreground block mb-1">
                  User ID / Client Code
                </label>
                <input
                  type="text"
                  placeholder="e.g. FT012345"
                  value={flattradeCreds.userId}
                  onChange={(e) =>
                    onChange({
                      flattrade: { ...flattradeCreds, userId: e.target.value.trim() },
                    })
                  }
                  className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-hidden focus:border-primary font-mono"
                />
                <span className="text-[10px] text-muted-foreground mt-1 block">
                  Your Flattrade trading account client ID.
                </span>
              </div>

              <div>
                <label className="text-xs font-semibold text-foreground block mb-1">
                  API Key (App Key)
                </label>
                <input
                  type="text"
                  placeholder="Enter your Flattrade API Key"
                  value={flattradeCreds.apiKey}
                  onChange={(e) =>
                    onChange({
                      flattrade: { ...flattradeCreds, apiKey: e.target.value.trim() },
                    })
                  }
                  className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-hidden focus:border-primary font-mono"
                />
              </div>

              <div className="sm:col-span-2">
                <label className="text-xs font-semibold text-foreground block mb-1">API Secret</label>
                <div className="relative">
                  <input
                    type={showSecret ? 'text' : 'password'}
                    placeholder="Enter your Flattrade API Secret"
                    value={flattradeCreds.apiSecret}
                    onChange={(e) =>
                      onChange({
                        flattrade: { ...flattradeCreds, apiSecret: e.target.value.trim() },
                      })
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
                  OAuth2 Redirect Callback URL (Render)
                </label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    readOnly
                    value={flattradeCreds.redirectUri || `${REDIRECT_BASE}/flattrade/callback`}
                    className="flex-1 bg-secondary/30 border border-border rounded-lg px-3 py-2 text-xs text-muted-foreground font-mono"
                  />
                  <button
                    type="button"
                    onClick={() => handleCopyRedirect('flattrade')}
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
              </div>

              <div className="sm:col-span-2 pt-2 border-t border-border/40">
                <div className="flex items-center justify-between mb-1">
                  <label className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                    <Lock className="w-3.5 h-3.5 text-muted-foreground" />
                    Manual Session Token (Optional)
                  </label>
                  <span className="text-[10px] text-muted-foreground">For pre-authenticated sessions</span>
                </div>
                <div className="relative">
                  <input
                    type={showAccessToken ? 'text' : 'password'}
                    placeholder="Paste session token if generated externally"
                    value={flattradeCreds.token || ''}
                    onChange={(e) =>
                      onChange({
                        flattrade: { ...flattradeCreds, token: e.target.value.trim() },
                      })
                    }
                    className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 pr-10 text-xs text-foreground focus:outline-hidden focus:border-primary font-mono"
                  />
                  <button
                    type="button"
                    onClick={() => setShowAccessToken(!showAccessToken)}
                    className="absolute right-2 top-2 text-muted-foreground hover:text-foreground cursor-pointer"
                  >
                    {showAccessToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              <div className="sm:col-span-2 pt-3 border-t border-border/50 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 bg-emerald-500/5 p-4 rounded-xl border border-emerald-500/20">
                <div>
                  <p className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                    <ShieldCheck className="w-4 h-4 text-emerald-400" />
                    Daily OAuth Authorization
                  </p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    Log in with Flattrade 2FA to generate your daily PiConnect session token.
                  </p>
                </div>
                {flattradeLoginUrl ? (
                  <a
                    href={flattradeLoginUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-foreground text-xs font-semibold rounded-lg shadow-sm transition-all cursor-pointer whitespace-nowrap"
                  >
                    <span>Login &amp; Authorize with Flattrade</span>
                    <ExternalLink className="w-3.5 h-3.5" />
                  </a>
                ) : (
                  <div className="text-[11px] text-amber-400 bg-amber-500/10 px-3 py-1.5 rounded-lg border border-amber-500/20">
                    Enter API Key above to enable login
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 5. Binance Crypto Credentials */}
      {settings.provider === 'binance' && (
        <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <Key className="w-4 h-4 text-primary" />
              Binance Spot &amp; Futures API Configuration
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
              <strong>Public Market Data is Free &amp; Active:</strong> Binance real-time Spot &amp; Futures tickers, Order Books, Candlesticks, and Funding Rates stream directly with zero authentication required. Optional API keys enable private account queries and paper execution.
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
                value={settings.binance.apiKey}
                onChange={(e) =>
                  onChange({ binance: { ...settings.binance, apiKey: e.target.value.trim() } })
                }
                className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-hidden focus:border-primary font-mono"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-foreground block mb-1">Binance API Secret</label>
              <div className="relative">
                <input
                  type={showSecret ? 'text' : 'password'}
                  placeholder="Enter your Binance API Secret"
                  value={settings.binance.apiSecret}
                  onChange={(e) =>
                    onChange({ binance: { ...settings.binance, apiSecret: e.target.value.trim() } })
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
          </div>
        </div>
      )}

      {/* 6. Live Stream Health */}
      <div className="bg-card border border-border rounded-xl p-5 shadow-xs">
        <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
          <Activity className="w-4 h-4 text-primary" />
          Live Market Stream Status
        </h3>
        <div className="flex items-center gap-3 mt-3 text-xs">
          <span
            className={`w-2.5 h-2.5 rounded-full ${
              providerMeta.connected ? 'bg-emerald-500 animate-pulse' : 'bg-destructive'
            }`}
          />
          <span
            className={`font-mono font-bold ${
              providerMeta.connected ? 'text-emerald-400' : 'text-destructive'
            }`}
          >
            {providerMeta.connected ? 'CONNECTED' : 'DISCONNECTED'}
          </span>
          <span className="text-muted-foreground">
            · {providerMeta.connected ? `${reconnectCount} reconnects` : providerMeta.sub}
          </span>
          <span className="ml-auto text-[11px] text-muted-foreground">
            {activeProviderCard ? activeProviderCard.name : '—'} · {settings.apiType.toUpperCase()}
          </span>
        </div>
      </div>
    </div>
  );
}
