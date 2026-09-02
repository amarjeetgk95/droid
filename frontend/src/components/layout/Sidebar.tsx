'use client';

import { useState, useEffect, useCallback, useMemo, memo } from 'react';
import Link from 'next/link';
import { useRouter, usePathname } from 'next/navigation';
import {
  ChevronDown,
  LayoutDashboard,
  Sparkles,
  Star,
  Layers,
  Activity,
  Coins,
} from 'lucide-react';
import { getStoredSettings } from '@/lib/settings';
import { cn } from '@/lib/utils';
import {
  NAV_GROUPS,
  STANDALONE_ITEMS,
  BOTTOM_ITEMS,
  ALL_NAV_ITEMS,
  isGroupActive,
  isActivePath,
  NavGroup,
  NavItem,
} from './nav-config';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { SidebarHeader } from './Sidebar/SidebarHeader';
import { SidebarFilter } from './Sidebar/SidebarFilter';
import { SidebarFavorites } from './Sidebar/SidebarFavorites';
import { SidebarFlyout } from './Sidebar/SidebarFlyout';
import { SidebarStatusDock } from './Sidebar/SidebarStatusDock';
import { useMarketDataContext } from '@/context/MarketDataContext';

// ---------------------------------------------------------------------------
// Storage keys & helpers
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
function loadGroupState(): Record<string, boolean> | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(SIDEBAR_GROUPS_KEY);
    return raw ? (JSON.parse(raw) as Record<string, boolean>) : null;
  } catch {
    return null;
  }
}
function saveGroupState(state: Record<string, boolean>) {
  try {
    localStorage.setItem(SIDEBAR_GROUPS_KEY, JSON.stringify(state));
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
// Reusable NavLink Item — memoized to avoid re-render on every pathname tick
// ---------------------------------------------------------------------------
const NavLink = memo(function NavLink({
  item,
  active,
  collapsed,
  onNavigate,
  badgeData,
}: {
  item: NavItem;
  active: boolean;
  collapsed?: boolean;
  onNavigate?: () => void;
  badgeData?: { label: string; color: string; pulse?: boolean };
}) {
  const Icon = item.icon;

  const content = (
    <Link
      href={item.href}
      aria-current={active ? 'page' : undefined}
      onClick={onNavigate}
      className={cn(
        'group relative flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-xs font-medium transition-all duration-150 ease-out',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-0',
        collapsed
          ? 'justify-center w-10 h-10 mx-auto'
          : 'w-full',
        active
          ? collapsed
            ? 'bg-primary text-primary-foreground shadow-sm ring-1 ring-primary/30'
            : 'bg-primary/10 text-primary font-semibold ring-1 ring-primary/15 dark:bg-primary/15'
          : 'text-muted-foreground hover:bg-accent/70 hover:text-foreground',
      )}
    >
      {/* Active left accent when expanded */}
      {active && !collapsed && (
        <span className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-0.5 rounded-full bg-primary" aria-hidden />
      )}

      <Icon
        className={cn(
          'shrink-0 transition-all duration-150',
          collapsed ? 'w-5 h-5' : 'w-4 h-4',
          active
            ? collapsed
              ? 'text-primary-foreground'
              : 'text-primary'
            : 'opacity-80 group-hover:opacity-100 group-hover:text-foreground',
        )}
      />

      {!collapsed && (
        <div className="flex flex-1 items-center justify-between min-w-0">
          <div className="flex flex-col min-w-0">
            <span className="truncate leading-tight">{item.label}</span>
          </div>

          <div className="flex items-center gap-1.5 shrink-0 ml-1">
            {badgeData ? (
              <span
                className={cn(
                  'text-[9px] font-bold px-1.5 py-0.2 rounded-full border leading-tight flex items-center gap-1',
                  badgeData.color,
                )}
              >
                {badgeData.pulse && (
                  <span className="inline-block h-1.5 w-1.5 rounded-full bg-current animate-pulse" />
                )}
                {badgeData.label}
              </span>
            ) : item.shortcut ? (
              <kbd className="hidden group-hover:inline-flex text-[9px] font-mono px-1 py-0.2 rounded bg-muted/70 text-muted-foreground border border-border/40">
                {item.shortcut}
              </kbd>
            ) : null}
          </div>
        </div>
      )}
    </Link>
  );

  if (!collapsed) return content;

  return (
    <Tooltip delayDuration={150}>
      <TooltipTrigger asChild>{content}</TooltipTrigger>
      <TooltipContent side="right" sideOffset={10} className="flex flex-col gap-0.5 max-w-[200px]">
        <div className="flex items-center justify-between gap-2">
          <span className="font-semibold text-xs">{item.label}</span>
          {item.shortcut && (
            <kbd className="text-[9px] font-mono px-1 py-0.2 rounded bg-muted text-muted-foreground border">
              {item.shortcut}
            </kbd>
          )}
        </div>
        {item.description && <span className="text-[10px] text-muted-foreground">{item.description}</span>}
      </TooltipContent>
    </Tooltip>
  );
});

// ---------------------------------------------------------------------------
// Group Accordion Header — memoized
// ---------------------------------------------------------------------------
const GroupHeader = memo(function GroupHeader({
  label,
  icon: Icon,
  open,
  activeGroup,
  onToggle,
  id,
}: {
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  open: boolean;
  activeGroup: boolean;
  onToggle: () => void;
  id: string;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      aria-controls={`nav-group-${id}`}
      className={cn(
        'w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-[10px] font-bold tracking-wider uppercase transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        activeGroup
          ? 'text-foreground font-extrabold bg-accent/40'
          : 'text-muted-foreground/80 hover:bg-accent/40 hover:text-foreground',
      )}
    >
      <Icon className={cn('w-3.5 h-3.5 shrink-0', activeGroup ? 'text-primary' : 'opacity-70')} />
      <span className="flex-1 text-left truncate">{label}</span>
      <ChevronDown
        className={cn(
          'w-3 h-3 shrink-0 opacity-60 transition-transform duration-200',
          open && 'rotate-180 opacity-100',
        )}
      />
    </button>
  );
});

// ---------------------------------------------------------------------------
// Main Enterprise Sidebar
// ---------------------------------------------------------------------------
export function Sidebar({
  collapsed: controlledCollapsed,
  onCollapsedChange,
  mobileOpen: controlledMobileOpen,
  onMobileOpenChange,
}: SidebarProps) {
  const router = useRouter();
  const pathname = usePathname();

  // Context market telemetry
  let marketCtx: ReturnType<typeof useMarketDataContext> | null = null;
  try {
    marketCtx = useMarketDataContext();
  } catch {}

  const streamState = marketCtx?.streamState ?? 'CONNECTED';

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
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});

  // Telemetry Badges — no pulse (single LIVE dot is in TopHeader)
  const telemetryBadges = useMemo(() => {
    return {
      signals: { label: '+3 LIVE', color: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/30', pulse: false },
      algo: { label: '2 RUNNING', color: 'bg-blue-500/10 text-blue-600 border-blue-500/30', pulse: false },
      ai: { label: 'SYNC', color: 'bg-purple-500/10 text-purple-600 border-purple-500/30', pulse: false },
      broker: { label: 'ONLINE', color: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/30', pulse: false },
    };
  }, []);

  // Hydrate settings and group state
  useEffect(() => {
    try {
      const s = getStoredSettings();
      setApiType(s.broker.apiType);
      setBrokerProvider(s.broker.provider);
    } catch {}
    const stored = loadGroupState();
    if (stored) {
      setOpenGroups(stored);
    } else {
      const initial: Record<string, boolean> = {};
      for (const g of NAV_GROUPS) initial[g.id] = g.defaultOpen ?? false;
      setOpenGroups(initial);
    }
    if (controlledCollapsed === undefined) {
      setInternalCollapsed(loadCollapsed());
    }
    const onStorage = (e: StorageEvent) => {
      if (e.key === SIDEBAR_COLLAPSED_KEY && controlledCollapsed === undefined) {
        setInternalCollapsed(e.newValue === '1');
      }
      if (e.key === SIDEBAR_GROUPS_KEY && e.newValue) {
        try {
          setOpenGroups(JSON.parse(e.newValue));
        } catch {}
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

  // Auto-open group containing active route
  useEffect(() => {
    setOpenGroups((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const g of NAV_GROUPS) {
        if (isGroupActive(pathname, g) && !next[g.id]) {
          next[g.id] = true;
          changed = true;
        }
        if (!(g.id in next)) {
          next[g.id] = g.defaultOpen ?? false;
          changed = true;
        }
      }
      if (changed) {
        saveGroupState(next);
        return next;
      }
      return prev;
    });
  }, [pathname]);

  // Keyboard Shortcuts: Cmd/Ctrl+B (toggle sidebar), Cmd/Ctrl+1..5 (jump to top tools)
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const isInput = ['INPUT', 'TEXTAREA', 'SELECT'].includes((e.target as HTMLElement)?.tagName);

      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'b') {
        e.preventDefault();
        if (window.innerWidth >= 768) setCollapsed((p) => !p);
        else setMobileOpen(!mobileOpen);
      }

      // Quick jumps: Cmd+1 to Cmd+5 when not typing in an input
      if ((e.metaKey || e.ctrlKey) && !isInput) {
        const num = parseInt(e.key, 10);
        if (num >= 1 && num <= 5) {
          const targetItem = ALL_NAV_ITEMS.find((item) => item.shortcut === `⌘${num}`);
          if (targetItem) {
            e.preventDefault();
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

  // Body scroll lock when mobile drawer open
  useEffect(() => {
    if (mobileOpen) {
      const prev = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
      return () => {
        document.body.style.overflow = prev;
      };
    }
  }, [mobileOpen]);

  const toggleGroup = useCallback((id: string) => {
    setOpenGroups((p) => {
      const next = { ...p, [id]: !p[id] };
      saveGroupState(next);
      return next;
    });
  }, []);

  const handleNavigate = useCallback(() => {
    if (mobileOpen) setMobileOpen(false);
  }, [mobileOpen, setMobileOpen]);

  const dashboardItem = STANDALONE_ITEMS[0];

  // -----------------------------------------------------------------------
  // Shared Nav Content Renderer
  // -----------------------------------------------------------------------
  const NavContent = ({ isCollapsed, isMobile }: { isCollapsed: boolean; isMobile?: boolean }) => (
    <div className="flex h-full flex-col select-none">
      {/* 1. Header & Desk Switcher */}
      <SidebarHeader
        collapsed={isCollapsed}
        isMobile={isMobile}
        onToggleCollapse={() => setCollapsed((p) => !p)}
        onCloseMobile={() => setMobileOpen(false)}
      />

      {/* 2. Fast Navigation Filter */}
      <SidebarFilter
        collapsed={isCollapsed}
        onNavigate={handleNavigate}
        onExpand={() => setCollapsed(false)}
      />

      {/* 3. Main Nav Scroll Area */}
      <ScrollArea className="flex-1 overflow-hidden">
        <nav
          aria-label="Primary"
          className={cn(
            'flex flex-col gap-2 p-2',
            isCollapsed && !isMobile && 'gap-2 items-center px-1.5',
          )}
        >
          {/* Dashboard Direct Link */}
          <NavLink
            item={dashboardItem}
            active={isActivePath(pathname, dashboardItem.href)}
            collapsed={isCollapsed && !isMobile}
            onNavigate={handleNavigate}
          />

          {/* Pinned Favorites */}
          <SidebarFavorites
            collapsed={isCollapsed && !isMobile}
            onNavigate={handleNavigate}
          />

          <Separator className="my-0.5 opacity-60" />

          {/* Navigation Groups */}
          <div className={cn('flex flex-col gap-1.5', isCollapsed && !isMobile && 'w-full items-center gap-1.5')}>
            {NAV_GROUPS.map((group) => {
              const Icon = group.icon;
              const open = openGroups[group.id] ?? group.defaultOpen ?? false;
              const activeGroup = isGroupActive(pathname, group);

              // Collapsed Rail Mode: Sleek Flyout Popover
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

              // Expanded Mode: Smooth Accordion
              return (
                <div key={group.id} className="flex flex-col gap-0.5">
                  <GroupHeader
                    id={group.id}
                    label={group.label}
                    icon={Icon}
                    open={open}
                    activeGroup={activeGroup}
                    onToggle={() => toggleGroup(group.id)}
                  />

                  <div
                    id={`nav-group-${group.id}`}
                    className={cn(
                      'grid transition-all duration-200 ease-out',
                      open ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0 pointer-events-none',
                    )}
                  >
                    <div className="overflow-hidden">
                      <div className="ml-2 pl-2 border-l border-border/60 flex flex-col gap-0.5 py-0.5">
                        {group.items.map((item) => {
                          const active = isActivePath(pathname, item.href);
                          const badgeData = item.badgeKey ? telemetryBadges[item.badgeKey] : undefined;
                          return (
                            <NavLink
                              key={item.href}
                              item={item}
                              active={active}
                              onNavigate={handleNavigate}
                              badgeData={badgeData}
                            />
                          );
                        })}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </nav>
      </ScrollArea>

      {/* 4. Bottom Operational Status Dock */}
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
    <TooltipProvider delayDuration={200}>
      {/* Desktop Persistent Sidebar */}
      <aside
        aria-label="Primary navigation"
        className={cn(
          'hidden md:flex shrink-0 flex-col border-r border-border bg-card transition-[width] duration-200 ease-out will-change-transform overflow-hidden shadow-sm [contain:paint]',
          collapsed ? 'w-[68px]' : 'w-64 lg:w-[268px]',
        )}
        style={{ contentVisibility: 'auto', containIntrinsicSize: '0 600px' } as React.CSSProperties}
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
        {/* Backdrop — no blur for perf */}
        <div
          onClick={() => setMobileOpen(false)}
          className={cn(
            'absolute inset-0 bg-black/50 transition-opacity duration-200',
            mobileOpen ? 'opacity-100' : 'opacity-0',
          )}
        />
        {/* Slide-out Drawer Panel */}
        <aside
          aria-label="Primary navigation"
          className={cn(
            'absolute left-0 top-0 h-full w-[84vw] max-w-[320px] bg-card border-r border-border shadow-sm flex flex-col transition-transform duration-300 ease-out will-change-transform',
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
