'use client';

import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Activity,
  ArrowRight,
  BarChart2,
  Radio,
  Search,
  Settings,
  Sparkles,
  TrendingUp,
  X,
} from 'lucide-react';
import { ALL_NAV_ITEMS, NAV_GROUPS, STANDALONE_ITEMS, BOTTOM_ITEMS } from '../nav-config';
import { useOptionalLiveMarketContext } from '@/context/LiveMarketContext';
import { safeNum, safeInt, cn } from '@/lib/utils';

export type PaletteCategory = 'all' | 'symbols' | 'pages' | 'actions';

export interface PaletteItem {
  key: string;
  category: 'symbols' | 'pages' | 'actions';
  section: string;
  label: string;
  sub?: string;
  badge?: string;
  badgeTone?: 'emerald' | 'rose' | 'amber' | 'blue' | 'muted';
  href?: string;
  action?: () => void;
  icon?: React.ReactNode;
}

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  onOpenDiagnostics: () => void;
  onToggleTicker?: () => void;
  tickerVisible?: boolean;
}

const EMPTY_CARDS: { symbol: string; display_name: string; ltp: number; change_percent: number; volume?: number }[] = [];

function getPlatformShortcutKey(): string {
  if (typeof window === 'undefined') return 'Ctrl+K';
  const isMac = /(Mac|iPhone|iPod|iPad)/i.test(navigator.userAgent);
  return isMac ? '⌘K' : 'Ctrl+K';
}

export function CommandPalette({
  open,
  onClose,
  onOpenDiagnostics,
  onToggleTicker,
  tickerVisible,
}: CommandPaletteProps) {
  const router = useRouter();
  const [query, setQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<PaletteCategory>('all');
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listContainerRef = useRef<HTMLDivElement>(null);
  const live = useOptionalLiveMarketContext();
  const cards = live?.cards ?? EMPTY_CARDS;
  const [shortcutKey] = useState<string>(getPlatformShortcutKey);

  // Autofocus input when dialog mounts/opens
  useEffect(() => {
    if (open) {
      const t = setTimeout(() => inputRef.current?.focus(), 40);
      return () => clearTimeout(t);
    }
  }, [open]);

  // Handle category change
  const handleCategoryChange = useCallback((cat: PaletteCategory) => {
    setSelectedCategory(cat);
    setActiveIndex(0);
  }, []);

  // Build items list
  const allItems: PaletteItem[] = useMemo(() => {
    const q = query.trim().toLowerCase();
    const match = (hay: string) => !q || hay.toLowerCase().includes(q);
    const out: PaletteItem[] = [];

    const groupOf = (href: string): string => {
      if (STANDALONE_ITEMS.some((i) => i.href === href)) return 'Overview';
      for (const g of NAV_GROUPS) if (g.items.some((i) => i.href === href)) return g.label;
      if (BOTTOM_ITEMS.some((i) => i.href === href)) return 'System';
      return 'Terminal Pages';
    };

    // 1. Pages / Screens
    for (const nav of ALL_NAV_ITEMS) {
      const hay = `${nav.label} ${nav.description ?? ''} ${(nav.keywords ?? []).join(' ')} ${nav.href} ${groupOf(nav.href)}`;
      if (match(hay)) {
        const NavIcon = nav.icon;
        out.push({
          key: `page:${nav.href}`,
          category: 'pages',
          section: groupOf(nav.href),
          label: nav.label,
          sub: `${nav.description ?? nav.href}${nav.shortcut ? ` • ${nav.shortcut}` : ''}`,
          href: nav.href,
          badge: nav.shortcut ?? nav.badge,
          icon: <NavIcon className="w-3.5 h-3.5 text-primary" />,
        });
      }
    }

    // 2. Live Market Symbols
    for (const c of (cards ?? []).slice(0, 50)) {
      const hay = `${c.symbol} ${c.display_name ?? ''}`;
      if (match(hay)) {
        const changeVal = Number(c.change_percent) || 0;
        const isPos = changeVal > 0;
        const isNeutral = changeVal === 0;
        out.push({
          key: `sym:${c.symbol}`,
          category: 'symbols',
          section: 'Market Instruments',
          label: c.display_name || c.symbol,
          sub: `${c.symbol} • LTP ${safeNum(Number(c.ltp))} ${c.volume ? `• Vol ${safeInt(c.volume)}` : ''}`,
          badge: `${isPos ? '+' : ''}${changeVal.toFixed(2)}%`,
          badgeTone: isNeutral ? 'muted' : isPos ? 'emerald' : 'rose',
          href: `/markets?symbol=${encodeURIComponent(c.symbol)}`,
          icon: <TrendingUp className="w-3.5 h-3.5 text-blue-500" />,
        });
      }
    }

    // 3. Quick Actions
    const actions: PaletteItem[] = [
      {
        key: 'act:diag',
        category: 'actions',
        section: 'Terminal Actions',
        label: 'Ingestion Diagnostics',
        sub: 'Inspect broker latency, reconnect counts & feed stream telemetry',
        action: onOpenDiagnostics,
        icon: <Activity className="w-3.5 h-3.5 text-amber-500" />,
      },
      ...(onToggleTicker
        ? [
            {
              key: 'act:ticker',
              category: 'actions' as const,
              section: 'Terminal Actions',
              label: tickerVisible ? 'Hide Market Ticker Marquee' : 'Show Market Ticker Marquee',
              sub: 'Toggle bottom market indices marquee stream',
              action: onToggleTicker,
              badge: tickerVisible ? 'Visible' : 'Hidden',
              badgeTone: 'muted' as const,
              icon: <BarChart2 className="w-3.5 h-3.5 text-emerald-500" />,
            },
          ]
        : []),
      {
        key: 'act:signals',
        category: 'actions',
        section: 'Terminal Actions',
        label: 'Live Signal Scanner',
        sub: 'Inspect real-time quant signals, momentum triggers & audit logs',
        href: '/signals',
        icon: <Radio className="w-3.5 h-3.5 text-emerald-500" />,
      },
      {
        key: 'act:ai',
        category: 'actions',
        section: 'Terminal Actions',
        label: 'AI Deep Insights Briefing',
        sub: 'Launch generative market synthesis, multi-TF bias & scenario tree',
        href: '/ai-analysis',
        icon: <Sparkles className="w-3.5 h-3.5 text-purple-500" />,
      },
      {
        key: 'act:settings',
        category: 'actions',
        section: 'Terminal Actions',
        label: 'Terminal & Broker Settings',
        sub: 'Configure broker API credentials, risk limits & models',
        href: '/settings',
        icon: <Settings className="w-3.5 h-3.5 text-slate-500" />,
      },
    ];

    for (const a of actions) {
      if (match(`${a.label} ${a.sub ?? ''}`)) {
        out.push(a);
      }
    }

    return out;
  }, [query, cards, onOpenDiagnostics, onToggleTicker, tickerVisible]);

  // Filter items by category tab
  const filteredItems = useMemo(() => {
    if (selectedCategory === 'all') return allItems.slice(0, 45);
    return allItems.filter((i) => i.category === selectedCategory).slice(0, 45);
  }, [allItems, selectedCategory]);

  const runItem = useCallback(
    (item: PaletteItem) => {
      onClose();
      if (item.action) {
        item.action();
      } else if (item.href) {
        router.push(item.href);
      }
    },
    [onClose, router],
  );

  // Keyboard navigation
  useEffect(() => {
    if (!open) return;

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActiveIndex((i) => (filteredItems.length === 0 ? 0 : Math.min(i + 1, filteredItems.length - 1)));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActiveIndex((i) => (filteredItems.length === 0 ? 0 : Math.max(i - 1, 0)));
      } else if (e.key === 'Enter') {
        e.preventDefault();
        const item = filteredItems[activeIndex];
        if (item) runItem(item);
      }
    };

    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, filteredItems, activeIndex, onClose, runItem]);

  // Scroll active item into view
  useEffect(() => {
    if (!listContainerRef.current) return;
    const activeEl = listContainerRef.current.querySelector(`[data-index="${activeIndex}"]`);
    if (activeEl) {
      activeEl.scrollIntoView({ block: 'nearest' });
    }
  }, [activeIndex]);

  if (!open) return null;

  let lastSection = '';

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[10vh] sm:pt-[12vh] bg-slate-950/40 backdrop-blur-xs p-3 sm:p-4 animate-in fade-in duration-150"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-label="Global search and command palette"
    >
      <div className="w-full max-w-xl rounded-xl border border-border bg-card shadow-2xl overflow-hidden flex flex-col max-h-[80vh] animate-in zoom-in-95 duration-150">
        {/* Search Input Bar */}
        <div className="flex items-center gap-2.5 px-3.5 py-1.5 border-b border-border bg-card shrink-0">
          <Search className="w-4 h-4 text-primary shrink-0" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActiveIndex(0);
            }}
            placeholder="Type a symbol (NIFTY, RELIANCE), page, or command…"
            className="flex-1 h-10 bg-transparent outline-none text-sm text-foreground placeholder:text-muted-foreground"
            aria-label="Search command input"
          />
          {query && (
            <button
              type="button"
              onClick={() => {
                setQuery('');
                setActiveIndex(0);
                inputRef.current?.focus();
              }}
              className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-secondary cursor-pointer"
              title="Clear search"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
          <kbd className="hidden sm:inline-flex items-center text-[10px] font-mono px-1.5 py-0.5 rounded border border-border bg-muted text-muted-foreground">
            ESC
          </kbd>
        </div>

        {/* Category Tabs */}
        <div className="flex items-center gap-1 px-3 py-1.5 border-b border-border/70 bg-secondary/30 shrink-0 overflow-x-auto text-xs">
          {(
            [
              { id: 'all', label: 'All Results' },
              { id: 'symbols', label: 'Instruments' },
              { id: 'pages', label: 'Desks & Pages' },
              { id: 'actions', label: 'Actions' },
            ] as const
          ).map((cat) => (
            <button
              key={cat.id}
              type="button"
              onClick={() => handleCategoryChange(cat.id)}
              className={cn(
                'px-2.5 py-1 rounded-md text-xs font-medium transition-colors cursor-pointer shrink-0',
                selectedCategory === cat.id
                  ? 'bg-card text-foreground shadow-2xs border border-border/80 font-semibold'
                  : 'text-muted-foreground hover:text-foreground hover:bg-secondary/60',
              )}
            >
              {cat.label}
            </button>
          ))}
          <span className="ml-auto text-[11px] text-muted-foreground font-mono shrink-0 pl-2">
            {filteredItems.length} {filteredItems.length === 1 ? 'item' : 'items'}
          </span>
        </div>

        {/* Results List */}
        <div ref={listContainerRef} className="flex-1 overflow-y-auto p-1.5 divide-y divide-border/20">
          {filteredItems.length === 0 ? (
            <div className="text-center py-10 px-4">
              <p className="text-sm font-semibold text-foreground">No matches found</p>
              <p className="text-xs text-muted-foreground mt-1 max-w-sm mx-auto">
                No items matching “{query}”. Try searching for NIFTY, Options, Diagnostics, or Signals.
              </p>
            </div>
          ) : (
            filteredItems.map((item, idx) => {
              const showHeader = selectedCategory === 'all' && item.section !== lastSection;
              if (showHeader) lastSection = item.section;
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
                    data-index={idx}
                    onMouseEnter={() => setActiveIndex(idx)}
                    onClick={() => runItem(item)}
                    className={cn(
                      'w-full flex items-center justify-between gap-3 px-2.5 py-2 rounded-lg text-left transition-colors cursor-pointer',
                      active ? 'bg-secondary text-foreground font-medium' : 'text-muted-foreground hover:bg-secondary/60',
                    )}
                  >
                    <div className="flex items-center gap-2.5 min-w-0 flex-1">
                      <div className="p-1 rounded bg-card border border-border/60 shrink-0">
                        {item.icon || <Search className="w-3.5 h-3.5 text-muted-foreground" />}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-semibold text-foreground truncate">{item.label}</span>
                          {item.badge && (
                            <span
                              className={cn(
                                'text-[10px] font-semibold px-1.5 py-0.2 rounded border shrink-0',
                                item.badgeTone === 'emerald' && 'bg-emerald-50 text-emerald-700 border-emerald-200',
                                item.badgeTone === 'rose' && 'bg-rose-50 text-rose-700 border-rose-200',
                                item.badgeTone === 'amber' && 'bg-amber-50 text-amber-800 border-amber-200',
                                item.badgeTone === 'blue' && 'bg-blue-50 text-blue-700 border-blue-200',
                                (!item.badgeTone || item.badgeTone === 'muted') &&
                                  'bg-secondary text-muted-foreground border-border',
                              )}
                            >
                              {item.badge}
                            </span>
                          )}
                        </div>
                        {item.sub && <span className="block text-[11px] text-muted-foreground truncate">{item.sub}</span>}
                      </div>
                    </div>

                    <ArrowRight
                      className={cn(
                        'w-3.5 h-3.5 shrink-0 transition-opacity',
                        active ? 'opacity-100 text-primary' : 'opacity-30',
                      )}
                    />
                  </button>
                </div>
              );
            })
          )}
        </div>

        {/* Footer Bar */}
        <div className="flex items-center gap-3 px-3 py-2 border-t border-border bg-secondary/30 text-[10px] text-muted-foreground shrink-0">
          <span>
            <kbd className="font-mono">↑↓</kbd> navigate
          </span>
          <span>
            <kbd className="font-mono">↵</kbd> open
          </span>
          <span>
            <kbd className="font-mono">Esc</kbd> close
          </span>
          <span className="ml-auto hidden sm:inline">
            <kbd className="font-mono">{shortcutKey}</kbd> toggle
          </span>
        </div>
      </div>
    </div>
  );
}

export const MemoizedCommandPalette = memo(CommandPalette);
