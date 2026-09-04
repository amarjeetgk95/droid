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
  Gauge,
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
// Unified system status — one pill instead of Session / Mode / Stream x3.
// ---------------------------------------------------------------------------
type UnifiedTone = 'live' | 'demo' | 'closed' | 'offline' | 'degraded';

function getUnifiedStatus(
  health: MarketHealthStatus | null,
  marketStatus: MarketStatusResponse | null,
  streamState: StreamConnectionState,
): { tone: UnifiedTone; label: string; dot: string; pill: string; animate: boolean } {
  const session = marketStatus?.session;
  const mode = health?.mode;
  const healthy = health?.status === 'HEALTHY' && mode === 'LIVE';

  if (streamState === 'DISCONNECTED' || health?.status === 'UNHEALTHY') {
    return {
      tone: 'offline',
      label: 'OFFLINE',
      dot: 'bg-red-500',
      pill: 'bg-red-500/10 text-red-400 border-red-500/20',
      animate: false,
    };
  }
  if (mode === 'OFFLINE') {
    return {
      tone: 'demo',
      label: session === 'OPEN' ? 'DEMO • OPEN' : 'DEMO',
      dot: 'bg-amber-500',
      pill: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
      animate: false,
    };
  }
  if (streamState === 'CONNECTING' || streamState === 'RECONNECTING') {
    return {
      tone: 'degraded',
      label: 'SYNCING',
      dot: 'bg-amber-500',
      pill: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
      animate: false,
    };
  }
  if (session === 'CLOSED' || session === 'POST_CLOSE' || marketStatus?.is_trading_day === false) {
    return {
      tone: 'closed',
      label: marketStatus?.is_trading_day === false ? 'HOLIDAY' : 'CLOSED',
      dot: 'bg-slate-500',
      pill: 'bg-secondary text-muted-foreground border-border',
      animate: false,
    };
  }
  if (session === 'PRE_OPEN') {
    return {
      tone: 'degraded',
      label: 'PRE-OPEN',
      dot: 'bg-amber-500',
      pill: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
      animate: false,
    };
  }
  if (healthy && streamState === 'CONNECTED') {
    return {
      tone: 'live',
      label: 'LIVE • OPEN',
      dot: 'bg-emerald-500',
      pill: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
      animate: true,
    };
  }
  return {
    tone: 'degraded',
    label: 'DEGRADED',
    dot: 'bg-amber-500',
    pill: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    animate: false,
  };
}

function getMarketHint(marketStatus: MarketStatusResponse | null): string {
  if (!marketStatus) return '';
  if (marketStatus.is_trading_day === false) return '• Holiday';
  if (marketStatus.session === 'OPEN') return '• Till 15:30';
  if (marketStatus.session === 'PRE_OPEN') return '• Opens 09:15';
  if (marketStatus.session === 'POST_CLOSE') return '• Closed';
  return '• Closed';
}

// ---------------------------------------------------------------------------
// Center mini-strip — isolated so 10Hz tick merges don't re-render the header.
// Only pinned indices, not the full marquee (that lives in MarketTicker).
// ---------------------------------------------------------------------------
const PIN_ORDER = ['NIFTY', 'BANKNIFTY', 'SENSEX', 'INDIAVIX', 'FINNIFTY', 'BTCUSDT', 'ETHUSDT'];

const MiniStrip = memo(function MiniStrip() {
  const live = useOptionalLiveMarketContext();
  const cards = live?.cards ?? EMPTY_CARDS;
  const pinned = useMemo(() => {
    if (!cards.length) return [];
    const bySymbol = new Map(cards.map((c) => [c.symbol, c]));
    const out: typeof cards = [];
    for (const sym of PIN_ORDER) {
      const hit = bySymbol.get(sym);
      if (hit) out.push(hit);
      if (out.length >= 3) break;
    }
    if (out.length < 3) {
      for (const c of cards) {
        if (!out.includes(c)) out.push(c);
        if (out.length >= 3) break;
      }
    }
    return out;
  }, [cards]);

  if (pinned.length === 0) return null;
  return (
    <div className="hidden xl:flex items-center gap-4 shrink-0" aria-label="Key indices">
      {pinned.map((card) => {
        const pct = Number(card.change_percent) || 0;
        const isPos = pct > 0;
        const isNeutral = pct === 0;
        return (
          <Link
            key={card.symbol}
            href="/markets"
            className="flex items-center gap-1.5 text-xs hover:opacity-80 transition-opacity"
            title={`${card.display_name || card.symbol}`}
          >
            <span className="font-semibold text-muted-foreground tracking-tight">{card.display_name || card.symbol}</span>
            <span className="tabular-nums font-semibold text-foreground">{safeNum(Number(card.ltp))}</span>
            <span
              className={`tabular-nums font-semibold ${
                isNeutral ? 'text-muted-foreground' : isPos ? 'text-emerald-500' : 'text-red-500'
              }`}
            >
              {isNeutral ? '—' : isPos ? '▲' : '▼'} {Math.abs(pct).toFixed(2)}%
            </span>
          </Link>
        );
      })}
    </div>
  );
});

// ---------------------------------------------------------------------------
// Command palette — ⌘K search over pages + symbols + actions.
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

  // Autofocus on mount — parent mounts fresh each open, so no reset effect needed.
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
      { key: 'act:diag', section: 'Actions', label: 'View ingestion diagnostics', sub: 'Latency, reconnects, provider', action: onOpenDiagnostics },
      ...(onToggleTicker
        ? [{ key: 'act:ticker', section: 'Actions', label: tickerVisible ? 'Hide market ticker' : 'Show market ticker', sub: 'Toggle index strip', action: onToggleTicker } as PaletteItem]
        : []),
      { key: 'act:signals', section: 'Actions', label: 'Open Signal Center', sub: '/signals', href: '/signals' },
      { key: 'act:settings', section: 'Actions', label: 'Terminal settings', sub: '/settings', href: '/settings' },
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
      className="fixed inset-0 z-50 flex items-start justify-center pt-[12vh] bg-black/60 backdrop-blur-sm p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-label="Global search"
    >
      <div className="w-full max-w-lg rounded-xl border border-border bg-card shadow-2xl overflow-hidden">
        <div className="flex items-center gap-2 px-3 border-b border-border">
          <Search className="w-4 h-4 text-muted-foreground shrink-0" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => handleQueryChange(e.target.value)}
            placeholder="Search symbols, pages, actions…"
            className="flex-1 h-11 bg-transparent outline-none text-sm text-foreground placeholder:text-muted-foreground"
            aria-label="Search symbols, pages, actions"
          />
          <kbd className="hidden sm:inline text-[10px] font-mono px-1.5 py-0.5 rounded border border-border text-muted-foreground">
            ESC
          </kbd>
        </div>
        <div className="max-h-[50vh] overflow-auto p-1.5">
          {items.length === 0 ? (
            <p className="text-xs text-muted-foreground px-3 py-6 text-center">No matches for “{query}”.</p>
          ) : (
            items.map((item, idx) => {
              const header =
                item.section !== lastSection ? (
                  <div className="px-2.5 pt-2 pb-1 text-[10px] font-bold tracking-wider uppercase text-muted-foreground/75">
                    {item.section}
                  </div>
                ) : null;
              lastSection = item.section;
              const active = idx === activeIndex;
              return (
                <div key={item.key}>
                  {header}
                  <button
                    type="button"
                    onMouseEnter={() => setActiveIndex(idx)}
                    onClick={() => runItem(item)}
                    className={`w-full flex items-center justify-between gap-3 px-2.5 py-2 rounded-lg text-left transition-colors cursor-pointer ${
                      active ? 'bg-secondary text-foreground' : 'text-muted-foreground hover:bg-secondary/60'
                    }`}
                  >
                    <span className="min-w-0">
                      <span className="block text-xs font-semibold truncate">{item.label}</span>
                      {item.sub ? <span className="block text-[11px] opacity-70 truncate">{item.sub}</span> : null}
                    </span>
                    <ArrowRight className="w-3.5 h-3.5 shrink-0 opacity-50" />
                  </button>
                </div>
              );
            })
          )}
        </div>
        <div className="flex items-center gap-3 px-3 py-2 border-t border-border text-[10px] text-muted-foreground">
          <span>↑↓ navigate</span>
          <span>↵ open</span>
          <span className="ml-auto">⌘K to toggle</span>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Header
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
  // Hydrate persisted broker selection lazily — no mount effect needed.
  // Storage listener below keeps it fresh when Settings changes it.
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

  useEffect(() => {
    const syncBroker = () => {
      try {
        const stored = getStoredSettings();
        if (stored?.broker) {
          setActiveBroker(stored.broker.provider || 'fyers');
          setIsIndian(stored.broker.apiType !== 'crypto');
        }
      } catch {
        // keep current values on read failure
      }
    };
    window.addEventListener('storage', syncBroker);
    window.addEventListener('focus', syncBroker);
    return () => {
      window.removeEventListener('storage', syncBroker);
      window.removeEventListener('focus', syncBroker);
    };
  }, []);

  // Real alert count — replaces the old permanently-pulsing bell dot.
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

  // ⌘K / Ctrl+K toggles the palette globally.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const openDiagnostics = useCallback(() => setShowHealthModal(true), []);
  const status = getUnifiedStatus(health, marketStatus, streamState);
  const isHealthy = health?.status === 'HEALTHY' && health?.mode === 'LIVE';
  const authLoginUrl = `${api.getBaseUrl()}/api/v1/tokens/${activeBroker}/login`;
  const marketHint = getMarketHint(marketStatus);
  const statusTitle = `Session: ${marketStatus?.session ?? '—'} • Mode: ${health?.mode ?? '—'} • Feed: ${streamState} • Latency: ${health?.latency_ms ?? '—'}ms • Reconnects: ${health?.reconnect_count ?? 0}`;

  return (
    <>
      <header
        className="sticky top-0 z-30 h-12 shrink-0 border-b border-border bg-card/95 backdrop-blur flex items-center gap-2 px-3 [contain:paint]"
        style={{ contentVisibility: 'auto', containIntrinsicSize: '0 48px' } as React.CSSProperties}
      >
        {/* LEFT — menu + search */}
        <div className="flex items-center gap-2 min-w-0 flex-1">
          {onMenuClick && (
            <button
              type="button"
              onClick={onMenuClick}
              aria-label="Open navigation"
              className="md:hidden inline-flex h-8 w-8 items-center justify-center rounded-md border border-border bg-secondary text-muted-foreground hover:text-slate-100 transition-colors shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Menu className="w-4 h-4" />
            </button>
          )}
          <button
            type="button"
            onClick={() => setPaletteOpen(true)}
            className="group flex items-center gap-2 h-8 w-full max-w-[220px] sm:max-w-xs px-2.5 rounded-md border border-border bg-secondary/60 hover:bg-secondary hover:border-border text-muted-foreground hover:text-foreground transition-colors text-left cursor-pointer"
            title="Global search (⌘K)"
            aria-label="Global search"
          >
            <Search className="w-3.5 h-3.5 shrink-0" />
            <span className="hidden sm:inline flex-1 truncate text-xs">Search symbols, pages…</span>
            <span className="sm:hidden flex-1 truncate text-xs">Search…</span>
            <kbd className="hidden md:inline text-[10px] font-mono px-1.5 py-0.5 rounded border border-border bg-card">
              ⌘K
            </kbd>
          </button>

          {/* Slim clock — single line, no icon box */}
          <div className="hidden md:flex items-center gap-1.5 shrink-0 tabular-nums" title="IST • Asia/Kolkata">
            <Clock />
            {marketHint ? <span className="hidden xl:inline text-[11px] text-muted-foreground">{marketHint}</span> : null}
          </div>

          <MiniStrip />
        </div>

        {/* RIGHT — status + actions */}
        <div className="flex items-center gap-1.5 shrink-0">
          {/* Unified status pill */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                className={`inline-flex items-center gap-1.5 pl-2 pr-1.5 py-1 rounded-full text-[10px] font-semibold tracking-wide border cursor-pointer transition-colors ${status.pill}`}
                title={statusTitle}
                aria-label={`System status: ${status.label}`}
              >
                <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${status.dot} ${status.animate ? 'animate-live' : ''}`} />
                {status.label}
                {health?.latency_ms ? (
                  <span className="hidden xl:inline font-medium opacity-60 tabular-nums">• {health.latency_ms}ms</span>
                ) : null}
                <ChevronDown className="w-3 h-3 opacity-60" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-64 bg-card border-border shadow-xl p-2">
              <DropdownMenuLabel className="text-[11px] font-bold text-foreground px-2 py-1">System status</DropdownMenuLabel>
              <div className="px-2 py-1 space-y-1.5 text-[11px]">
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Session</span>
                  <span className="font-semibold text-foreground font-mono">{marketStatus?.session ?? '—'}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Trading day</span>
                  <span className="font-semibold text-foreground">{marketStatus?.is_trading_day === false ? 'Holiday' : 'Trading day'}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Data mode</span>
                  <span className="font-semibold text-foreground font-mono">{health?.mode ?? '—'}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Feed</span>
                  <span className="font-semibold text-foreground font-mono">{streamState}</span>
                </div>
                <div className="flex items-center justify-between tabular-nums">
                  <span className="text-muted-foreground">Latency</span>
                  <span className="font-semibold text-foreground">{health?.latency_ms != null ? `${health.latency_ms}ms` : '—'}</span>
                </div>
                <div className="flex items-center justify-between tabular-nums">
                  <span className="text-muted-foreground">Reconnects</span>
                  <span className="font-semibold text-foreground">{health?.reconnect_count ?? 0}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Provider</span>
                  <span className="font-semibold text-foreground font-mono">{health?.provider ?? marketStatus?.provider ?? '—'}</span>
                </div>
              </div>
              <DropdownMenuSeparator className="bg-border my-1" />
              <DropdownMenuItem
                onClick={openDiagnostics}
                className="cursor-pointer text-xs font-semibold text-primary flex items-center justify-between"
              >
                <span>View diagnostics</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          {/* Broker connection */}
          {isIndian && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-semibold transition-colors cursor-pointer whitespace-nowrap ${
                    !isHealthy
                      ? 'bg-amber-500 hover:bg-amber-400 text-slate-950'
                      : 'bg-emerald-500/10 hover:bg-emerald-500/15 text-emerald-400 border border-emerald-500/20'
                  }`}
                  title={!isHealthy ? `Daily auth required — authorize ${activeBroker.toUpperCase()}` : `Connected to ${activeBroker.toUpperCase()}`}
                  aria-label="Broker connection"
                >
                  <Zap className="w-3.5 h-3.5 fill-current" />
                  <span className="hidden sm:inline">{!isHealthy ? `Auth ${activeBroker.toUpperCase()}` : activeBroker.toUpperCase()}</span>
                  <span className="sm:hidden">{!isHealthy ? 'Auth' : 'Live'}</span>
                  <ChevronDown className="w-3 h-3 opacity-60" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-72 bg-card border-border shadow-xl p-2">
                <DropdownMenuLabel className="font-normal px-2 py-1.5">
                  <p className="text-xs font-bold text-foreground">Broker connection</p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    {!isHealthy
                      ? `${activeBroker.toUpperCase()} needs daily re-authorization.`
                      : `Live session via ${activeBroker.toUpperCase()}. Tokens expire daily.`}
                  </p>
                </DropdownMenuLabel>
                <DropdownMenuSeparator className="bg-border my-1" />
                <DropdownMenuItem asChild className="cursor-pointer p-2 rounded-lg">
                  <a href={authLoginUrl} target="_blank" rel="noreferrer" className="flex items-center justify-between w-full">
                    <span className="text-xs font-semibold">{!isHealthy ? `Authorize ${activeBroker.toUpperCase()}` : 'Re-authorize session'}</span>
                    <ExternalLink className="w-3.5 h-3.5 opacity-60" />
                  </a>
                </DropdownMenuItem>
                <DropdownMenuItem asChild className="cursor-pointer p-2 rounded-lg">
                  <Link href="/settings" className="flex items-center justify-between w-full">
                    <span className="text-xs font-semibold text-muted-foreground">Manage in Settings</span>
                    <ArrowRight className="w-3.5 h-3.5 opacity-60" />
                  </Link>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}

          <div className="hidden sm:block h-5 w-px bg-border mx-0.5" />

          {/* Ticker toggle */}
          {onToggleTicker && (
            <button
              onClick={onToggleTicker}
              className="p-2 rounded-md hover:bg-secondary border border-transparent hover:border-border text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
              title={tickerVisible ? 'Hide market ticker' : 'Show market ticker'}
              aria-label={tickerVisible ? 'Hide market ticker' : 'Show market ticker'}
              aria-pressed={tickerVisible}
            >
              {tickerVisible ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          )}

          {/* Telemetry */}
          <button
            onClick={openDiagnostics}
            className="p-2 rounded-md hover:bg-secondary border border-transparent hover:border-border text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
            title="View ingestion diagnostics"
            aria-label="Telemetry"
          >
            <Gauge className="w-4 h-4" />
          </button>

          {/* Notifications — badge only when there is a real count */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                className="relative p-2 rounded-md hover:bg-secondary border border-transparent hover:border-border text-muted-foreground hover:text-foreground transition-colors cursor-pointer outline-none focus:ring-1 focus:ring-primary"
                title={signalCount > 0 ? `${signalCount} active signals` : 'Alerts & signals'}
                aria-label="Notifications"
              >
                <Bell className="w-4 h-4" />
                {signalCount > 0 && (
                  <span className="absolute top-0.5 right-0.5 min-w-[16px] h-4 px-0.5 rounded-full bg-emerald-500 text-slate-950 text-[10px] font-bold leading-4 text-center tabular-nums ring-2 ring-card">
                    {signalCount > 99 ? '99+' : signalCount}
                  </span>
                )}
              </button>
            </DropdownMenuTrigger>

            <DropdownMenuContent align="end" className="w-80 bg-card border-border shadow-xl p-2">
              <DropdownMenuLabel className="font-normal px-2 py-1.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <span className={`w-2 h-2 rounded-full ${signalCount > 0 ? 'bg-emerald-500' : 'bg-slate-500'}`} />
                    <span className="text-xs font-bold text-foreground tracking-tight">Active Signals & Alerts</span>
                  </div>
                  {streamState === 'CONNECTED' && signalCount > 0 ? (
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-primary/10 text-primary border border-primary/20 font-semibold">
                      LIVE • {signalCount}
                    </span>
                  ) : (
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-secondary text-muted-foreground border border-border font-semibold">
                      {signalCount > 0 ? `${signalCount}` : 'IDLE'}
                    </span>
                  )}
                </div>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  Real-time alpha triggers, volatility spikes &amp; regime updates.
                </p>
              </DropdownMenuLabel>

              <DropdownMenuSeparator className="bg-border my-1" />

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

      {paletteOpen && (
        <CommandPalette
          open={paletteOpen}
          onClose={() => setPaletteOpen(false)}
          onOpenDiagnostics={openDiagnostics}
          onToggleTicker={onToggleTicker}
          tickerVisible={tickerVisible}
        />
      )}

      <MarketHealthModal
        isOpen={showHealthModal}
        onClose={() => setShowHealthModal(false)}
        health={health}
        streamState={streamState}
      />
    </>
  );
}

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
