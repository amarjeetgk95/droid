'use client';

import { useEffect, useState, useMemo } from 'react';
import { usePathname } from 'next/navigation';
import { MarketHealthStatus, MarketStatusResponse } from '@/lib/types';
import { StreamConnectionState } from '@/hooks/useMarketStream';
import { UserProfileMenu } from '../auth/UserProfileMenu';
import { MarketHealthModal } from '../dashboard/MarketHealthModal';
import { Activity, Search, Bell, Clock3, Command, Menu, Zap, ExternalLink } from 'lucide-react';
import { useSettings } from '@/components/settings/SettingsProvider';

// Route label map for breadcrumb
const ROUTE_LABELS: Record<string, string> = {
  '/': 'Dashboard',
  '/markets': 'Markets',
  '/crypto': 'Crypto',
  '/options': 'Options',
  '/chart-analysis': 'Chart Analysis',
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
        pill: 'bg-emerald-500/10 text-emerald-700 border-emerald-500/25',
        dotAnimate: 'animate-pulse',
      };
    case 'PRE_OPEN':
      return {
        label: 'PRE-OPEN',
        dot: 'bg-amber-500',
        pill: 'bg-amber-500/10 text-amber-700 border-amber-500/25',
        dotAnimate: 'animate-pulse',
      };
    case 'POST_CLOSE':
      return {
        label: 'POST-CLOSE',
        dot: 'bg-blue-500',
        pill: 'bg-blue-500/10 text-blue-700 border-blue-500/20',
        dotAnimate: '',
      };
    case 'CLOSED':
    default:
      return {
        label: 'CLOSED',
        dot: 'bg-slate-400',
        pill: 'bg-slate-100 text-slate-600 border-slate-200',
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
        pill: 'bg-emerald-500/10 text-emerald-700 border-emerald-500/20',
        animate: 'animate-pulse',
      };
    case 'CONNECTING':
      return {
        label: 'CONNECTING',
        dot: 'bg-amber-500',
        pill: 'bg-amber-500/10 text-amber-700 border-amber-500/20',
        animate: 'animate-pulse',
      };
    case 'RECONNECTING':
      return {
        label: 'RECONNECTING',
        dot: 'bg-amber-500',
        pill: 'bg-amber-500/10 text-amber-700 border-amber-500/20',
        animate: 'animate-pulse',
      };
    case 'DISCONNECTED':
      return {
        label: 'OFFLINE',
        dot: 'bg-red-500',
        pill: 'bg-red-500/10 text-red-600 border-red-500/20',
        animate: '',
      };
    default:
      return {
        label: state,
        dot: 'bg-slate-400',
        pill: 'bg-slate-100 text-slate-600 border-slate-200',
        animate: '',
      };
  }
}

function getModeConfig(mode?: string) {
  if (mode === 'OFFLINE') {
    return {
      label: 'OFFLINE',
      dot: 'bg-amber-500',
      pill: 'bg-amber-500/10 text-amber-700 border-amber-500/30',
    };
  }
  return {
    label: 'LIVE',
    dot: 'bg-emerald-500',
    pill: 'bg-emerald-500/10 text-emerald-700 border-emerald-500/20',
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
  const [now, setNow] = useState<Date>(() => new Date());

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  const timeStr = useMemo(
    () => now.toLocaleTimeString('en-GB', { timeZone: 'Asia/Kolkata', hour12: false }),
    [now]
  );
  const dateStr = useMemo(
    () =>
      now.toLocaleDateString('en-IN', {
        timeZone: 'Asia/Kolkata',
        weekday: 'short',
        day: '2-digit',
        month: 'short',
      }),
    [now]
  );

  const breadcrumb = (ROUTE_LABELS[pathname] ?? pathname.replace('/', '').replace(/-/g, ' ')) || 'Dashboard';
  const sessionCfg = getSessionConfig(marketStatus?.session);
  const streamCfg = getStreamConfig(streamState);
  const modeCfg = getModeConfig(health?.mode);
  const isDemo = health?.mode === 'OFFLINE';

  let activeBroker = 'fyers';
  let isIndian = true;
  try {
    // eslint-disable-next-line react-hooks/rules-of-hooks
    const settingsCtx = useSettings();
    activeBroker = settingsCtx?.settings?.broker?.provider || 'fyers';
    isIndian = settingsCtx?.settings?.broker?.apiType !== 'crypto';
  } catch {
    // Graceful fallback if rendered outside provider context
  }

  const showQuickAuth = isIndian && streamState !== 'CONNECTED';
  const authLoginUrl = `https://droid-backend-emeq.onrender.com/api/v1/tokens/${activeBroker}/login`;

  // Keyboard shortcut hint for search
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        // Future: open command palette
        // For now, no-op but keeps hint functional
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  return (
    <>
      <header className="sticky top-0 z-30 h-14 shrink-0 border-b border-border bg-card/80 backdrop-blur-md supports-[backdrop-filter]:bg-card/60 flex items-center justify-between gap-2 px-3 sm:px-4">
        {/* LEFT — Clock + Context */}
        <div className="flex items-center gap-3 min-w-0 flex-1">
          {onMenuClick && (
            <button
              type="button"
              onClick={onMenuClick}
              aria-label="Open navigation"
              className="md:hidden inline-flex h-8 w-8 items-center justify-center rounded-md border border-border bg-card hover:bg-accent text-muted-foreground hover:text-foreground transition-colors shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Menu className="w-4 h-4" />
            </button>
          )}
          {/* Clock block */}
          <div className="flex items-center gap-2.5 shrink-0">
            <div className="flex items-center gap-2">
              <div className="hidden sm:flex h-8 w-8 items-center justify-center rounded-md bg-primary/10 border border-primary/15">
                <Clock3 className="w-4 h-4 text-primary" />
              </div>
              <div className="flex flex-col leading-none">
                <div className="flex items-baseline gap-1.5">
                  <span className="text-[13px] font-bold tabular-nums tracking-tight text-foreground">
                    {timeStr}
                  </span>
                  <span className="hidden sm:inline text-[11px] font-semibold text-muted-foreground">IST</span>
                </div>
                <span className="hidden sm:inline text-[11px] font-medium text-muted-foreground tabular-nums">
                  {dateStr} • IST
                </span>
                {/* Mobile: collapsed */}
                <span className="sm:hidden text-[10px] font-medium text-muted-foreground">IST • {dateStr}</span>
              </div>
            </div>

            <div className="hidden md:block h-7 w-px bg-border" />

            {/* Breadcrumb — desktop only */}
            <div className="hidden lg:flex items-center gap-2 min-w-0">
              <span className="text-xs font-semibold text-foreground truncate max-w-[160px]">{breadcrumb}</span>
              <span className="text-[11px] text-muted-foreground hidden xl:inline truncate max-w-[180px]">
                {marketStatus?.is_trading_day === false ? '• Holiday' : ''}
              </span>
            </div>
          </div>
        </div>

        {/* CENTER — System Status Capsule + Quick Connect */}
        <div className="flex items-center justify-center gap-2 shrink-0">
          {/* 1-Click Quick Connect Pill (Only shown when daily auth is required) */}
          {showQuickAuth && (
            <a
              href={authLoginUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-amber-500/15 hover:bg-amber-500/25 text-amber-400 dark:text-amber-300 border border-amber-500/40 shadow-xs animate-pulse transition-all cursor-pointer whitespace-nowrap"
              title={`1-Click connect ${activeBroker.toUpperCase()} daily session via Render`}
            >
              <Zap className="w-3.5 h-3.5 text-amber-400 fill-amber-400/30" />
              <span>1-Click Connect {activeBroker.toUpperCase()}</span>
              <ExternalLink className="w-3 h-3 opacity-70" />
            </a>
          )}

          {/* Desktop capsule */}
          <div className="hidden md:flex items-center gap-1 p-1 rounded-full bg-muted/60 border border-border/60 shadow-sm">
            {/* Session */}
            <span
              className={`inline-flex items-center gap-1.5 pl-1 pr-2.5 py-1 rounded-full text-[11px] font-bold tracking-wide border ${sessionCfg.pill}`}
              title={`Session: ${marketStatus?.session ?? 'UNKNOWN'}`}
            >
              <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${sessionCfg.dot} ${sessionCfg.dotAnimate}`} />
              {sessionCfg.label}
            </span>

            <span className="w-px h-4 bg-border/80" />

            {/* Mode */}
            <span
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold tracking-wide border ${modeCfg.pill}`}
              title={isDemo ? 'Simulated / delayed data' : 'Live market data'}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${modeCfg.dot} ${isDemo ? 'animate-pulse' : ''}`} />
              {modeCfg.label}
            </span>

            <span className="w-px h-4 bg-border/80" />

            {/* Stream */}
            <span
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold border ${streamCfg.pill}`}
              title={`Feed: ${streamState} • Reconnects: ${health?.reconnect_count ?? 0} • Latency: ${health?.latency_ms ?? '—'}ms`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${streamCfg.dot} ${streamCfg.animate}`} />
              {streamCfg.label}
              {health?.latency_ms ? (
                <span className="hidden xl:inline text-[10px] font-medium opacity-70">• {health.latency_ms}ms</span>
              ) : null}
            </span>
          </div>

          {/* Mobile dots */}
          <div className="flex md:hidden items-center gap-1.5 p-1.5 rounded-full bg-muted/60 border border-border/60">
            <span className={`w-2 h-2 rounded-full ${sessionCfg.dot} ${sessionCfg.dotAnimate}`} title={sessionCfg.label} />
            <span className={`w-2 h-2 rounded-full ${modeCfg.dot}`} title={modeCfg.label} />
            <span className={`w-2 h-2 rounded-full ${streamCfg.dot} ${streamCfg.animate}`} title={streamCfg.label} />
          </div>
        </div>

        {/* RIGHT — Actions */}
        <div className="flex items-center gap-1 sm:gap-1.5 shrink-0 flex-1 justify-end">
          {/* Search — desktop */}
          <button
            onClick={() => {
              // placeholder: in future open command palette
              const el = document.getElementById('global-search-trigger');
              el?.click();
            }}
            className="hidden sm:inline-flex items-center gap-2 pl-2.5 pr-1.5 py-1.5 rounded-md bg-muted hover:bg-muted/80 border border-border text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer group"
            title="Search instruments (⌘K)"
          >
            <Search className="w-3.5 h-3.5 text-muted-foreground group-hover:text-foreground" />
            <span className="hidden lg:inline font-medium">Search</span>
            <kbd className="hidden lg:inline-flex items-center gap-1 ml-1 px-1.5 py-0.5 rounded bg-card border border-border text-[10px] font-medium leading-none shadow-sm">
              <Command className="w-3 h-3" />K
            </kbd>
          </button>

          {/* Search — mobile icon */}
          <button
            className="sm:hidden p-2 rounded-md hover:bg-muted border border-transparent hover:border-border text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
            aria-label="Search"
            title="Search"
          >
            <Search className="w-4 h-4" />
          </button>

          <div className="hidden sm:block h-5 w-px bg-border mx-0.5" />

          {/* Telemetry */}
          <button
            onClick={() => setShowHealthModal(true)}
            className="p-2 rounded-md hover:bg-muted border border-transparent hover:border-border text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
            title="View ingestion diagnostics"
            aria-label="Telemetry"
          >
            <Activity className="w-4 h-4" />
          </button>

          {/* Notifications */}
          <button
            className="relative p-2 rounded-md hover:bg-muted border border-transparent hover:border-border text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
            title="Alerts & notifications"
            aria-label="Notifications"
          >
            <Bell className="w-4 h-4" />
            {/* Dot indicator — only if needed; hidden for now but ready for count */}
            {/* <span className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-red-500 rounded-full ring-2 ring-card" /> */}
          </button>

          <div className="h-6 w-px bg-border mx-1 hidden sm:block" />

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
