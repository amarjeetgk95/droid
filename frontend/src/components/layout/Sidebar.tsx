'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { ChevronDown } from 'lucide-react';
import { getStoredSettings } from '@/lib/settings';
import { cn } from '@/lib/utils';
import {
  NAV_GROUPS,
  STANDALONE_ITEMS,
  ALL_NAV_ITEMS,
  isActivePath,
  isGroupActive,
} from './nav-config';
import { TooltipProvider } from '@/components/ui/tooltip';
import { SidebarHeader, SidebarNavItem, SidebarFlyout, SidebarStatusDock } from './Sidebar/index';
import { useOptionalMarketDataContext } from '@/context/MarketDataContext';
import { useOptionalLiveMarketContext } from '@/context/LiveMarketContext';
import { navigationController } from '@/lib/navigationController';

// ---------------------------------------------------------------------------
// Storage key & helpers
// ---------------------------------------------------------------------------
const SIDEBAR_COLLAPSED_KEY = 'droid:sidebar:collapsed';
const SIDEBAR_GROUPS_KEY = 'droid:sidebar:groups';

function loadCollapsed(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1';
  } catch {
    return false;
  }
}

function saveCollapsed(v: boolean) {
  try {
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, v ? '1' : '0');
  } catch {}
}

function defaultGroupOpen(): Record<string, boolean> {
  const out: Record<string, boolean> = {};
  for (const g of NAV_GROUPS) out[g.id] = g.defaultOpen !== false;
  return out;
}

function loadGroupOpen(): Record<string, boolean> {
  const fallback = defaultGroupOpen();
  if (typeof window === 'undefined') return fallback;
  try {
    const raw = localStorage.getItem(SIDEBAR_GROUPS_KEY);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Record<string, boolean>;
    return { ...fallback, ...parsed };
  } catch {
    return fallback;
  }
}

function saveGroupOpen(v: Record<string, boolean>) {
  try {
    localStorage.setItem(SIDEBAR_GROUPS_KEY, JSON.stringify(v));
  } catch {}
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
export type SidebarProps = {
  collapsed?: boolean;
  onCollapsedChange?: (collapsed: boolean) => void;
  mobileOpen?: boolean;
  onMobileOpenChange?: (open: boolean) => void;
};

// ---------------------------------------------------------------------------
// Main Confined, Zero-Scroll Side Navigation Bar
// ---------------------------------------------------------------------------
export function Sidebar({
  collapsed: controlledCollapsed,
  onCollapsedChange,
  mobileOpen: controlledMobileOpen,
  onMobileOpenChange,
}: SidebarProps) {
  const router = useRouter();
  const pathname = usePathname();

  // Telemetry / stream health — prefer LiveMarket (stable health context),
  // fall back to Dashboard context for isolated usage.
  let streamState: import('@/hooks/useMarketStream').StreamConnectionState = 'CONNECTED';
  try {
    streamState = useOptionalLiveMarketContext()?.streamState ?? useOptionalMarketDataContext()?.streamState ?? 'CONNECTED';
  } catch {
    streamState = 'CONNECTED';
  }

  // Collapsed state
  const [internalCollapsed, setInternalCollapsed] = useState<boolean>(() => loadCollapsed());
  const collapsed = controlledCollapsed ?? internalCollapsed;
  const setCollapsed = useCallback(
    (next: boolean | ((prev: boolean) => boolean)) => {
      const value = typeof next === 'function' ? (next as (p: boolean) => boolean)(collapsed) : next;
      if (onCollapsedChange) onCollapsedChange(value);
      else setInternalCollapsed(value);
      saveCollapsed(value);
    },
    [collapsed, onCollapsedChange],
  );

  // Mobile state
  const [internalMobileOpen, setInternalMobileOpen] = useState(false);
  const mobileOpen = controlledMobileOpen ?? internalMobileOpen;
  const setMobileOpen = useCallback(
    (v: boolean) => {
      if (onMobileOpenChange) onMobileOpenChange(v);
      else setInternalMobileOpen(v);
    },
    [onMobileOpenChange],
  );

  const [apiType, setApiType] = useState<string>('indian');
  const [brokerProvider, setBrokerProvider] = useState<string>('fyers');
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>(() => loadGroupOpen());

  const toggleGroup = useCallback((id: string) => {
    setOpenGroups((prev) => {
      const next = { ...prev, [id]: !prev[id] };
      saveGroupOpen(next);
      return next;
    });
  }, []);

  // Auto-expand the group that contains the current page (e.g. deep-link reload)
  // Intentional external->state sync on route change.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => {
    const active = NAV_GROUPS.find((g) => isGroupActive(pathname, g));
    if (active) {
      setOpenGroups((prev) => {
        if (prev[active.id]) return prev;
        const next = { ...prev, [active.id]: true };
        saveGroupOpen(next);
        return next;
      });
    }
  }, [pathname]);

  // Truthful telemetry badges — derived from real stream state, never fake.
  // Signals/AI counts will be wired when a global engine context lands;
  // until then show connection truth (LIVE / SYNC / OFF).
  const telemetryBadges = useMemo(() => {
    const live = streamState === 'CONNECTED';
    const syncing = streamState === 'CONNECTING' || streamState === 'RECONNECTING';
    const dot = live
      ? { label: 'LIVE', color: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/30', pulse: true }
      : syncing
        ? { label: 'SYNC', color: 'bg-amber-500/10 text-amber-600 border-amber-500/30', pulse: true }
        : { label: 'OFF', color: 'bg-rose-500/10 text-rose-600 border-rose-500/30', pulse: false };
    return {
      signals: dot,
      ai: live
        ? { label: 'READY', color: 'bg-purple-500/10 text-purple-600 border-purple-500/30', pulse: false }
        : syncing
          ? { label: 'SYNC', color: 'bg-amber-500/10 text-amber-600 border-amber-500/30', pulse: true }
          : { label: 'OFF', color: 'bg-rose-500/10 text-rose-600 border-rose-500/30', pulse: false },
      broker: live
        ? { label: 'ONLINE', color: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/30', pulse: false }
        : syncing
          ? { label: 'SYNC', color: 'bg-amber-500/10 text-amber-600 border-amber-500/30', pulse: true }
          : { label: 'OFFLINE', color: 'bg-rose-500/10 text-rose-600 border-rose-500/30', pulse: false },
    };
  }, [streamState]);

  // Hydrate settings
  useEffect(() => {
    try {
      const s = getStoredSettings();
      setApiType(s.broker.apiType);
      setBrokerProvider(s.broker.provider);
    } catch {}

    if (controlledCollapsed === undefined) {
      setInternalCollapsed(loadCollapsed());
    }

    const onStorage = (e: StorageEvent) => {
      if (e.key === SIDEBAR_COLLAPSED_KEY && controlledCollapsed === undefined) {
        setInternalCollapsed(e.newValue === '1');
      }
      if (e.key === 'droid_app_settings_v1') {
        try {
          const s = getStoredSettings();
          setApiType(s.broker.apiType);
          setBrokerProvider(s.broker.provider);
        } catch {}
      }
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, [controlledCollapsed]);

  // Keyboard Shortcuts: Cmd/Ctrl+B (toggle sidebar), Cmd/Ctrl+1..0 + Cmd+, (quick jumps)
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      const isInput =
        tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target?.isContentEditable;

      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'b') {
        e.preventDefault();
        if (window.innerWidth >= 768) setCollapsed((p) => !p);
        else setMobileOpen(!mobileOpen);
      }

      // Quick jumps when not typing: Cmd+1..9, Cmd+0, Cmd+,
      if ((e.metaKey || e.ctrlKey) && !isInput) {
        let shortcut: string | null = null;
        if (e.key >= '0' && e.key <= '9') shortcut = `⌘${e.key}`;
        else if (e.key === ',') shortcut = '⌘,';
        if (shortcut) {
          const targetItem = ALL_NAV_ITEMS.find((item) => item.shortcut === shortcut);
          if (targetItem) {
            e.preventDefault();
            navigationController.start();
            router.push(targetItem.href);
          }
        }
      }

      if (e.key === 'Escape' && mobileOpen) {
        setMobileOpen(false);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [mobileOpen, setCollapsed, setMobileOpen, router]);

  // Prevent body scroll when mobile drawer is open
  useEffect(() => {
    if (mobileOpen) {
      const prev = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
      return () => {
        document.body.style.overflow = prev;
      };
    }
  }, [mobileOpen]);

  const handleNavigate = useCallback(() => {
    if (mobileOpen) setMobileOpen(false);
  }, [mobileOpen, setMobileOpen]);

  const dashboardItem = STANDALONE_ITEMS[0];

  // -----------------------------------------------------------------------
  // Shared Navigation Content (scroll-safe, collapsible groups)
  // -----------------------------------------------------------------------
  const NavContent = ({ isCollapsed, isMobile }: { isCollapsed: boolean; isMobile?: boolean }) => (
    <div className="flex h-full min-h-0 flex-col select-none">
      {/* 1. Header (Brand + Pulse + Collapse toggle) */}
      <SidebarHeader
        collapsed={isCollapsed}
        isMobile={isMobile}
        streamState={streamState}
        onToggleCollapse={() => setCollapsed((p) => !p)}
        onCloseMobile={() => setMobileOpen(false)}
      />

      {/* 2. Main Navigation Items (scrolls when short viewport) */}
      <nav
        aria-label="Primary"
        className={cn(
          'flex-1 min-h-0 overflow-y-auto overscroll-contain flex flex-col gap-1 py-2 px-2 scrollbar-thin',
          isCollapsed && !isMobile && 'items-center px-1.5 overflow-y-auto overflow-x-hidden',
        )}
      >
        {/* Home */}
        <ul className={cn('flex flex-col gap-0.5', isCollapsed && !isMobile && 'items-center')}>
          <li>
            <SidebarNavItem
              item={dashboardItem}
              active={isActivePath(pathname, dashboardItem.href)}
              collapsed={isCollapsed && !isMobile}
              onNavigate={handleNavigate}
            />
          </li>
        </ul>

        {/* Workflow groups */}
        {NAV_GROUPS.map((group) => {
          // Collapsed rail: floating flyout
          if (isCollapsed && !isMobile) {
            return (
              <SidebarFlyout
                key={group.id}
                group={group}
                onNavigate={handleNavigate}
                telemetryBadges={telemetryBadges}
              />
            );
          }

          const isOpen = openGroups[group.id] !== false;
          const groupActive = isGroupActive(pathname, group);

          // Expanded / mobile: collapsible section
          return (
            <section key={group.id} aria-labelledby={`sidebar-group-${group.id}`} className="flex flex-col mt-2 first:mt-1">
              <h2 id={`sidebar-group-${group.id}`} className="sr-only">
                {group.label}
              </h2>
              <button
                type="button"
                onClick={() => toggleGroup(group.id)}
                aria-expanded={isOpen}
                aria-controls={`sidebar-section-${group.id}`}
                className="group flex w-full items-center justify-between rounded-md px-2 py-1 text-[11px] font-semibold tracking-wider uppercase text-muted-foreground hover:text-foreground hover:bg-accent/50 transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span className="flex items-center gap-1.5 min-w-0">
                  {groupActive && (
                    <span className="h-1.5 w-1.5 rounded-full bg-primary shrink-0" aria-hidden />
                  )}
                  <span className="truncate">{group.label}</span>
                  <span className="text-[10px] font-mono font-normal opacity-60">{group.items.length}</span>
                </span>
                <ChevronDown
                  className={cn(
                    'w-3.5 h-3.5 shrink-0 opacity-60 transition-transform duration-150 group-hover:opacity-100',
                    !isOpen && '-rotate-90',
                  )}
                />
              </button>

              {isOpen && (
                <ul id={`sidebar-section-${group.id}`} className="flex flex-col gap-0.5 mt-0.5">
                  {group.items.map((item) => {
                    const active = isActivePath(pathname, item.href);
                    const badgeData = item.badgeKey ? telemetryBadges[item.badgeKey] : undefined;
                    return (
                      <li key={item.href}>
                        <SidebarNavItem
                          item={item}
                          active={active}
                          onNavigate={handleNavigate}
                          badgeData={badgeData}
                        />
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>
          );
        })}
      </nav>

      {/* 3. Bottom status dock (always visible) */}
      <SidebarStatusDock
        collapsed={isCollapsed}
        isMobile={isMobile}
        apiType={apiType}
        provider={brokerProvider}
        streamState={streamState}
        onExpand={() => setCollapsed(false)}
        onNavigate={handleNavigate}
      />
    </div>
  );

  return (
    <TooltipProvider delayDuration={150}>
      {/* Desktop Persistent Sidebar */}
      <aside
        aria-label="Primary navigation"
        className={cn(
          'hidden md:flex shrink-0 flex-col border-r border-border bg-card transition-[width] duration-200 ease-out will-change-transform overflow-hidden shadow-2xs select-none',
          collapsed ? 'w-[68px]' : 'w-64 lg:w-[268px]',
        )}
      >
        <NavContent isCollapsed={collapsed} />
      </aside>

      {/* Mobile Modal Drawer */}
      <div
        className={cn(
          'md:hidden fixed inset-0 z-50 transition',
          mobileOpen ? 'visible' : 'invisible pointer-events-none',
        )}
        aria-hidden={!mobileOpen}
      >
        {/* Backdrop */}
        <div
          onClick={() => setMobileOpen(false)}
          className={cn(
            'absolute inset-0 bg-black/50 transition-opacity duration-200',
            mobileOpen ? 'opacity-100' : 'opacity-0',
          )}
        />
        {/* Slide-out Drawer */}
        <aside
          aria-label="Primary navigation"
          className={cn(
            'absolute left-0 top-0 h-full w-[80vw] max-w-[300px] bg-card border-r border-border shadow-md flex flex-col transition-transform duration-300 ease-out will-change-transform',
            mobileOpen ? 'translate-x-0' : '-translate-x-full',
          )}
        >
          <NavContent isCollapsed={false} isMobile />
        </aside>
      </div>
    </TooltipProvider>
  );
}

export function useSidebarMobile() {
  const [open, setOpen] = useState(false);
  return { open, setOpen };
}
