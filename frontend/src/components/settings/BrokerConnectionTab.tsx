'use client';

import React, { useState, useEffect } from 'react';
import {
  Radio,
  RefreshCw,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  Copy,
  Check,
  Activity,
  ExternalLink,
  Info,
  Bitcoin,
  TrendingUp,
  Landmark,
  Globe,
  HelpCircle,
  Server,
  Lock,
  ChevronDown,
  ChevronUp,
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

const BACKEND_BASE = 'https://droid-backend-emeq.onrender.com';
const REDIRECT_BASE = `${BACKEND_BASE}/api/v1/tokens`;

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
    desc: 'Official REST & WebSocket Gateway',
    apiType: 'indian',
    icon: TrendingUp,
    portalUrl: 'https://myapi.fyers.in/dashboard',
  },
  {
    id: 'flattrade',
    name: 'Flattrade PiConnect',
    badge: 'Zero Brokerage',
    desc: 'WallConnect API & Realtime Feed',
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
    desc: 'Public Spot & Futures Gateway',
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
  const [copiedRedirect, setCopiedRedirect] = useState(false);
  const [testing, setTesting] = useState(false);
  const [showSetupGuide, setShowSetupGuide] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showSecret, setShowSecret] = useState(false);
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
      return {
        connected: true,
        label: 'CONNECTED',
        sub: 'Public WebSocket (Zero auth needed)',
        tone: 'emerald' as const,
        hasCreds: true,
      };
    }
    const tokenConnected = tokenStatus?.is_token_valid === true;
    if (p === 'fyers') {
      if (tokenConnected) {
        return {
          connected: true,
          label: 'CONNECTED',
          sub: 'WebSocket • Live Stream Active',
          tone: 'emerald' as const,
          hasCreds: true,
        };
      }
      return {
        connected: false,
        label: tokenStatus?.state === 'AUTH_EXPIRED'
          ? 'DAILY AUTH EXPIRED'
          : 'RENDER MANAGED — DAILY AUTH REQUIRED',
        sub: 'Click below to authorize your daily session',
        tone: tokenStatus?.state === 'AUTH_EXPIRED' ? ('red' as const) : ('amber' as const),
        hasCreds: true,
      };
    }
    if (p === 'flattrade') {
      if (tokenConnected || Boolean(flattradeCreds.token)) {
        return {
          connected: true,
          label: 'CONNECTED',
          sub: 'PiConnect • Live Stream Active',
          tone: 'emerald' as const,
          hasCreds: true,
        };
      }
      return {
        connected: false,
        label: tokenStatus?.state === 'AUTH_EXPIRED'
          ? 'DAILY AUTH EXPIRED'
          : 'RENDER MANAGED — DAILY AUTH REQUIRED',
        sub: 'Click below to authorize your daily session',
        tone: tokenStatus?.state === 'AUTH_EXPIRED' ? ('red' as const) : ('amber' as const),
        hasCreds: true,
      };
    }
    return { connected: false, label: 'UNKNOWN', sub: '', tone: 'red' as const, hasCreds: false };
  };

  const providerMeta = getProviderMeta();

  const fetchTokenStatus = async () => {
    setLoadingToken(true);
    try {
      const res = await api.getTokenStatus();
      setTokenStatus(res.data);
    } catch {
      setTokenStatus({
        provider: settings.provider,
        has_token: false,
        is_valid: false,
        expires_at: null,
        time_to_expiry_hours: 0,
        token_type: 'NONE',
      });
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
    const uri = `${REDIRECT_BASE}/${provider}/callback`;
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

  // Server-side direct OAuth endpoints hosted on Render
  const fyersServerLoginUrl = `${REDIRECT_BASE}/fyers/login`;
  const flattradeServerLoginUrl = `${REDIRECT_BASE}/flattrade/login`;

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
            Choose your market universe. Indian markets operate via FYERS API v3 or Flattrade PiConnect; Crypto operates via Binance.
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
            {settings.apiType === 'crypto' ? 'Crypto Gateway' : 'Active Indian Broker'}
          </h3>
          <p className="text-xs text-muted-foreground mt-1">
            {settings.apiType === 'crypto'
              ? 'Binance provides real-time spot and futures market data.'
              : 'Select your active broker. All API credentials and secret keys are securely stored on your Render backend.'}
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

      {/* 3. Render Managed Integration Card */}
      {settings.apiType === 'indian' && (
        <div className="bg-card border border-primary/20 rounded-xl p-5 space-y-4 shadow-xs">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-lg bg-primary/10 text-primary">
                <Server className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                  <span>Render Backend Integration</span>
                  <span className="text-[10px] px-2 py-0.5 rounded-full font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1">
                    <Lock className="w-2.5 h-2.5" />
                    Keys Managed on Render
                  </span>
                </h3>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  Your App ID, API Secret, and OAuth exchanges are handled directly by your Render service (<code>droid-backend-emeq</code>).
                </p>
              </div>
            </div>
            <a
              href={
                settings.provider === 'fyers'
                  ? 'https://myapi.fyers.in/dashboard'
                  : 'https://wallconnect.flattrade.in/'
              }
              target="_blank"
              rel="noreferrer"
              className="text-xs text-primary hover:underline flex items-center gap-1 font-medium shrink-0"
            >
              <span>{settings.provider === 'fyers' ? 'Fyers Portal' : 'WallConnect Portal'}</span>
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>

          <div className="p-3.5 bg-secondary/40 rounded-xl border border-border/50 space-y-2.5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
              <span className="text-muted-foreground font-medium">
                Render Callback URL (Configure in {settings.provider === 'fyers' ? 'Fyers' : 'Flattrade'} Portal):
              </span>
              <div className="flex items-center gap-2">
                <code className="text-[11px] font-mono bg-background/80 px-2 py-1 rounded border border-border/60 text-sky-300">
                  {REDIRECT_BASE}/{settings.provider}/callback
                </code>
                <button
                  type="button"
                  onClick={() => handleCopyRedirect(settings.provider as 'fyers' | 'flattrade')}
                  className="flex items-center gap-1 px-2.5 py-1 bg-secondary hover:bg-secondary/80 text-foreground rounded text-[11px] font-medium transition-all cursor-pointer border border-border"
                >
                  {copiedRedirect ? (
                    <>
                      <Check className="w-3 h-3 text-emerald-400" />
                      <span>Copied!</span>
                    </>
                  ) : (
                    <>
                      <Copy className="w-3 h-3" />
                      <span>Copy</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>

          {/* Daily 1-Click Login Banner */}
          <div className="p-4 rounded-xl border border-primary/20 bg-primary/5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div className="space-y-0.5">
              <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                <ShieldCheck className="w-4 h-4 text-primary" />
                Daily 1-Click Authentication (SEBI Compliant)
              </div>
              <p className="text-[11px] text-muted-foreground leading-relaxed">
                Render will automatically fetch server keys, process the 2FA login, and activate your 24-hour market feed.
              </p>
            </div>
            <a
              href={settings.provider === 'fyers' ? fyersServerLoginUrl : flattradeServerLoginUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 px-4 py-2.5 bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold rounded-lg shadow-sm transition-all cursor-pointer whitespace-nowrap"
            >
              <span>
                {settings.provider === 'fyers'
                  ? 'Login & Authorize with FYERS'
                  : 'Login & Authorize with Flattrade'}
              </span>
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          </div>
        </div>
      )}

      {/* 4. Live Token Status & Diagnostic Card */}
      <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border pb-3">
          <div>
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-emerald-500" />
              Live Telemetry &amp; Connection Status
            </h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Monitored by Render backend TokenManager.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleTestConnection}
              disabled={testing}
              title="Test broker connection in real time"
              className="flex items-center gap-1.5 px-3 py-1.5 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/30 rounded-lg text-xs font-semibold transition-all cursor-pointer disabled:opacity-50"
            >
              <Activity className={`w-3.5 h-3.5 ${testing ? 'animate-spin' : ''}`} />
              <span>{testing ? 'Testing Live...' : 'Test Connection'}</span>
            </button>
            <button
              type="button"
              onClick={handleRefreshToken}
              disabled={refreshing || loadingToken}
              title="Refresh token"
              className="flex items-center gap-1.5 px-3 py-1.5 bg-secondary hover:bg-secondary/80 text-foreground rounded-lg text-xs font-semibold transition-all cursor-pointer disabled:opacity-50"
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
                      Click <strong>&quot;Login &amp; Authorize&quot;</strong> above to generate and activate your daily session.
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
            <span className="text-muted-foreground text-[11px] block">API Universe</span>
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

      {/* 5. Binance Crypto Details (if selected) */}
      {settings.provider === 'binance' && (
        <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <Key className="w-4 h-4 text-primary" />
              Binance Spot &amp; Futures Gateway
            </h3>
            <a
              href="https://www.binance.com/en/my/settings/api-management"
              target="_blank"
              rel="noreferrer"
              className="text-xs text-primary hover:underline flex items-center gap-1 font-medium"
            >
              <span>Binance Portal</span>
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>

          <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-lg text-xs text-amber-300 flex items-start gap-2">
            <Info className="w-4 h-4 shrink-0 mt-0.5" />
            <div>
              <strong>Public Market Data is Free &amp; Active:</strong> Binance real-time Spot &amp; Futures tickers, Order Books, Candlesticks, and Funding Rates stream directly with zero authentication required.
            </div>
          </div>
        </div>
      )}

      {/* 6. Optional Advanced Override Drawer */}
      <div className="border border-border/60 rounded-xl overflow-hidden bg-card/50">
        <button
          type="button"
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="w-full flex items-center justify-between p-4 text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
        >
          <span className="flex items-center gap-2">
            <Lock className="w-3.5 h-3.5" />
            Advanced: Custom UI Override (Optional)
          </span>
          {showAdvanced ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>

        {showAdvanced && (
          <div className="p-5 pt-0 border-t border-border/40 space-y-4 text-xs">
            <p className="text-[11px] text-muted-foreground mt-3">
              Leave empty to use credentials configured in Render Environment Variables. Enter values below only if you wish to override server defaults in this browser session.
            </p>

            {settings.provider === 'fyers' && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-semibold text-foreground block mb-1">
                    Custom Fyers App ID (Override)
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
                </div>
                <div>
                  <label className="text-xs font-semibold text-foreground block mb-1">
                    Custom Secret Key (Override)
                  </label>
                  <input
                    type={showSecret ? 'text' : 'password'}
                    placeholder="Enter Secret Key"
                    value={settings.fyers.secret}
                    onChange={(e) =>
                      onChange({ fyers: { ...settings.fyers, secret: e.target.value.trim() } })
                    }
                    className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-hidden focus:border-primary font-mono"
                  />
                </div>
              </div>
            )}

            {settings.provider === 'flattrade' && (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label className="text-xs font-semibold text-foreground block mb-1">
                    Client Code (Override)
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
                </div>
                <div>
                  <label className="text-xs font-semibold text-foreground block mb-1">
                    API Key (Override)
                  </label>
                  <input
                    type="text"
                    placeholder="Enter API Key"
                    value={flattradeCreds.apiKey}
                    onChange={(e) =>
                      onChange({
                        flattrade: { ...flattradeCreds, apiKey: e.target.value.trim() },
                      })
                    }
                    className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-hidden focus:border-primary font-mono"
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold text-foreground block mb-1">
                    API Secret (Override)
                  </label>
                  <input
                    type={showSecret ? 'text' : 'password'}
                    placeholder="Enter API Secret"
                    value={flattradeCreds.apiSecret}
                    onChange={(e) =>
                      onChange({
                        flattrade: { ...flattradeCreds, apiSecret: e.target.value.trim() },
                      })
                    }
                    className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-hidden focus:border-primary font-mono"
                  />
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
