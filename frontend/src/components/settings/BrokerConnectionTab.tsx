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
  Smartphone,
  Building2,
  Landmark,
  Globe,
} from 'lucide-react';
import { BrokerSettings, ApiType, BrokerProviderId } from '@/lib/settings';
import { api } from '@/lib/api';
import { useMarketStream } from '@/hooks/useMarketStream';

interface Props {
  settings: BrokerSettings;
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
  { id: 'fyers',     name: 'Fyers API v3',     badge: 'Low Latency',    desc: 'WebSocket & Brokerage',         apiType: 'indian', icon: TrendingUp, portalUrl: 'https://myapi.fyers.in/dashboard' },
  { id: 'upstox',    name: 'Upstox Pro',       badge: 'Official V2',    desc: 'Real-Time Tick Stream',         apiType: 'indian', icon: Building2,  portalUrl: 'https://developer.upstox.com/' },
  { id: 'groww',     name: 'Groww Open API',   badge: 'New',            desc: 'API Key + API Secret',          apiType: 'indian', icon: Smartphone, portalUrl: 'https://groww.in/trade-api' },
  { id: 'kotak_neo', name: 'Kotak Neo',        badge: 'Session-based',  desc: 'API Key + TOTP + MPIN',         apiType: 'indian', icon: Landmark,   portalUrl: 'https://www.kotaksecurities.com/platform/neo-trade-api/' },
];

const CRYPTO_PROVIDERS: ProviderCard[] = [
  { id: 'binance', name: 'Binance API', badge: 'Crypto & Spot', desc: 'Public Spot & Futures', apiType: 'crypto', icon: Bitcoin, portalUrl: 'https://www.binance.com/en/my/settings/api-management' },
];

export function BrokerConnectionTab({ settings, onChange, errors = [] }: Props) {
  const getError = (field: string) => errors.find((e) => e.path === `broker.${field}`)?.message;
  const [tokenStatus, setTokenStatus] = useState<Record<string, any> | null>(null);
  const [loadingToken, setLoadingToken] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [tokenMsg, setTokenMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [showSecret, setShowSecret] = useState(false);
  const [copiedRedirect, setCopiedRedirect] = useState(false);

  const { streamState, reconnectCount } = useMarketStream();

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
      if (tokenConnected) return { connected: true, label: 'CONNECTED', sub: 'WebSocket • Live', tone: 'emerald' as const, hasCreds };
      return { connected: false, label: hasCreds ? (tokenStatus?.state === 'AUTH_EXPIRED' ? 'AUTH EXPIRED' : 'CREDENTIALS SAVED — AUTH REQUIRED') : 'NOT CONFIGURED', sub: hasCreds ? (tokenStatus?.last_error || 'Click Force Refresh to authenticate') : 'Enter App ID + Secret', tone: hasCreds ? (tokenStatus?.state === 'AUTH_EXPIRED' ? 'red' as const : 'amber' as const) : 'red' as const, hasCreds };
    }
    if (p === 'upstox') {
      const hasCreds = Boolean(settings.upstox.apiKey && settings.upstox.secret);
      if (tokenConnected) return { connected: true, label: 'CONNECTED', sub: 'WebSocket • Live', tone: 'emerald' as const, hasCreds };
      return { connected: false, label: hasCreds ? (tokenStatus?.state === 'AUTH_EXPIRED' ? 'AUTH EXPIRED' : 'CREDENTIALS SAVED — AUTH REQUIRED') : 'NOT CONFIGURED', sub: hasCreds ? (tokenStatus?.last_error || 'Click Force Refresh to authenticate') : 'Enter API Key + Secret', tone: hasCreds ? (tokenStatus?.state === 'AUTH_EXPIRED' ? 'red' as const : 'amber' as const) : 'red' as const, hasCreds };
    }
    if (p === 'groww') {
      const hasCreds = Boolean(settings.groww.apiKey && settings.groww.apiSecret);
      if (tokenConnected) return { connected: true, label: 'CONNECTED', sub: 'WebSocket • Live', tone: 'emerald' as const, hasCreds };
      return { connected: false, label: hasCreds ? (tokenStatus?.state === 'AUTH_EXPIRED' ? 'AUTH EXPIRED' : 'CREDENTIALS SAVED — AUTH REQUIRED') : 'NOT CONFIGURED', sub: hasCreds ? (tokenStatus?.last_error || 'Click Force Refresh to authenticate') : 'Enter API Key + API Secret', tone: hasCreds ? (tokenStatus?.state === 'AUTH_EXPIRED' ? 'red' as const : 'amber' as const) : 'red' as const, hasCreds };
    }
    if (p === 'kotak_neo') {
      const hasCreds = Boolean(settings.kotakNeo.apiKey && settings.kotakNeo.apiSecret && settings.kotakNeo.mpin);
      if (tokenConnected) return { connected: true, label: 'CONNECTED', sub: 'WebSocket • Live', tone: 'emerald' as const, hasCreds };
      return { connected: false, label: hasCreds ? (tokenStatus?.state === 'AUTH_EXPIRED' ? 'AUTH EXPIRED' : 'CREDENTIALS SAVED — AUTH REQUIRED') : 'NOT CONFIGURED', sub: hasCreds ? (tokenStatus?.last_error || 'Click Force Refresh to start a session') : 'Enter API Key + Secret + MPIN', tone: hasCreds ? (tokenStatus?.state === 'AUTH_EXPIRED' ? 'red' as const : 'amber' as const) : 'red' as const, hasCreds };
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
      const res = await api.refreshToken();
      setTokenMsg({
        type: 'success',
        text: `Token successfully refreshed for ${res.data.provider.toUpperCase()} provider!`,
      });
      await fetchTokenStatus();
    } catch (err: any) {
      setTokenMsg({ type: 'error', text: err?.message || 'Failed to refresh token' });
    } finally {
      setRefreshing(false);
    }
  };

  const handleCopyRedirect = () => {
    let uri = window.location.origin + '/api/v1/auth/callback';
    if (settings.provider === 'fyers') uri = settings.fyers.redirectUri || `${REDIRECT_BASE}/fyers/callback`;
    if (settings.provider === 'upstox') uri = settings.upstox.redirectUri || `${REDIRECT_BASE}/upstox/callback`;
    navigator.clipboard.writeText(uri);
    setCopiedRedirect(true);
    setTimeout(() => setCopiedRedirect(false), 2000);
  };

  const handleApiTypeChange = (next: ApiType) => {
    const defaultProvider: BrokerProviderId = next === 'crypto' ? 'binance' : 'fyers';
    onChange({ apiType: next, provider: defaultProvider });
  };

  const activeProviderCard = [...INDIAN_PROVIDERS, ...CRYPTO_PROVIDERS].find((p) => p.id === settings.provider);

  return (
    <div className="space-y-6">
      {/* 1. API Type Selector (Indian vs Crypto) */}
      <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
        <div>
          <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
            <Globe className="w-4 h-4 text-primary" />
            API Type
          </h3>
          <p className="text-xs text-muted-foreground mt-1">
            Choose the asset universe you want to connect. Indian markets use SEBI-registered brokers; Crypto uses Binance public + private APIs.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {([
            { id: 'indian' as ApiType, name: 'Indian Market', desc: 'NSE / BSE cash, F&O derivatives, indices (INR)', icon: Landmark },
            { id: 'crypto' as ApiType, name: 'Crypto Market',  desc: 'Spot & Futures pairs on Binance (USDT-quoted)',   icon: Bitcoin },
          ]).map((t) => {
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
                <div className={`p-2 rounded-lg ${isSelected ? 'bg-primary text-primary-foreground' : 'bg-secondary text-muted-foreground'}`}>
                  <Icon className="w-4 h-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold text-foreground">{t.name}</div>
                  <div className="text-[11px] text-muted-foreground">{t.desc}</div>
                </div>
                <span className={`text-[10px] px-2 py-0.5 rounded font-mono font-medium ${
                  isSelected ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'
                }`}>
                  {isSelected ? 'ACTIVE' : 'TAP'}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* 2. Active Provider Switcher (filtered by apiType) */}
      <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
        <div>
          <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
            <Radio className="w-4 h-4 text-primary" />
            {settings.apiType === 'crypto' ? 'Crypto Provider' : 'Indian Broker'}
          </h3>
          <p className="text-xs text-muted-foreground mt-1">
            Select the primary data provider for market feeds, order books, and real-time tick streaming.
          </p>
        </div>

        <div className={`grid grid-cols-1 ${settings.apiType === 'crypto' ? 'sm:grid-cols-1' : 'sm:grid-cols-2 lg:grid-cols-4'} gap-3`}>
          {visibleProviders.map((p) => {
            const isSelected = settings.provider === p.id;
            const Icon = p.icon;
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => onChange({ provider: p.id })}
                className={`flex flex-col text-left p-3.5 rounded-xl border transition-all cursor-pointer ${
                  isSelected
                    ? 'border-primary bg-primary/10 ring-2 ring-primary/20'
                    : 'border-border bg-card hover:bg-secondary/40'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-xs text-foreground flex items-center gap-1.5">
                    <Icon className="w-3.5 h-3.5" />
                    {p.name}
                  </span>
                  <span
                    className={`text-[10px] px-1.5 py-0.5 rounded font-mono font-medium ${
                      isSelected ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'
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

      {/* 3. Live Token Status & Diagnostic Card */}
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
            {tokenMsg.type === 'success' ? <CheckCircle2 className="w-4 h-4 shrink-0" /> : <AlertCircle className="w-4 h-4 shrink-0" />}
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
              {settings.apiType === 'crypto' ? <Bitcoin className="w-3 h-3" /> : <Landmark className="w-3 h-3" />}
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
            <span className="text-[10px] text-muted-foreground block">{providerMeta.connected ? 'WebSocket • Live' : 'Enter credentials to connect'}</span>
          </div>
        </div>
      </div>

      {/* 4. Provider Specific Credentials Configuration */}
      {settings.provider === 'binance' && (
        <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <Key className="w-4 h-4 text-primary" />
              Binance Spot & Futures API Configuration
            </h3>
            <a href="https://www.binance.com/en/my/settings/api-management" target="_blank" rel="noreferrer" className="text-xs text-primary hover:underline flex items-center gap-1 font-medium">
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
              <label className="text-xs font-semibold text-foreground block mb-1">Binance API Key (Optional)</label>
              <input
                type="text"
                placeholder="e.g. vmPUZE6mv9SD5VNH..."
                value={settings.binance.apiKey}
                onChange={(e) => onChange({ binance: { ...settings.binance, apiKey: e.target.value } })}
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
                  onChange={(e) => onChange({ binance: { ...settings.binance, apiSecret: e.target.value } })}
                  className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 pr-10 text-xs text-foreground focus:outline-hidden focus:border-primary font-mono"
                />
                <button type="button" onClick={() => setShowSecret(!showSecret)} className="absolute right-2 top-2 text-muted-foreground hover:text-foreground cursor-pointer">
                  {showSecret ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {settings.provider === 'fyers' && (
        <IndianBrokerCredentials
          title="Fyers API v3 Credentials"
          portalUrl="https://myapi.fyers.in/dashboard"
          portalLabel="Fyers Developer Portal"
          appIdLabel="Fyers App ID (Client ID)"
          appIdPlaceholder="e.g. XC12345-100"
          appId={settings.fyers.appId}
          onAppIdChange={(v) => onChange({ fyers: { ...settings.fyers, appId: v } })}
          secret={settings.fyers.secret}
          onSecretChange={(v) => onChange({ fyers: { ...settings.fyers, secret: v } })}
          redirectUri={settings.fyers.redirectUri}
          showSecret={showSecret}
          setShowSecret={setShowSecret}
          copied={copiedRedirect}
          onCopy={handleCopyRedirect}
        />
      )}

      {settings.provider === 'upstox' && (
        <IndianBrokerCredentials
          title="Upstox API v2 Credentials"
          portalUrl="https://developer.upstox.com/"
          portalLabel="Upstox Developer Console"
          appIdLabel="Upstox API Key"
          appIdPlaceholder="e.g. 849a9b..."
          appId={settings.upstox.apiKey}
          onAppIdChange={(v) => onChange({ upstox: { ...settings.upstox, apiKey: v } })}
          secret={settings.upstox.secret}
          onSecretChange={(v) => onChange({ upstox: { ...settings.upstox, secret: v } })}
          redirectUri={settings.upstox.redirectUri}
          showSecret={showSecret}
          setShowSecret={setShowSecret}
          copied={copiedRedirect}
          onCopy={handleCopyRedirect}
        />
      )}

      {settings.provider === 'groww' && (
        <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <Key className="w-4 h-4 text-primary" />
              Groww Open API Credentials
            </h3>
            <a href="https://groww.in/trade-api" target="_blank" rel="noreferrer" className="text-xs text-primary hover:underline flex items-center gap-1 font-medium">
              <span>Groww Trade API</span>
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>

          <div className="p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg text-xs text-blue-300 flex items-start gap-2">
            <Info className="w-4 h-4 shrink-0 mt-0.5" />
            <div>
              <strong>Authentication:</strong> Groww uses API Key + API Secret pairs. Generate these from the Groww Trade API dashboard. The backend will exchange them for a short-lived access token on Force Refresh.
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-semibold text-foreground block mb-1">Groww API Key</label>
              <input
                type="text"
                placeholder="e.g. groww_xxxxxxxxxxxxxxxx"
                value={settings.groww.apiKey}
                onChange={(e) => onChange({ groww: { ...settings.groww, apiKey: e.target.value } })}
                className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-hidden focus:border-primary font-mono"
              />
              {getError('groww.apiKey') && <p className="text-[10px] text-destructive mt-1">{getError('groww.apiKey')}</p>}
            </div>
            <div>
              <label className="text-xs font-semibold text-foreground block mb-1">Groww API Secret</label>
              <div className="relative">
                <input
                  type={showSecret ? 'text' : 'password'}
                  placeholder="Enter your Groww API Secret"
                  value={settings.groww.apiSecret}
                  onChange={(e) => onChange({ groww: { ...settings.groww, apiSecret: e.target.value } })}
                  className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 pr-10 text-xs text-foreground focus:outline-hidden focus:border-primary font-mono"
                />
                <button type="button" onClick={() => setShowSecret(!showSecret)} className="absolute right-2 top-2 text-muted-foreground hover:text-foreground cursor-pointer">
                  {showSecret ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              {getError('groww.apiSecret') && <p className="text-[10px] text-destructive mt-1">{getError('groww.apiSecret')}</p>}
            </div>
          </div>
        </div>
      )}

      {settings.provider === 'kotak_neo' && (
        <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <Key className="w-4 h-4 text-primary" />
              Kotak Neo (Neo API) Credentials
            </h3>
            <a href="https://www.kotaksecurities.com/platform/neo-trade-api/" target="_blank" rel="noreferrer" className="text-xs text-primary hover:underline flex items-center gap-1 font-medium">
              <span>Neo Trade API Docs</span>
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>

          <div className="p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg text-xs text-blue-300 flex items-start gap-2">
            <Info className="w-4 h-4 shrink-0 mt-0.5" />
            <div>
              <strong>Two-step auth (UCC + TOTP + MPIN):</strong> Enter your Unique Client Code (UCC), the Access Token from the Neo API Dashboard, your registered mobile number, and your 6-digit MPIN. The backend performs TOTP login → MPIN validate to obtain a 6-hour trade token. <strong>TOPT code must be supplied at runtime</strong> — it changes every 30 seconds via Google/Microsoft Authenticator.
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-semibold text-foreground block mb-1">UCC — Unique Client Code</label>
              <input
                type="text"
                placeholder="e.g. AB123 (5 chars)"
                value={settings.kotakNeo.apiKey}
                onChange={(e) => onChange({ kotakNeo: { ...settings.kotakNeo, apiKey: e.target.value } })}
                className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-hidden focus:border-primary font-mono"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-foreground block mb-1">Access Token (from Neo API Dashboard)</label>
              <div className="relative">
                <input
                  type={showSecret ? 'text' : 'password'}
                  placeholder="e.g. ec6a746c-e44b-455e-abf2-c13352b2fc45"
                  value={settings.kotakNeo.apiSecret}
                  onChange={(e) => onChange({ kotakNeo: { ...settings.kotakNeo, apiSecret: e.target.value } })}
                  className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 pr-10 text-xs text-foreground focus:outline-hidden focus:border-primary font-mono"
                />
                <button type="button" onClick={() => setShowSecret(!showSecret)} className="absolute right-2 top-2 text-muted-foreground hover:text-foreground cursor-pointer">
                  {showSecret ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>
            <div>
              <label className="text-xs font-semibold text-foreground block mb-1">Mobile Number (with country code)</label>
              <input
                type="text"
                placeholder="+91XXXXXXXXXX"
                value={settings.kotakNeo.mobileNumber}
                onChange={(e) => onChange({ kotakNeo: { ...settings.kotakNeo, mobileNumber: e.target.value } })}
                className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-hidden focus:border-primary font-mono"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-foreground block mb-1">MPIN (6 digits)</label>
              <input
                type="password"
                inputMode="numeric"
                maxLength={6}
                placeholder="••••••"
                value={settings.kotakNeo.mpin}
                onChange={(e) => onChange({ kotakNeo: { ...settings.kotakNeo, mpin: e.target.value.replace(/\D/g, '') } })}
                className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-hidden focus:border-primary font-mono tracking-widest"
              />
            </div>

            <div className="sm:col-span-2">
              <label className="text-xs font-semibold text-foreground block mb-1">TOTP Code (runtime, rotates every 30s)</label>
              <p className="text-[10px] text-muted-foreground mb-1">
                Current 6-digit code from Google/Microsoft Authenticator. Enter a fresh code and click Force Refresh to log in (step 1 of 2).
              </p>
              <input
                type="text"
                inputMode="numeric"
                maxLength={6}
                placeholder="e.g. 123456"
                value={settings.kotakNeo.totp}
                onChange={(e) => onChange({ kotakNeo: { ...settings.kotakNeo, totp: e.target.value.replace(/\D/g, '') } })}
                className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-hidden focus:border-primary font-mono tracking-widest"
              />
            </div>
          </div>
        </div>
      )}

      {/* 5. Stream Health */}
      <div className="bg-card border border-border rounded-xl p-5 shadow-xs">
        <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
          <Activity className="w-4 h-4 text-primary" />
          Live Market Stream
        </h3>
        <div className="flex items-center gap-3 mt-3 text-xs">
          <span className={`w-2.5 h-2.5 rounded-full ${providerMeta.connected ? 'bg-emerald-500 animate-pulse' : 'bg-destructive'}`} />
          <span className={`font-mono font-bold ${providerMeta.connected ? 'text-emerald-400' : 'text-destructive'}`}>
            {providerMeta.connected ? 'CONNECTED' : 'DISCONNECTED'}
          </span>
          <span className="text-muted-foreground">· {providerMeta.connected ? `${reconnectCount} reconnects` : providerMeta.sub}</span>
          <span className="ml-auto text-[11px] text-muted-foreground">
            {activeProviderCard ? activeProviderCard.name : '—'} · {settings.apiType.toUpperCase()}
          </span>
        </div>
        {!providerMeta.connected && (
          <p className="text-[11px] text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2 mt-3">
            Only the Binance public stream is connected without credentials. All Indian brokers and Binance private account queries require valid API credentials.
          </p>
        )}
      </div>
    </div>
  );
}

interface IndianBrokerCredentialsProps {
  title: string;
  portalUrl: string;
  portalLabel: string;
  appIdLabel: string;
  appIdPlaceholder: string;
  appId: string;
  onAppIdChange: (v: string) => void;
  secret: string;
  onSecretChange: (v: string) => void;
  redirectUri: string;
  showSecret: boolean;
  setShowSecret: (b: boolean) => void;
  copied: boolean;
  onCopy: () => void;
}

function IndianBrokerCredentials(props: IndianBrokerCredentialsProps) {
  return (
    <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
          <Key className="w-4 h-4 text-primary" />
          {props.title}
        </h3>
        <a href={props.portalUrl} target="_blank" rel="noreferrer" className="text-xs text-primary hover:underline flex items-center gap-1 font-medium">
          <span>{props.portalLabel}</span>
          <ExternalLink className="w-3 h-3" />
        </a>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="text-xs font-semibold text-foreground block mb-1">{props.appIdLabel}</label>
          <input
            type="text"
            placeholder={props.appIdPlaceholder}
            value={props.appId}
            onChange={(e) => props.onAppIdChange(e.target.value)}
            className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-hidden focus:border-primary font-mono"
          />
        </div>
        <div>
          <label className="text-xs font-semibold text-foreground block mb-1">Secret Key</label>
          <div className="relative">
            <input
              type={props.showSecret ? 'text' : 'password'}
              placeholder="Enter your API Secret Key"
              value={props.secret}
              onChange={(e) => props.onSecretChange(e.target.value)}
              className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 pr-10 text-xs text-foreground focus:outline-hidden focus:border-primary font-mono"
            />
            <button type="button" onClick={() => props.setShowSecret(!props.showSecret)} className="absolute right-2 top-2 text-muted-foreground hover:text-foreground cursor-pointer">
              {props.showSecret ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
        </div>
        <div className="sm:col-span-2">
          <label className="text-xs font-semibold text-foreground block mb-1">OAuth2 Redirect Callback URL</label>
          <div className="flex gap-2">
            <input
              type="text"
              readOnly
              value={props.redirectUri}
              className="flex-1 bg-secondary/30 border border-border rounded-lg px-3 py-2 text-xs text-muted-foreground font-mono"
            />
            <button type="button" onClick={props.onCopy} className="flex items-center gap-1 px-3 py-2 bg-secondary hover:bg-secondary/80 text-foreground rounded-lg text-xs font-semibold transition-all cursor-pointer">
              {props.copied ? (<><Check className="w-3.5 h-3.5 text-emerald-400" /><span>Copied!</span></>) : (<><Copy className="w-3.5 h-3.5" /><span>Copy</span></>)}
            </button>
          </div>
          <span className="text-[11px] text-muted-foreground mt-1 block">Paste this exact callback URL into your broker developer app configuration.</span>
        </div>
      </div>
    </div>
  );
}
