'use client';

import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
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
import {
  Activity,
  ArrowRight,
  Bell,
  ChevronDown,
  ExternalLink,
  Eye,
  EyeOff,
  Globe,
  Menu,
  Radio,
  Search,
  Sparkles,
  Zap,
} from 'lucide-react';
import { getStoredSettings } from '@/lib/settings';
import { api } from '@/lib/api';
import { Clock } from './Clock';
import { ALL_NAV_ITEMS } from './nav-config';
import { useOptionalLiveMarketContext } from '@/context/LiveMarketContext';
import { safeNum } from '@/lib/utils';

const TICKER_VISIBLE_KEY = 'droid:ticker:visible';
const EMPTY_CARDS: { symbol: string; display_name: string; ltp: number; change_percent: number }[] = [];

// ---------------------------------------------------------------------------
// Unified System & Broker Status
// ---------------------------------------------------------------------------
type StatusTone = 'live' | 'demo' | 'closed' | 'offline' | 'degraded';

interface SystemStatus {
  tone: StatusTone;
  label: string;
  mobileLabel: string;
  dot: string;
  badge: string;
  animate: boolean;
}

function getSystemStatus(
  health: MarketHealthStatus | null,
  marketStatus: MarketStatusResponse | null,
  streamState: StreamConnectionState,
  activeBroker: string,
  isIndian: boolean,
): SystemStatus {
  const session = marketStatus?.session;
  const mode = health?.mode;
  const isBrokerAuthed = health?.status === 'HEALTHY' && mode === 'LIVE';
  const brokerName = (activeBroker || 'FYERS').toUpperCase();

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

  // If Indian broker needs daily token auth
  if (isIndian && !isBrokerAuthed) {
    return {
      tone: 'degraded',
      label: `AUTH ${brokerName}`,
      mobileLabel: 'AUTH',
      dot: 'bg-amber-500',
      badge: 'bg-amber-50 text-amber-800 border-amber-300 hover:bg-amber-100 ring-1 ring-amber-400/20',
      animate: true,
    };
  }

  if (mode === 'OFFLINE') {
    return {
      tone: 'demo',
      label: session === 'OPEN' ? `${brokerName} • DEMO` : 'DEMO',
      mobileLabel: 'DEMO',
      dot: 'bg-amber-500',
      badge: 'bg-amber-50 text-amber-800 border-amber-200 hover:bg-amber-100',
      animate: false,
    };
  }

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

  if (session === 'CLOSED' || session === 'POST_CLOSE' || marketStatus?.is_trading_day === false) {
    return {
      tone: 'closed',
      label: marketStatus?.is_trading_day === false ? `${brokerName} • HOLIDAY` : `${brokerName} • CLOSED`,
      mobileLabel: marketStatus?.is_trading_day === false ? 'HOLIDAY' : 'CLOSED',
      dot: 'bg-slate-400',
      badge: 'bg-secondary text-slate-700 border-border hover:bg-secondary/80',
      animate: false,
    };
  }

  if (session === 'PRE_OPEN') {
    return {
      tone: 'degraded',
      label: `${brokerName} • PRE-OPEN`,
      mobileLabel: 'PRE-OPEN',
      dot: 'bg-amber-500',
      badge: 'bg-amber-50 text-amber-800 border-amber-200 hover:bg-amber-100',
      animate: false,
    };
  }

  if (isBrokerAuthed && streamState === 'CONNECTED') {
    return {
      tone: 'live',
      label: `${brokerName} • LIVE`,
      mobileLabel: brokerName,
      dot: 'bg-emerald-500',
      badge: 'bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100',
      animate: true,
    };
  }

  return {
    tone: 'degraded',
    label: `${brokerName} • DEGRADED`,
    mobileLabel: 'DEGRADED',
    dot: 'bg-amber-500',
    badge: 'bg-amber-50 text-amber-800 border-amber-200 hover:bg-amber-100',
    animate: false,
  };
}

// ---------------------------------------------------------------------------
// Command Palette — ⌘K fast search across pages, symbols & actions
// ---------------------------------------------------------------------------
type PaletteItem = {
  key: string;
  section: string;
  label: string;
  sub?: string;
  href?: string;
  action?: () => void;
  icon?: React.ReactNode;
};

function CommandPalette({
  open,
  onClose,
  onOpenDiagnostics,
  onToggleTicker,
  tickerVisible,
}: {
  open: boolean;
  onClose: () => void;
  onOpenDiagnostics: () => void;
  onToggleTicker?: () => void;
  tickerVisible?: boolean;
}) {
  const router = useRouter();
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const live = useOptionalLiveMarketContext();
  const cards = live?.cards ?? EMPTY_CARDS;

  useEffect(() => {
    if (open) {
      const t = setTimeout(() => inputRef.current?.focus(), 30);
      return () => clearTimeout(t);
    }
  }, [open]);

  const handleQueryChange = useCallback((v: string) => {
    setQuery(v);
    setActiveIndex(0);
  }, []);

  const items: PaletteItem[] = useMemo(() => {
    const q = query.trim().toLowerCase();
    const match = (hay: string) => !q || hay.toLowerCase().includes(q);
    const out: PaletteItem[] = [];

    for (const nav of ALL_NAV_ITEMS) {
      const hay = `${nav.label} ${nav.description ?? ''} ${(nav.keywords ?? []).join(' ')} ${nav.href}`;
      if (match(hay)) {
        out.push({
          key: `page:${nav.href}`,
          section: 'Pages',
          label: nav.label,
          sub: nav.description ?? nav.href,
          href: nav.href,
        });
      }
    }
    for (const c of (cards ?? []).slice(0, 30)) {
      const hay = `${c.symbol} ${c.display_name ?? ''}`;
      if (match(hay)) {
        out.push({
          key: `sym:${c.symbol}`,
          section: 'Symbols',
          label: `${c.display_name || c.symbol}`,
          sub: `${c.symbol} • ${safeNum(Number(c.ltp))} • ${Number(c.change_percent || 0).toFixed(2)}%`,
          href: '/markets',
        });
      }
    }
    const actions: PaletteItem[] = [
      { key: 'act:diag', section: 'Actions', label: 'View Ingestion Diagnostics', sub: 'Latency, reconnects, data provider', action: onOpenDiagnostics },
      ...(onToggleTicker
        ? [{ key: 'act:ticker', section: 'Actions', label: tickerVisible ? 'Hide Market Ticker Marquee' : 'Show Market Ticker Marquee', sub: 'Toggle bottom index bar', action: onToggleTicker } as PaletteItem]
        : []),
      { key: 'act:signals', section: 'Actions', label: 'Open Signal Centre', sub: '/signals', href: '/signals' },
      { key: 'act:settings', section: 'Actions', label: 'Terminal & Broker Settings', sub: '/settings', href: '/settings' },
    ];
    for (const a of actions) {
      if (match(`${a.label} ${a.sub ?? ''}`)) out.push(a);
    }
    return out.slice(0, 40);
  }, [query, cards, onOpenDiagnostics, onToggleTicker, tickerVisible]);

  const runItem = useCallback(
    (item: PaletteItem) => {
      onClose();
      if (item.action) item.action();
      else if (item.href) router.push(item.href);
    },
    [onClose, router],
  );

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActiveIndex((i) => Math.min(i + 1, Math.max(items.length - 1, 0)));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActiveIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === 'Enter') {
        e.preventDefault();
        const item = items[activeIndex];
        if (item) runItem(item);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, items, activeIndex, onClose, runItem]);

  if (!open) return null;
  let lastSection = '';

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[14vh] bg-slate-900/40 backdrop-blur-xs p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-label="Global search palette"
    >
      <div className="w-full max-w-lg rounded-xl border border-border bg-card shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        <div className="flex items-center gap-2.5 px-3.5 border-b border-border bg-card">
          <Search className="w-4 h-4 text-muted-foreground shrink-0" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => handleQueryChange(e.target.value)}
            placeholder="Search symbols, pages, terminal actions…"
            className="flex-1 h-11 bg-transparent outline-none text-sm text-foreground placeholder:text-muted-foreground"
            aria-label="Search symbols, pages, actions"
          />
          <kbd className="hidden sm:inline text-[10px] font-mono px-1.5 py-0.5 rounded border border-border bg-muted text-muted-foreground">
            ESC
          </kbd>
        </div>

        <div className="max-h-[50vh] overflow-auto p-1.5 divide-y divide-border/20">
          {items.length === 0 ? (
            <div className="text-center py-8 px-4">
              <p className="text-xs font-medium text-foreground">No matches found</p>
              <p className="text-[11px] text-muted-foreground mt-1">No results matching “{query}”</p>
            </div>
          ) : (
            items.map((item, idx) => {
              const showHeader = item.section !== lastSection;
              lastSection = item.section;
              const active = idx === activeIndex;
              return (
                <div key={item.key}>
                  {showHeader && (
                    <div className="px-2.5 pt-2.5 pb-1 text-[10px] font-bold tracking-wider uppercase text-muted-foreground/80">
                      {item.section}
                    </div>
                  )}
                  <button
                    type="button"
                    onMouseEnter={() => setActiveIndex(idx)}
                    onClick={() => runItem(item)}
                    className={`w-full flex items-center justify-between gap-3 px-2.5 py-2 rounded-lg text-left transition-colors cursor-pointer ${
                      active ? 'bg-secondary text-foreground font-medium' : 'text-muted-foreground hover:bg-secondary/60'
                    }`}
                  >
                    <span className="min-w-0">
                      <span className="block text-xs font-semibold text-foreground truncate">{item.label}</span>
                      {item.sub ? <span className="block text-[11px] text-muted-foreground truncate">{item.sub}</span> : null}
                    </span>
                    <ArrowRight className={`w-3.5 h-3.5 shrink-0 transition-opacity ${active ? 'opacity-100 text-primary' : 'opacity-40'}`} />
                  </button>
                </div>
              );
            })
          )}
        </div>

        <div className="flex items-center gap-3 px-3 py-2 border-t border-border bg-secondary/30 text-[10px] text-muted-foreground">
          <span><kbd className="font-mono">↑↓</kbd> navigate</span>
          <span><kbd className="font-mono">↵</kbd> select</span>
          <span className="ml-auto"><kbd className="font-mono">⌘K</kbd> toggle</span>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main TopHeader Component
// ---------------------------------------------------------------------------
export function TopHeader({
  health,
  marketStatus,
  streamState,
  onMenuClick,
  tickerVisible = true,
  onToggleTicker,
}: {
  health: MarketHealthStatus | null;
  marketStatus: MarketStatusResponse | null;
  streamState: StreamConnectionState;
  onMenuClick?: () => void;
  tickerVisible?: boolean;
  onToggleTicker?: () => void;
}) {
  const [showHealthModal, setShowHealthModal] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
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
  const [signalCount, setSignalCount] = useState<number>(0);

  // Sync settings when changed from other tabs/dialogs
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

  // Poll signal count for notification badge
  useEffect(() => {
    let mounted = true;
    const fetchCount = async () => {
      try {
        const res = await api.getSignalsStatus();
        if (mounted) setSignalCount(res.active_count ?? 0);
      } catch {
        if (mounted) setSignalCount(0);
      }
    };
    void fetchCount();
    const id = setInterval(fetchCount, 60000);
    return () => {
      mounted = false;
      clearInterval(id);
    };
  }, []);

  // ⌘K / Ctrl+K keyboard shortcut
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
      // ⌘T / Ctrl+T toggles bottom ticker
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 't' && onToggleTicker) {
        e.preventDefault();
        onToggleTicker();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onToggleTicker]);

  const openDiagnostics = useCallback(() => setShowHealthModal(true), []);
  const status = getSystemStatus(health, marketStatus, streamState, activeBroker, isIndian);
  const isHealthy = health?.status === 'HEALTHY' && health?.mode === 'LIVE';
  const authLoginUrl = `${api.getBaseUrl()}/api/v1/tokens/${activeBroker}/login`;

  // Market session label
  const session = marketStatus?.session;
  const isTradingDay = marketStatus?.is_trading_day !== false;
  const sessionDisplay = useMemo(() => {
    if (!isTradingDay) return { text: 'Holiday', color: 'text-muted-foreground' };
    if (session === 'OPEN') return { text: 'Open • Till 15:30', color: 'text-emerald-700' };
    if (session === 'PRE_OPEN') return { text: 'Pre-Open • Till 09:15', color: 'text-amber-700' };
    if (session === 'POST_CLOSE') return { text: 'Post-Close', color: 'text-muted-foreground' };
    return { text: 'Closed', color: 'text-muted-foreground' };
  }, [session, isTradingDay]);

  return (
    <>
      <header
        className="sticky top-0 z-30 h-14 shrink-0 border-b border-border bg-card/95 backdrop-blur flex items-center justify-between px-3 md:px-4 [contain:paint]"
        style={{ contentVisibility: 'auto', containIntrinsicSize: '0 56px' } as React.CSSProperties}
      >
        {/* ================================================================= */}
        {/* LEFT ZONE: Navigation Toggle & Command Search                     */}
        {/* ================================================================= */}
        <div className="flex items-center gap-2 sm:gap-3 min-w-0">
          {onMenuClick && (
            <button
              type="button"
              onClick={onMenuClick}
              aria-label="Open mobile navigation"
              className="md:hidden inline-flex h-8 w-8 items-center justify-center rounded-md border border-border bg-card text-foreground hover:bg-secondary transition-colors shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Menu className="w-4 h-4" />
            </button>
          )}

          <button
            type="button"
            onClick={() => setPaletteOpen(true)}
            className="group flex items-center gap-2 h-8 w-44 sm:w-56 md:w-64 px-2.5 rounded-md border border-border/80 bg-secondary/60 hover:bg-secondary hover:border-border text-muted-foreground hover:text-foreground transition-all text-left cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            title="Global search (⌘K)"
            aria-label="Global command palette"
          >
            <Search className="w-3.5 h-3.5 shrink-0 text-muted-foreground group-hover:text-foreground transition-colors" />
            <span className="hidden sm:inline flex-1 truncate text-xs">Search symbols, pages…</span>
            <span className="sm:hidden flex-1 truncate text-xs">Search…</span>
            <kbd className="hidden sm:inline text-[10px] font-mono px-1.5 py-0.5 rounded border border-border/80 bg-card text-muted-foreground shadow-2xs">
              ⌘K
            </kbd>
          </button>
        </div>

        {/* ================================================================= */}
        {/* CENTER ZONE: Wall Clock & Session Context                         */}
        {/* ================================================================= */}
        <div className="hidden md:flex items-center shrink-0">
          <div className="flex items-center gap-2 px-2.5 py-1 rounded-md bg-secondary/40 border border-border/50 text-xs">
            <Clock />
            <span className="text-border">•</span>
            <span className={`font-medium ${sessionDisplay.color}`}>
              {sessionDisplay.text}
            </span>
          </div>
        </div>

        {/* ================================================================= */}
        {/* RIGHT ZONE: Unified Status, Ticker, Alerts, Profile              */}
        {/* ================================================================= */}
        <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
          {/* Consolidated Broker & System Status Pill */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                className={`inline-flex items-center gap-1.5 h-8 px-2.5 rounded-md text-xs font-semibold border transition-all cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-ring ${status.badge}`}
                title={`Broker: ${activeBroker.toUpperCase()} • Session: ${marketStatus?.session ?? '—'} • Stream: ${streamState}`}
                aria-label={`System & Broker Status: ${status.label}`}
              >
                <span className={`w-2 h-2 rounded-full shrink-0 ${status.dot} ${status.animate ? 'animate-live' : ''}`} />
                <span className="hidden sm:inline font-semibold">{status.label}</span>
                <span className="sm:hidden font-semibold">{status.mobileLabel}</span>
                {health?.latency_ms != null && (
                  <span className="hidden lg:inline text-[11px] opacity-70 font-normal tabular-nums">
                    {health.latency_ms}ms
                  </span>
                )}
                <ChevronDown className="w-3 h-3 opacity-60" />
              </button>
            </DropdownMenuTrigger>

            <DropdownMenuContent align="end" className="w-72 bg-card border-border shadow-xl p-2">
              <DropdownMenuLabel className="font-normal px-2 py-1">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-foreground">Broker & Gateway</span>
                  <span className={`text-[10px] font-bold px-1.5 py-0.2 rounded border ${
                    isHealthy
                      ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                      : 'bg-amber-50 text-amber-800 border-amber-200'
                  }`}>
                    {isHealthy ? 'ACTIVE' : 'AUTH REQUIRED'}
                  </span>
                </div>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  {isHealthy
                    ? `Live market feed via ${activeBroker.toUpperCase()}.`
                    : `${activeBroker.toUpperCase()} requires daily token authentication.`}
                </p>
              </DropdownMenuLabel>

              {/* 1-Click Action for Broker Auth */}
              {isIndian && (
                <div className="p-1">
                  <a
                    href={authLoginUrl}
                    target="_blank"
                    rel="noreferrer"
                    className={`flex items-center justify-between w-full px-2.5 py-1.5 rounded-md text-xs font-semibold transition-colors ${
                      !isHealthy
                        ? 'bg-amber-500 hover:bg-amber-600 text-slate-950 shadow-2xs'
                        : 'bg-secondary hover:bg-secondary/80 text-foreground border border-border'
                    }`}
                  >
                    <div className="flex items-center gap-1.5">
                      <Zap className="w-3.5 h-3.5 fill-current" />
                      <span>{!isHealthy ? `Authorize ${activeBroker.toUpperCase()}` : 'Re-authorize Session'}</span>
                    </div>
                    <ExternalLink className="w-3 h-3 opacity-70" />
                  </a>
                </div>
              )}

              <DropdownMenuSeparator className="bg-border my-1.5" />

              <div className="px-2 py-1 space-y-1.5 text-[11px]">
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Market Session</span>
                  <span className="font-semibold text-foreground font-mono">{marketStatus?.session ?? '—'}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Trading Day</span>
                  <span className="font-semibold text-foreground">
                    {marketStatus?.is_trading_day === false ? 'Exchange Holiday' : 'Normal Trading'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Live Feed</span>
                  <span className="font-semibold text-foreground font-mono">{streamState}</span>
                </div>
                <div className="flex items-center justify-between tabular-nums">
                  <span className="text-muted-foreground">Gateway Latency</span>
                  <span className="font-semibold text-foreground font-mono">
                    {health?.latency_ms != null ? `${health.latency_ms}ms` : '—'}
                  </span>
                </div>
                <div className="flex items-center justify-between tabular-nums">
                  <span className="text-muted-foreground">Reconnects</span>
                  <span className="font-semibold text-foreground">{health?.reconnect_count ?? 0}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Provider Gateway</span>
                  <span className="font-semibold text-foreground font-mono">
                    {health?.provider ?? marketStatus?.provider ?? activeBroker.toUpperCase()}
                  </span>
                </div>
              </div>

              <DropdownMenuSeparator className="bg-border my-1.5" />

              <div className="flex flex-col gap-0.5">
                <DropdownMenuItem
                  onClick={openDiagnostics}
                  className="cursor-pointer text-xs font-semibold text-primary flex items-center justify-between px-2 py-1.5 rounded-md hover:bg-primary/10"
                >
                  <div className="flex items-center gap-1.5">
                    <Activity className="w-3.5 h-3.5" />
                    <span>View Ingestion Diagnostics</span>
                  </div>
                  <ArrowRight className="w-3.5 h-3.5" />
                </DropdownMenuItem>

                <DropdownMenuItem asChild className="cursor-pointer text-xs font-medium text-muted-foreground flex items-center justify-between px-2 py-1.5 rounded-md hover:bg-secondary">
                  <Link href="/settings">
                    <div className="flex items-center gap-1.5">
                      <Globe className="w-3.5 h-3.5" />
                      <span>Manage Gateways in Settings</span>
                    </div>
                    <ArrowRight className="w-3.5 h-3.5 opacity-60" />
                  </Link>
                </DropdownMenuItem>
              </div>
            </DropdownMenuContent>
          </DropdownMenu>

          {/* Ticker Toggle Button */}
          {onToggleTicker && (
            <button
              onClick={onToggleTicker}
              className={`inline-flex items-center justify-center h-8 w-8 rounded-md border transition-colors cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                tickerVisible
                  ? 'border-border/80 bg-card text-foreground hover:bg-secondary'
                  : 'border-dashed border-border bg-secondary/50 text-muted-foreground hover:bg-secondary hover:text-foreground'
              }`}
              title={tickerVisible ? 'Hide market ticker marquee (⌘T)' : 'Show market ticker marquee (⌘T)'}
              aria-label={tickerVisible ? 'Hide market ticker' : 'Show market ticker'}
              aria-pressed={tickerVisible}
            >
              {tickerVisible ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          )}

          {/* Notifications & Active Signals */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                className="relative inline-flex items-center justify-center h-8 w-8 rounded-md border border-border/80 bg-card hover:bg-secondary text-muted-foreground hover:text-foreground transition-colors cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-ring"
                title={signalCount > 0 ? `${signalCount} active signals detected` : 'Active signals & scanner'}
                aria-label="Signals and notifications"
              >
                <Bell className="w-4 h-4" />
                {signalCount > 0 && (
                  <span className="absolute -top-1 -right-1 min-w-[17px] h-[17px] px-1 rounded-full bg-primary text-primary-foreground text-[10px] font-bold leading-[17px] text-center tabular-nums ring-2 ring-card shadow-2xs">
                    {signalCount > 99 ? '99+' : signalCount}
                  </span>
                )}
              </button>
            </DropdownMenuTrigger>

            <DropdownMenuContent align="end" className="w-80 bg-card border-border shadow-xl p-2">
              <DropdownMenuLabel className="font-normal px-2 py-1.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <span className={`w-2 h-2 rounded-full ${signalCount > 0 ? 'bg-emerald-500' : 'bg-slate-400'}`} />
                    <span className="text-xs font-bold text-foreground">Signals & Market Alerts</span>
                  </div>
                  <span className={`text-[10px] font-mono px-1.5 py-0.2 rounded font-semibold border ${
                    signalCount > 0
                      ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                      : 'bg-secondary text-muted-foreground border-border'
                  }`}>
                    {signalCount > 0 ? `${signalCount} LIVE` : 'IDLE'}
                  </span>
                </div>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  Real-time alpha triggers, options flow & regime alerts.
                </p>
              </DropdownMenuLabel>

              <DropdownMenuSeparator className="bg-border my-1" />

              <DropdownMenuItem asChild className="cursor-pointer p-2 rounded-lg flex items-start gap-2.5 hover:bg-secondary">
                <Link href="/signals">
                  <div className="p-1.5 rounded-md bg-emerald-50 text-emerald-600 border border-emerald-200 shrink-0 mt-0.5">
                    <Radio className="w-3.5 h-3.5" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-semibold text-foreground">Active Alpha Signals</p>
                    <p className="text-[10px] text-muted-foreground truncate">
                      Momentum, breakout & mean-reversion scanner
                    </p>
                  </div>
                </Link>
              </DropdownMenuItem>

              <DropdownMenuItem asChild className="cursor-pointer p-2 rounded-lg flex items-start gap-2.5 hover:bg-secondary">
                <Link href="/options">
                  <div className="p-1.5 rounded-md bg-blue-50 text-blue-600 border border-blue-200 shrink-0 mt-0.5">
                    <Activity className="w-3.5 h-3.5" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-semibold text-foreground">Options Greeks & Flow</p>
                    <p className="text-[10px] text-muted-foreground truncate">
                      PCR shifts, Max Pain migration & institutional OI
                    </p>
                  </div>
                </Link>
              </DropdownMenuItem>

              <DropdownMenuItem asChild className="cursor-pointer p-2 rounded-lg flex items-start gap-2.5 hover:bg-secondary">
                <Link href="/ai-analysis">
                  <div className="p-1.5 rounded-md bg-purple-50 text-purple-600 border border-purple-200 shrink-0 mt-0.5">
                    <Sparkles className="w-3.5 h-3.5" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-semibold text-foreground">AI Intelligence Briefing</p>
                    <p className="text-[10px] text-muted-foreground truncate">
                      Probabilistic model synthesis & multi-TF bias
                    </p>
                  </div>
                </Link>
              </DropdownMenuItem>

              <DropdownMenuSeparator className="bg-border my-1" />

              <DropdownMenuItem asChild className="cursor-pointer p-2 rounded-lg flex items-center justify-between text-xs font-semibold text-primary hover:bg-primary/10">
                <Link href="/signals">
                  <span>Open Signal Centre</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </Link>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          {/* Clean Divider */}
          <div className="h-5 w-px bg-border mx-0.5 hidden sm:block" />

          {/* User Profile */}
          <UserProfileMenu />
        </div>
      </header>

      {/* Global Command Palette */}
      {paletteOpen && (
        <CommandPalette
          open={paletteOpen}
          onClose={() => setPaletteOpen(false)}
          onOpenDiagnostics={openDiagnostics}
          onToggleTicker={onToggleTicker}
          tickerVisible={tickerVisible}
        />
      )}

      {/* Deep Ingestion Diagnostics Modal */}
      <MarketHealthModal
        isOpen={showHealthModal}
        onClose={() => setShowHealthModal(false)}
        health={health}
        streamState={streamState}
      />
    </>
  );
}

// ---------------------------------------------------------------------------
// Helpers for persistent ticker visibility
// ---------------------------------------------------------------------------
export function loadTickerVisible(): boolean {
  if (typeof window === 'undefined') return true;
  try {
    const v = localStorage.getItem(TICKER_VISIBLE_KEY);
    return v === null ? true : v === '1';
  } catch {
    return true;
  }
}

export function saveTickerVisible(v: boolean) {
  try {
    localStorage.setItem(TICKER_VISIBLE_KEY, v ? '1' : '0');
  } catch {}
}
