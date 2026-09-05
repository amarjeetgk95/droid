'use client';

import { memo, useEffect, useState } from 'react';
import Link from 'next/link';
import { MarketHealthStatus, MarketStatusResponse } from '@/lib/types';
import { StreamConnectionState } from '@/hooks/useMarketStream';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Activity, ArrowRight, ChevronDown, ExternalLink, Globe, Zap } from 'lucide-react';
import { getStoredSettings } from '@/lib/settings';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';

export type StatusTone = 'live' | 'demo' | 'closed' | 'offline' | 'degraded';

interface SystemStatus {
  tone: StatusTone;
  label: string;
  mobileLabel: string;
  dot: string;
  badge: string;
  animate: boolean;
}

function resolveSystemStatus(
  health: MarketHealthStatus | null,
  marketStatus: MarketStatusResponse | null,
  streamState: StreamConnectionState,
  activeBroker: string,
  isIndian: boolean,
): SystemStatus {
  const session = marketStatus?.session;
  const mode = health?.mode;
  const brokerName = (activeBroker || 'FYERS').toUpperCase();
  const isHealthyStatus = health?.status === 'HEALTHY' || health?.mode === 'LIVE';
  const isBrokerConnected = isHealthyStatus && streamState === 'CONNECTED';

  // 1. Fully Offline or Unhealthy Stream -> Red
  if (streamState === 'DISCONNECTED' || health?.status === 'UNHEALTHY') {
    return {
      tone: 'offline',
      label: 'OFFLINE',
      mobileLabel: 'OFFLINE',
      dot: 'bg-rose-500',
      badge: 'bg-rose-50 text-rose-700 border-rose-200 hover:bg-rose-100',
      animate: false,
    };
  }

  // 2. Connecting / Syncing -> Amber pulsing
  if (streamState === 'CONNECTING' || streamState === 'RECONNECTING') {
    return {
      tone: 'degraded',
      label: 'SYNCING…',
      mobileLabel: 'SYNC',
      dot: 'bg-amber-500',
      badge: 'bg-amber-50 text-amber-800 border-amber-200 hover:bg-amber-100',
      animate: true,
    };
  }

  // 3. Broker is Authenticated & Connected -> GREEN!
  if (isBrokerConnected) {
    if (session === 'OPEN') {
      return {
        tone: 'live',
        label: `${brokerName} • LIVE`,
        mobileLabel: brokerName,
        dot: 'bg-emerald-500',
        badge: 'bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100',
        animate: true,
      };
    }
    if (session === 'PRE_OPEN') {
      return {
        tone: 'live',
        label: `${brokerName} • PRE-OPEN`,
        mobileLabel: 'PRE-OPEN',
        dot: 'bg-emerald-500',
        badge: 'bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100',
        animate: false,
      };
    }
    // Connected outside trading hours (after market / holiday) -> Solid Green Connected
    return {
      tone: 'live',
      label: `${brokerName} • CONNECTED`,
      mobileLabel: brokerName,
      dot: 'bg-emerald-500',
      badge: 'bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100',
      animate: false,
    };
  }

  // 4. If Indian broker is degraded / needs token authentication
  if (isIndian && !isHealthyStatus) {
    if (session === 'CLOSED' || session === 'POST_CLOSE' || marketStatus?.is_trading_day === false) {
      return {
        tone: 'closed',
        label: marketStatus?.is_trading_day === false ? `${brokerName} • HOLIDAY` : `${brokerName} • CLOSED`,
        mobileLabel: marketStatus?.is_trading_day === false ? 'HOLIDAY' : 'CLOSED',
        dot: 'bg-amber-500',
        badge: 'bg-secondary text-slate-700 border-border hover:bg-secondary/80',
        animate: false,
      };
    }

    return {
      tone: 'degraded',
      label: `AUTH ${brokerName}`,
      mobileLabel: 'AUTH',
      dot: 'bg-amber-500',
      badge: 'bg-amber-50 text-amber-800 border-amber-300 hover:bg-amber-100 ring-1 ring-amber-400/20',
      animate: true,
    };
  }

  // 5. Explicit Offline / Demo Mode
  if (mode === 'OFFLINE' && !isHealthyStatus) {
    return {
      tone: 'demo',
      label: session === 'OPEN' ? `${brokerName} • DEMO` : 'DEMO',
      mobileLabel: 'DEMO',
      dot: 'bg-amber-500',
      badge: 'bg-amber-50 text-amber-800 border-amber-200 hover:bg-amber-100',
      animate: false,
    };
  }

  // Fallback Closed
  return {
    tone: 'closed',
    label: `${brokerName} • CLOSED`,
    mobileLabel: 'CLOSED',
    dot: 'bg-slate-400',
    badge: 'bg-secondary text-slate-700 border-border hover:bg-secondary/80',
    animate: false,
  };
}

interface HeaderBrokerGatewayProps {
  health: MarketHealthStatus | null;
  marketStatus: MarketStatusResponse | null;
  streamState: StreamConnectionState;
  onOpenDiagnostics: () => void;
}

export function HeaderBrokerGateway({
  health,
  marketStatus,
  streamState,
  onOpenDiagnostics,
}: HeaderBrokerGatewayProps) {
  const [activeBroker, setActiveBroker] = useState<string>(() => {
    try {
      return getStoredSettings()?.broker?.provider || 'fyers';
    } catch {
      return 'fyers';
    }
  });

  const [isIndian, setIsIndian] = useState<boolean>(() => {
    try {
      return getStoredSettings()?.broker?.apiType !== 'crypto';
    } catch {
      return true;
    }
  });

  // Sync settings when modified in other tabs or modal dialogs
  useEffect(() => {
    const syncBroker = () => {
      try {
        const stored = getStoredSettings();
        if (stored?.broker) {
          setActiveBroker(stored.broker.provider || 'fyers');
          setIsIndian(stored.broker.apiType !== 'crypto');
        }
      } catch {}
    };

    window.addEventListener('storage', syncBroker);
    window.addEventListener('focus', syncBroker);
    return () => {
      window.removeEventListener('storage', syncBroker);
      window.removeEventListener('focus', syncBroker);
    };
  }, []);

  const status = resolveSystemStatus(health, marketStatus, streamState, activeBroker, isIndian);
  const isHealthy = (health?.status === 'HEALTHY' || health?.mode === 'LIVE') && streamState === 'CONNECTED';
  const authLoginUrl = `${api.getBaseUrl()}/api/v1/tokens/${activeBroker}/login`;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className={cn(
            'inline-flex items-center gap-1.5 h-8 px-2.5 rounded-lg text-xs font-semibold border transition-all cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-ring shadow-2xs select-none',
            status.badge,
          )}
          title={`Broker: ${activeBroker.toUpperCase()} • Session: ${marketStatus?.session ?? '—'} • Stream: ${streamState}`}
          aria-label={`Broker Gateway: ${status.label}`}
        >
          <span className={cn('w-2 h-2 rounded-full shrink-0', status.dot, status.animate && 'animate-live')} />
          <span className="hidden sm:inline font-semibold">{status.label}</span>
          <span className="sm:hidden font-semibold">{status.mobileLabel}</span>

          {health?.latency_ms != null && (
            <span className="hidden lg:inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono font-medium bg-black/5 text-foreground/80 tabular-nums">
              {health.latency_ms}ms
            </span>
          )}

          <ChevronDown className="w-3 h-3 opacity-60 ml-0.5" />
        </button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="w-80 bg-card border-border shadow-xl p-2.5">
        <DropdownMenuLabel className="font-normal px-2 py-1">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-foreground">Broker & Data Feed</span>
            <span
              className={cn(
                'text-[10px] font-bold px-2 py-0.5 rounded-full border',
                isHealthy
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                  : 'bg-amber-50 text-amber-800 border-amber-200',
              )}
            >
              {isHealthy ? 'CONNECTED' : 'ACTION REQUIRED'}
            </span>
          </div>
          <p className="text-[11px] text-muted-foreground mt-1">
            {isHealthy
              ? `Connected to ${activeBroker.toUpperCase()} real-time tick engine.${marketStatus?.session === 'CLOSED' ? ' Exchange is currently closed.' : ''}`
              : `${activeBroker.toUpperCase()} session requires active token authentication.`}
          </p>
        </DropdownMenuLabel>

        {/* 1-Click Action for Indian Broker Auth */}
        {isIndian && (
          <div className="p-1">
            <a
              href={authLoginUrl}
              target="_blank"
              rel="noreferrer"
              className={cn(
                'flex items-center justify-between w-full px-3 py-2 rounded-lg text-xs font-semibold transition-all shadow-2xs cursor-pointer',
                !isHealthy
                  ? 'bg-amber-500 hover:bg-amber-600 text-slate-950 font-bold'
                  : 'bg-secondary hover:bg-secondary/80 text-foreground border border-border',
              )}
            >
              <div className="flex items-center gap-1.5">
                <Zap className={cn('w-3.5 h-3.5', !isHealthy ? 'fill-current' : 'text-primary')} />
                <span>{!isHealthy ? `Authorize ${activeBroker.toUpperCase()}` : 'Re-authorize Token'}</span>
              </div>
              <ExternalLink className="w-3 h-3 opacity-70" />
            </a>
          </div>
        )}

        <DropdownMenuSeparator className="bg-border my-1.5" />

        {/* Gateway Telemetry Specs */}
        <div className="px-2 py-1 space-y-1.5 text-[11px]">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">Market Session</span>
            <span className="font-semibold text-foreground font-mono">{marketStatus?.session ?? '—'}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">Exchange Day</span>
            <span className="font-semibold text-foreground">
              {marketStatus?.is_trading_day === false ? 'Exchange Holiday' : 'Normal Trading'}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">WebSocket Stream</span>
            <span className="font-semibold text-foreground font-mono">{streamState}</span>
          </div>
          <div className="flex items-center justify-between tabular-nums">
            <span className="text-muted-foreground">Round-Trip Latency</span>
            <span className="font-semibold text-foreground font-mono">
              {health?.latency_ms != null ? `${health.latency_ms}ms` : '—'}
            </span>
          </div>
          <div className="flex items-center justify-between tabular-nums">
            <span className="text-muted-foreground">Stream Reconnects</span>
            <span className="font-semibold text-foreground">{health?.reconnect_count ?? 0}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">Provider Gateway</span>
            <span className="font-semibold text-foreground font-mono uppercase">
              {health?.provider ?? marketStatus?.provider ?? activeBroker.toUpperCase()}
            </span>
          </div>
        </div>

        <DropdownMenuSeparator className="bg-border my-1.5" />

        {/* Quick Links with unified styling */}
        <div className="flex flex-col gap-0.5">
          <DropdownMenuItem
            onClick={onOpenDiagnostics}
            className="cursor-pointer text-xs font-medium text-foreground flex items-center justify-between px-2.5 py-2 rounded-lg hover:bg-secondary transition-colors"
          >
            <div className="flex items-center gap-2">
              <Activity className="w-3.5 h-3.5 text-primary" />
              <span>Ingestion Diagnostics</span>
            </div>
            <ArrowRight className="w-3.5 h-3.5 text-muted-foreground/60" />
          </DropdownMenuItem>

          <DropdownMenuItem asChild className="cursor-pointer text-xs font-medium text-foreground flex items-center justify-between px-2.5 py-2 rounded-lg hover:bg-secondary transition-colors">
            <Link href="/settings">
              <div className="flex items-center gap-2">
                <Globe className="w-3.5 h-3.5 text-muted-foreground" />
                <span>Configure in Settings</span>
              </div>
              <ArrowRight className="w-3.5 h-3.5 text-muted-foreground/60" />
            </Link>
          </DropdownMenuItem>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export const MemoizedHeaderBrokerGateway = memo(HeaderBrokerGateway);
