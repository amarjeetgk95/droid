'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  ChevronDown,
  PanelLeftClose,
  PanelLeftOpen,
  X,
  Sparkles,
} from 'lucide-react';
import { getStoredSettings } from '@/lib/settings';
import { cn } from '@/lib/utils';
import {
  NAV_GROUPS,
  STANDALONE_ITEMS,
  BOTTOM_ITEMS,
  isGroupActive,
  isActivePath,
} from './nav-config';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';

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
// Reusable NavLink
// ---------------------------------------------------------------------------
function NavLink({
  href,
  label,
  icon: Icon,
  active,
  collapsed,
  onNavigate,
  description,
  badge,
  muted,
  tooltipSide = 'right',
}: {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  active: boolean;
  collapsed?: boolean;
  onNavigate?: () => void;
  description?: string;
  badge?: string;
  muted?: boolean;
  tooltipSide?: 'right' | 'left' | 'top' | 'bottom';
}) {
  const content = (
    <Link
      href={href}
      aria-current={active ? 'page' : undefined}
      onClick={onNavigate}
      className={cn(
        'group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-all duration-150 ease-out',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-0',
        collapsed
          ? 'justify-center px-2 py-2.5 w-10 h-10 mx-auto'
          : 'w-full',
        active
          ? collapsed
            ? 'bg-primary text-primary-foreground shadow-sm ring-1 ring-primary/20'
            : 'bg-primary/10 text-primary font-medium shadow-sm ring-1 ring-primary/10 dark:bg-primary/15'
          : muted
            ? 'text-muted-foreground/60 hover:bg-accent/40 hover:text-foreground'
            : 'text-muted-foreground hover:bg-accent hover:text-foreground',
      )}
    >
      {/* Active left accent when expanded */}
      {active && !collapsed && (
        <span className="absolute left-0 top-1/2 -translate-y-1/2 h-6 w-0.5 rounded-full bg-primary" aria-hidden />
      )}
      <Icon
        className={cn(
          'shrink-0 transition-colors',
          collapsed ? 'w-5 h-5' : 'w-4 h-4',
          active ? (collapsed ? 'text-primary-foreground' : 'text-primary') : 'group-hover:text-foreground',
        )}
      />
      {!collapsed && (
        <>
          <span className="flex-1 truncate text-left">{label}</span>
          {badge && (
            <span className="shrink-0 text-[10px] leading-none font-semibold px-1.5 py-0.5 rounded-full bg-muted border text-muted-foreground">
              {badge}
            </span>
          )}
        </>
      )}
    </Link>
  );

  if (!collapsed) return content;

  return (
    <Tooltip delayDuration={150}>
      <TooltipTrigger asChild>{content}</TooltipTrigger>
      <TooltipContent side={tooltipSide} sideOffset={8} className="flex flex-col gap-0.5">
        <span className="font-medium">{label}</span>
        {description && <span className="text-[11px] opacity-75">{description}</span>}
      </TooltipContent>
    </Tooltip>
  );
}

// ---------------------------------------------------------------------------
// Group header button
// ---------------------------------------------------------------------------
function GroupHeader({
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
        'w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold tracking-widest uppercase transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        activeGroup
          ? 'text-foreground bg-secondary/60'
          : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground',
      )}
    >
      <Icon className={cn('w-3.5 h-3.5 shrink-0', activeGroup && 'text-primary')} />
      <span className="flex-1 text-left truncate">{label}</span>
      <ChevronDown className={cn('w-3 h-3 shrink-0 transition-transform duration-200', open && 'rotate-180')} />
    </button>
  );
}

// ---------------------------------------------------------------------------
// Main Sidebar
// ---------------------------------------------------------------------------
export function Sidebar({
  collapsed: controlledCollapsed,
  onCollapsedChange,
  mobileOpen: controlledMobileOpen,
  onMobileOpenChange,
}: SidebarProps) {
  const pathname = usePathname();

  // collapsed state: controlled if provided, else internal
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

  // mobile drawer
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
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});

  // Sync apiType + hydrate collapsed/groups
  useEffect(() => {
    try {
      setApiType(getStoredSettings().broker.apiType);
    } catch {}
    const stored = loadGroupState();
    if (stored) {
      setOpenGroups(stored);
    } else {
      const initial: Record<string, boolean> = {};
      for (const g of NAV_GROUPS) initial[g.id] = g.defaultOpen ?? false;
      setOpenGroups(initial);
    }
    // also sync collapsed from storage if uncontrolled
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
        } catch {}
      }
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, [controlledCollapsed]);

  // Auto-open group containing active route, persist
  useEffect(() => {
    setOpenGroups((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const g of NAV_GROUPS) {
        if (isGroupActive(pathname, g) && !next[g.id]) {
          next[g.id] = true;
          changed = true;
        }
        // initialize missing groups with default
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

  // Persist openGroups
  useEffect(() => {
    if (Object.keys(openGroups).length) saveGroupState(openGroups);
  }, [openGroups]);

  // Keyboard: Cmd/Ctrl+B toggles collapsed (desktop only)
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'b') {
        e.preventDefault();
        if (window.innerWidth >= 768) setCollapsed((p) => !p);
        else setMobileOpen(!mobileOpen);
      }
      if (e.key === 'Escape' && mobileOpen) setMobileOpen(false);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [mobileOpen, setCollapsed, setMobileOpen]);

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

  // Derived: bottom items split
  const cryptoItem = useMemo(() => BOTTOM_ITEMS.find((i) => i.href === '/crypto')!, []);
  const settingsItem = useMemo(() => BOTTOM_ITEMS.find((i) => i.href === '/settings')!, []);
  const dashboardItem = STANDALONE_ITEMS[0];

  // -----------------------------------------------------------------------
  // Shared nav content
  // -----------------------------------------------------------------------
  const NavContent = ({ isCollapsed, isMobile }: { isCollapsed: boolean; isMobile?: boolean }) => (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className={cn('flex h-14 shrink-0 items-center gap-2 border-b border-border px-3', isCollapsed && !isMobile && 'justify-center px-2')}>
        <div className={cn('flex items-center gap-2 min-w-0', isCollapsed && !isMobile && 'justify-center')}>
          <div className="h-8 w-8 rounded-lg bg-primary flex items-center justify-center text-primary-foreground font-bold text-xs tracking-widest shadow-sm ring-1 ring-primary/20 shrink-0">
            D
          </div>
          {!isCollapsed && (
            <div className="flex items-center gap-2 min-w-0">
              <span className="font-bold tracking-tight text-sm">DROID</span>
              <span className="hidden lg:inline-flex items-center gap-1 text-[10px] font-semibold leading-none bg-muted border px-2 py-1 rounded-full text-muted-foreground">
                <Sparkles className="w-3 h-3 opacity-60" />
                PHASE 1
              </span>
            </div>
          )}
        </div>

        {/* Desktop collapse toggle */}
        {!isMobile && (
          <Tooltip delayDuration={200}>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={() => setCollapsed((p) => !p)}
                aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
                className={cn(
                  'inline-flex items-center justify-center rounded-md border border-transparent h-7 w-7 shrink-0',
                  'text-muted-foreground hover:text-foreground hover:bg-accent hover:border-border transition-colors',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                  isCollapsed && 'mx-auto',
                  !isCollapsed && 'ml-auto',
                )}
              >
                {isCollapsed ? <PanelLeftOpen className="w-4 h-4" /> : <PanelLeftClose className="w-4 h-4" />}
              </button>
            </TooltipTrigger>
            <TooltipContent side="right" sideOffset={10}>
              {isCollapsed ? 'Expand (⌘B)' : 'Collapse (⌘B)'}
            </TooltipContent>
          </Tooltip>
        )}

        {/* Mobile close */}
        {isMobile && (
          <button
            type="button"
            onClick={() => setMobileOpen(false)}
            aria-label="Close navigation"
            className="ml-auto inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-accent border border-transparent hover:border-border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Nav */}
      <ScrollArea className="flex-1 overflow-hidden">
        <nav aria-label="Primary" className={cn('flex flex-col gap-3 p-3', isCollapsed && !isMobile && 'p-2 gap-2 items-center')}>
          {/* Dashboard */}
          <NavLink
            href={dashboardItem.href}
            label={dashboardItem.label}
            icon={dashboardItem.icon}
            active={isActivePath(pathname, dashboardItem.href)}
            collapsed={isCollapsed && !isMobile}
            onNavigate={handleNavigate}
            description={dashboardItem.description}
          />

          {!isCollapsed && <Separator className="my-0.5 opacity-60" />}

          {/* Groups */}
          <div className={cn('flex flex-col gap-1', isCollapsed && !isMobile && 'w-full items-center gap-1')}>
            {NAV_GROUPS.map((group) => {
              const Icon = group.icon;
              const open = openGroups[group.id] ?? group.defaultOpen ?? false;
              const activeGroup = isGroupActive(pathname, group);

              // Collapsed rendering: flatten items as icons
              if (isCollapsed && !isMobile) {
                return (
                  <div key={group.id} className="flex flex-col items-center gap-1 w-full">
                    <div className="flex items-center justify-center w-full py-1">
                      <Tooltip delayDuration={150}>
                        <TooltipTrigger asChild>
                          <span className={cn('h-6 w-6 rounded-md flex items-center justify-center border', activeGroup ? 'bg-secondary border-border text-foreground' : 'bg-muted/50 border-transparent text-muted-foreground')}>
                            <Icon className="w-3.5 h-3.5" />
                          </span>
                        </TooltipTrigger>
                        <TooltipContent side="right" sideOffset={10}>
                          <span className="font-medium">{group.label}</span>
                        </TooltipContent>
                      </Tooltip>
                    </div>
                    {group.items.map((item) => (
                      <NavLink
                        key={item.href}
                        href={item.href}
                        label={item.label}
                        icon={item.icon}
                        active={isActivePath(pathname, item.href)}
                        collapsed
                        onNavigate={handleNavigate}
                        description={item.description}
                      />
                    ))}
                    <Separator className="my-1 w-6 opacity-60" />
                  </div>
                );
              }

              // Expanded
              return (
                <div key={group.id} className="flex flex-col gap-1">
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
                      <div className="ml-2 pl-3 border-l border-border/60 flex flex-col gap-0.5 py-0.5">
                        {group.items.map((item) => {
                          const ItemIcon = item.icon;
                          const active = isActivePath(pathname, item.href);
                          return (
                            <Link
                              key={item.href}
                              href={item.href}
                              aria-current={active ? 'page' : undefined}
                              onClick={handleNavigate}
                              className={cn(
                                'group relative flex items-center gap-2.5 rounded-md px-3 py-1.5 text-sm transition-colors duration-150',
                                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                                active
                                  ? 'bg-primary/10 text-primary font-medium ring-1 ring-primary/10 dark:bg-primary/15'
                                  : 'text-muted-foreground hover:bg-accent hover:text-foreground',
                              )}
                            >
                              {active && <span className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-0.5 rounded-full bg-primary" aria-hidden />}
                              <ItemIcon className={cn('w-4 h-4 shrink-0', active ? 'text-primary' : 'opacity-70 group-hover:opacity-100')} />
                              <span className="truncate">{item.label}</span>
                            </Link>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {!isCollapsed && <Separator className="opacity-60" />}

          {/* Crypto */}
          <div className={cn('flex flex-col gap-1', isCollapsed && !isMobile && 'w-full items-center')}>
            <NavLink
              href={cryptoItem.href}
              label={cryptoItem.label}
              icon={cryptoItem.icon}
              active={isActivePath(pathname, cryptoItem.href)}
              collapsed={isCollapsed && !isMobile}
              onNavigate={handleNavigate}
              description={cryptoItem.description}
              badge={!isCollapsed && apiType !== 'crypto' ? 'Binance' : undefined}
              muted={apiType !== 'crypto'}
            />
            {/* Settings */}
            <NavLink
              href={settingsItem.href}
              label={settingsItem.label}
              icon={settingsItem.icon}
              active={isActivePath(pathname, settingsItem.href)}
              collapsed={isCollapsed && !isMobile}
              onNavigate={handleNavigate}
              description={settingsItem.description}
            />
          </div>
        </nav>
      </ScrollArea>

      {/* Footer */}
      <div className={cn('shrink-0 border-t border-border p-3', isCollapsed && !isMobile && 'p-2 flex flex-col items-center gap-2')}>
        {!isCollapsed ? (
          <>
            <div className="flex items-center gap-2 text-[11px] leading-tight text-muted-foreground">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" aria-hidden />
              <span className="font-medium">8 menus grouped</span>
              <span className="hidden xl:inline opacity-60">• ⌘B to toggle</span>
            </div>
            <p className="mt-1 text-[11px] leading-snug text-muted-foreground/80">
              Click group header to collapse. Crypto dims when Broker = Indian.
            </p>
          </>
        ) : (
          !isMobile && (
            <Tooltip delayDuration={200}>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  onClick={() => setCollapsed(false)}
                  aria-label="Expand sidebar"
                  className="h-8 w-8 rounded-md bg-muted hover:bg-accent border border-border flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors"
                >
                  <PanelLeftOpen className="w-4 h-4" />
                </button>
              </TooltipTrigger>
              <TooltipContent side="right" sideOffset={10}>Expand sidebar</TooltipContent>
            </Tooltip>
          )
        )}
      </div>
    </div>
  );

  return (
    <TooltipProvider delayDuration={200}>
      {/* Desktop */}
      <aside
        aria-label="Primary navigation"
        className={cn(
          'hidden md:flex shrink-0 flex-col border-r border-border bg-card/80 backdrop-blur-sm supports-[backdrop-filter]:bg-card/80 transition-all duration-300 ease-in-out will-change-[width] overflow-hidden',
          collapsed ? 'w-[72px]' : 'w-64 lg:w-[272px]',
        )}
      >
        <NavContent isCollapsed={collapsed} />
      </aside>

      {/* Mobile trigger placeholder - actual trigger lives in TopHeader, but we expose via global event */}
      {/* Mobile drawer */}
      <div className={cn('md:hidden fixed inset-0 z-50 transition', mobileOpen ? 'visible' : 'invisible pointer-events-none')} aria-hidden={!mobileOpen}>
        {/* Backdrop */}
        <div
          onClick={() => setMobileOpen(false)}
          className={cn(
            'absolute inset-0 bg-black/40 backdrop-blur-sm transition-opacity duration-300',
            mobileOpen ? 'opacity-100' : 'opacity-0',
          )}
        />
        {/* Panel */}
        <aside
          aria-label="Primary navigation"
          className={cn(
            'absolute left-0 top-0 h-full w-[84vw] max-w-[320px] bg-card border-r border-border shadow-xl flex flex-col transition-transform duration-300 ease-out will-change-transform',
            mobileOpen ? 'translate-x-0' : '-translate-x-full',
          )}
        >
          <NavContent isCollapsed={false} isMobile />
        </aside>
      </div>
    </TooltipProvider>
  );
}

// Expose a tiny hook for TopHeader to control drawer when Sidebar is uncontrolled
export function useSidebarMobile() {
  const [open, setOpen] = useState(false);
  return { open, setOpen };
}
