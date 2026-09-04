'use client';

import { useEffect, useState, memo } from 'react';
import { usePathname } from 'next/navigation';
import Link from 'next/link';
import { MarketHealthStatus, MarketStatusResponse } from '@/lib/types';
import { StreamConnectionState } from '@/hooks/useMarketStream';
import { UserProfileMenu } from '../auth/UserProfileMenu';
import { MarketHealthModal } from '../dashboard/MarketHealthModal';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Activity, Bell, Clock3, Menu, Zap, ExternalLink, Radio, Sparkles, ArrowRight } from 'lucide-react';
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
  // MarketHealthStatus has no `is_healthy` field — derive from the real
  // status/mode signals so the button isn't permanently stuck on amber.
  const isHealthy = health?.status === 'HEALTHY' && health?.mode === 'LIVE';

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
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                className="relative p-2 rounded-md hover:bg-secondary border border-transparent hover:border-border text-muted-foreground hover:text-foreground transition-colors cursor-pointer outline-none focus:ring-1 focus:ring-primary"
                title="Alerts & signals"
                aria-label="Notifications"
              >
                <Bell className="w-4 h-4" />
                <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-emerald-500 ring-2 ring-card animate-pulse" />
              </button>
            </DropdownMenuTrigger>

            <DropdownMenuContent align="end" className="w-80 bg-card border-border shadow-xl p-2">
              <DropdownMenuLabel className="font-normal px-2 py-1.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-emerald-500" />
                    <span className="text-xs font-bold text-foreground tracking-tight">Active Signals & Alerts</span>
                  </div>
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-primary/10 text-primary border border-primary/20 font-semibold">
                    LIVE
                  </span>
                </div>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  Real-time alpha triggers, volatility spikes &amp; regime updates.
                </p>
              </DropdownMenuLabel>

              <DropdownMenuSeparator className="bg-border my-1" />

              {/* Native Links (not router.push) so Radix closes the menu and
                  Next navigates in the same commit — no close-animation race. */}
              <DropdownMenuItem
                asChild
                className="cursor-pointer p-2 rounded-lg flex items-start gap-2.5 hover:bg-secondary/80 transition-colors"
              >
                <Link href="/signals">
                <div className="p-1.5 rounded-md bg-emerald-500/10 text-emerald-400 shrink-0 mt-0.5">
                  <Radio className="w-3.5 h-3.5" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-semibold text-foreground">Active Alpha Signals</p>
                  <p className="text-[10px] text-muted-foreground truncate">
                    Live momentum, breakout &amp; mean-reversion scanner
                  </p>
                </div>
                </Link>
              </DropdownMenuItem>

              <DropdownMenuItem
                asChild
                className="cursor-pointer p-2 rounded-lg flex items-start gap-2.5 hover:bg-secondary/80 transition-colors"
              >
                <Link href="/options">
                <div className="p-1.5 rounded-md bg-blue-500/10 text-blue-400 shrink-0 mt-0.5">
                  <Activity className="w-3.5 h-3.5" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-semibold text-foreground">Options Greeks &amp; Flow</p>
                  <p className="text-[10px] text-muted-foreground truncate">
                    PCR shifts, Max Pain migration &amp; institutional OI
                  </p>
                </div>
                </Link>
              </DropdownMenuItem>

              <DropdownMenuItem
                asChild
                className="cursor-pointer p-2 rounded-lg flex items-start gap-2.5 hover:bg-secondary/80 transition-colors"
              >
                <Link href="/ai-analysis">
                <div className="p-1.5 rounded-md bg-purple-500/10 text-purple-400 shrink-0 mt-0.5">
                  <Sparkles className="w-3.5 h-3.5" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-semibold text-foreground">AI Intelligence Briefing</p>
                  <p className="text-[10px] text-muted-foreground truncate">
                    Probabilistic model synthesis &amp; multi-TF bias
                  </p>
                </div>
                </Link>
              </DropdownMenuItem>

              <DropdownMenuSeparator className="bg-border my-1" />

              <DropdownMenuItem
                asChild
                className="cursor-pointer p-2 rounded-lg flex items-center justify-between text-xs font-semibold text-primary hover:bg-primary/10 transition-colors"
              >
                <Link href="/signals">
                <span>Open Signal Center</span>
                <ArrowRight className="w-3.5 h-3.5" />
                </Link>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

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
