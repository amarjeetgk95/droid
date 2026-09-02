'use client';

import { useEffect, useState, memo } from 'react';
import { usePathname } from 'next/navigation';
import { MarketHealthStatus, MarketStatusResponse } from '@/lib/types';
import { StreamConnectionState } from '@/hooks/useMarketStream';
import { UserProfileMenu } from '../auth/UserProfileMenu';
import { MarketHealthModal } from '../dashboard/MarketHealthModal';
import { Activity, Search, Bell, Clock3, Command, Menu, Zap, ExternalLink } from 'lucide-react';
import { getStoredSettings } from '@/lib/settings';
import { ClockDate } from './Clock';

// Route label map for breadcrumb
const ROUTE_LABELS: Record<string, string> = {
  '/': 'Dashboard',
  '/markets': 'Markets',
  '/crypto': 'Crypto',
  '/options': 'Options',
  '/historical-intelligence': 'Historical Intelligence',
  '/ai-analysis': 'AI Analysis',
  '/paper-trading': 'Paper Trading',
  '/algo-trading': 'Algo Trading',
  '/watchlist': 'Watchlist',
  '/settings': 'Settings',
};

function getSessionConfig(session?: string) {
  switch (session) {
    case 'OPEN':
      return {
        label: 'OPEN',
        dot: 'bg-emerald-500',
        pill: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
        dotAnimate: '',
      };
    case 'PRE_OPEN':
      return {
        label: 'PRE-OPEN',
        dot: 'bg-amber-500',
        pill: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
        dotAnimate: '',
      };
    case 'POST_CLOSE':
      return {
        label: 'POST-CLOSE',
        dot: 'bg-blue-500',
        pill: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
        dotAnimate: '',
      };
    case 'CLOSED':
    default:
      return {
        label: 'CLOSED',
        dot: 'bg-slate-500',
        pill: 'bg-secondary text-muted-foreground border-border',
        dotAnimate: '',
      };
  }
}

function getStreamConfig(state: StreamConnectionState) {
  switch (state) {
    case 'CONNECTED':
      return {
        label: 'LIVE',
        dot: 'bg-emerald-500',
        pill: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
        animate: 'animate-live',
      };
    case 'CONNECTING':
      return {
        label: 'CONNECTING',
        dot: 'bg-amber-500',
        pill: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
        animate: '',
      };
    case 'RECONNECTING':
      return {
        label: 'RECONNECTING',
        dot: 'bg-amber-500',
        pill: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
        animate: '',
      };
    case 'DISCONNECTED':
      return {
        label: 'OFFLINE',
        dot: 'bg-red-500',
        pill: 'bg-red-500/10 text-red-400 border-red-500/20',
        animate: '',
      };
    default:
      return {
        label: state,
        dot: 'bg-slate-500',
        pill: 'bg-secondary text-muted-foreground border-border',
        animate: '',
      };
  }
}

function getModeConfig(mode?: string) {
  if (mode === 'OFFLINE') {
    return {
      label: 'OFFLINE',
      dot: 'bg-amber-500',
      pill: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    };
  }
  return {
    label: 'LIVE',
    dot: 'bg-emerald-500',
    pill: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  };
}

export function TopHeader({
  health,
  marketStatus,
  streamState,
  onMenuClick,
}: {
  health: MarketHealthStatus | null;
  marketStatus: MarketStatusResponse | null;
  streamState: StreamConnectionState;
  onMenuClick?: () => void;
}) {
  const pathname = usePathname();
  const [showHealthModal, setShowHealthModal] = useState(false);
  const [activeBroker, setActiveBroker] = useState<string>('fyers');
  const [isIndian, setIsIndian] = useState<boolean>(true);

  useEffect(() => {
    try {
      const stored = getStoredSettings();
      if (stored?.broker) {
        setActiveBroker(stored.broker.provider || 'fyers');
        setIsIndian(stored.broker.apiType !== 'crypto');
      }
    } catch {
      setActiveBroker('fyers');
      setIsIndian(true);
    }
  }, [pathname]);

  const breadcrumb = (ROUTE_LABELS[pathname] ?? pathname.replace('/', '').replace(/-/g, ' ')) || 'Dashboard';
  const sessionCfg = getSessionConfig(marketStatus?.session);
  const streamCfg = getStreamConfig(streamState);
  const modeCfg = getModeConfig(health?.mode);
  const isDemo = health?.mode === 'OFFLINE';

  const authLoginUrl = `https://droid-backend-emeq.onrender.com/api/v1/tokens/${activeBroker}/login`;
  const isHealthy = health?.is_healthy === true && health?.mode !== 'OFFLINE';

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  return (
    <>
      <header className="sticky top-0 z-30 h-14 shrink-0 border-b border-border bg-card flex items-center justify-between gap-2 px-3 sm:px-4 [contain:paint]" style={{ contentVisibility: 'auto', containIntrinsicSize: '0 56px' } as React.CSSProperties}>
        {/* LEFT — Clock + Context */}
        <div className="flex items-center gap-3 min-w-0 flex-1">
          {onMenuClick && (
            <button
              type="button"
              onClick={onMenuClick}
              aria-label="Open navigation"
              className="md:hidden inline-flex h-8 w-8 items-center justify-center rounded-md border border-border bg-secondary hover:bg-secondary text-muted-foreground hover:text-slate-100 transition-colors shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Menu className="w-4 h-4" />
            </button>
          )}
          {/* Clock block — isolated ClockDate uses useSyncExternalStore so header no longer re-renders every second */}
          <div className="flex items-center gap-2.5 shrink-0">
            <div className="flex items-center gap-2">
              <div className="hidden sm:flex h-8 w-8 items-center justify-center rounded-md bg-blue-500/10 border border-blue-500/15">
                <Clock3 className="w-4 h-4 text-blue-400" />
              </div>
              <ClockDate />
            </div>

            <div className="hidden md:block h-7 w-px bg-secondary" />

            {/* Breadcrumb — desktop only */}
            <div className="hidden lg:flex items-center gap-2 min-w-0">
              <span className="text-xs font-semibold text-slate-100 truncate max-w-[160px]">{breadcrumb}</span>
              <span className="text-[11px] text-slate-500 hidden xl:inline truncate max-w-[180px]">
                {marketStatus?.is_trading_day === false ? '• Holiday' : ''}
              </span>
            </div>
          </div>
        </div>

        {/* CENTER — System Status Capsule — tight pills, single LIVE pulse only */}
        <div className="flex items-center justify-center gap-2 shrink-0">
          {/* Desktop capsule */}
          <div className="hidden md:flex items-center gap-1 p-1 rounded-full bg-card border border-border">
            {/* Session */}
            <span
              className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-[10px] font-semibold tracking-wide border ${sessionCfg.pill}`}
              title={`Session: ${marketStatus?.session ?? 'UNKNOWN'}`}
            >
              <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${sessionCfg.dot}`} />
              {sessionCfg.label}
            </span>

            <span className="w-px h-4 bg-secondary" />

            {/* Mode — no pulse */}
            <span
              className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-[10px] font-semibold tracking-wide border ${modeCfg.pill}`}
              title={isDemo ? 'Simulated / delayed data' : 'Live market data'}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${modeCfg.dot}`} />
              {modeCfg.label}
            </span>

            <span className="w-px h-4 bg-secondary" />

            {/* Stream — only LIVE dot animates */}
            <span
              className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-[10px] font-semibold border ${streamCfg.pill}`}
              title={`Feed: ${streamState} • Reconnects: ${health?.reconnect_count ?? 0} • Latency: ${health?.latency_ms ?? '—'}ms`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${streamCfg.dot} ${streamCfg.animate}`} />
              {streamCfg.label}
              {health?.latency_ms ? (
                <span className="hidden xl:inline text-[10px] font-medium opacity-60">• {health.latency_ms}ms</span>
              ) : null}
            </span>
          </div>

          {/* Mobile dots — only LIVE animates */}
          <div className="flex md:hidden items-center gap-1.5 p-1.5 rounded-full bg-card border border-border">
            <span className={`w-2 h-2 rounded-full ${sessionCfg.dot}`} title={sessionCfg.label} />
            <span className={`w-2 h-2 rounded-full ${modeCfg.dot}`} title={modeCfg.label} />
            <span className={`w-2 h-2 rounded-full ${streamCfg.dot} ${streamCfg.animate}`} title={streamCfg.label} />
          </div>
        </div>

        {/* RIGHT — Actions */}
        <div className="flex items-center gap-1.5 sm:gap-2 shrink-0 flex-1 justify-end">
          {/* 1-Click Connect — no pulse, TradingView tight style */}
          {isIndian && (
            <a
              href={authLoginUrl}
              target="_blank"
              rel="noreferrer"
              className={`inline-flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-md text-xs font-semibold transition-colors cursor-pointer whitespace-nowrap ${
                !isHealthy
                  ? 'bg-amber-500 hover:bg-amber-400 text-slate-950'
                  : 'bg-emerald-500/10 hover:bg-emerald-500/15 text-emerald-400 border border-emerald-500/20'
              }`}
              title={
                !isHealthy
                  ? `Daily Auth Required — Authorize ${activeBroker.toUpperCase()}`
                  : `Connected to ${activeBroker.toUpperCase()}`
              }
            >
              <Zap className={`w-3.5 h-3.5 ${!isHealthy ? 'fill-current text-slate-950' : 'text-emerald-400'}`} />
              <span className="font-semibold hidden sm:inline">
                {!isHealthy ? `Auth ${activeBroker.toUpperCase()}` : `${activeBroker.toUpperCase()}`}
              </span>
              <span className="sm:hidden font-semibold">{!isHealthy ? 'Auth' : 'Live'}</span>
              <ExternalLink className="w-3 h-3 opacity-60" />
            </a>
          )}

          {/* Search — desktop */}
          <button
            onClick={() => {
              const el = document.getElementById('global-search-trigger');
              el?.click();
            }}
            className="hidden sm:inline-flex items-center gap-2 pl-2.5 pr-1.5 py-1.5 rounded-md bg-secondary hover:bg-secondary border border-border text-xs text-muted-foreground hover:text-slate-100 transition-colors cursor-pointer group"
            title="Search instruments (⌘K)"
          >
            <Search className="w-3.5 h-3.5 text-slate-500 group-hover:text-muted-foreground" />
            <span className="hidden lg:inline font-medium">Search</span>
            <kbd className="hidden lg:inline-flex items-center gap-1 ml-1 px-1.5 py-0.5 rounded bg-card border border-border text-[10px] font-medium leading-none">
              <Command className="w-3 h-3" />K
            </kbd>
          </button>

          {/* Search — mobile icon */}
          <button
            className="sm:hidden p-2 rounded-md hover:bg-secondary border border-transparent hover:border-border text-muted-foreground hover:text-slate-100 transition-colors cursor-pointer"
            aria-label="Search"
            title="Search"
          >
            <Search className="w-4 h-4" />
          </button>

          <div className="hidden sm:block h-5 w-px bg-border mx-0.5" />

          {/* Telemetry */}
          <button
            onClick={() => setShowHealthModal(true)}
            className="p-2 rounded-md hover:bg-secondary border border-transparent hover:border-border text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
            title="View ingestion diagnostics"
            aria-label="Telemetry"
          >
            <Activity className="w-4 h-4" />
          </button>

          {/* Notifications */}
          <button
            className="relative p-2 rounded-md hover:bg-secondary border border-transparent hover:border-border text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
            title="Alerts & notifications"
            aria-label="Notifications"
          >
            <Bell className="w-4 h-4" />
          </button>

          <div className="h-6 w-px bg-secondary mx-1 hidden sm:block" />

          <UserProfileMenu />
        </div>
      </header>

      <MarketHealthModal
        isOpen={showHealthModal}
        onClose={() => setShowHealthModal(false)}
        health={health}
        streamState={streamState}
      />
    </>
  );
}
