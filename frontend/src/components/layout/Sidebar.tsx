'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { getStoredSettings } from '@/lib/settings';
import { cn } from '@/lib/utils';
import {
  NAV_GROUPS,
  STANDALONE_ITEMS,
  ALL_NAV_ITEMS,
  isActivePath,
} from './nav-config';
import { TooltipProvider } from '@/components/ui/tooltip';
import { SidebarHeader, SidebarNavItem, SidebarFlyout, SidebarStatusDock } from './Sidebar/index';
import { useOptionalMarketDataContext } from '@/context/MarketDataContext';
import { useOptionalLiveMarketContext } from '@/context/LiveMarketContext';

// ---------------------------------------------------------------------------
// Storage key & helpers
// ---------------------------------------------------------------------------
const SIDEBAR_COLLAPSED_KEY = 'droid:sidebar:collapsed';

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

  // Live Telemetry Badges
  const telemetryBadges = useMemo(() => {
    return {
      signals: { label: '+3 LIVE', color: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/30', pulse: false },
      ai: { label: 'SYNC', color: 'bg-purple-500/10 text-purple-600 border-purple-500/30', pulse: false },
      broker: { label: 'ONLINE', color: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/30', pulse: false },
    };
  }, []);

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

  // Keyboard Shortcuts: Cmd/Ctrl+B (toggle sidebar), Cmd/Ctrl+1..5 (quick jumps)
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const isInput = ['INPUT', 'TEXTAREA', 'SELECT'].includes((e.target as HTMLElement)?.tagName);

      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'b') {
        e.preventDefault();
        if (window.innerWidth >= 768) setCollapsed((p) => !p);
        else setMobileOpen(!mobileOpen);
      }

      // Quick jumps: Cmd+1 to Cmd+5 when not typing
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
  // Shared Navigation Content (100% Confined & Non-Scrolling)
  // -----------------------------------------------------------------------
  const NavContent = ({ isCollapsed, isMobile }: { isCollapsed: boolean; isMobile?: boolean }) => (
    <div className="flex h-full flex-col justify-between overflow-hidden select-none">
      {/* 1. Header (Brand + Pulse + Collapse toggle) */}
      <SidebarHeader
        collapsed={isCollapsed}
        isMobile={isMobile}
        streamState={streamState}
        onToggleCollapse={() => setCollapsed((p) => !p)}
        onCloseMobile={() => setMobileOpen(false)}
      />

      {/* 2. Main Navigation Items (Confined without scrollbars) */}
      <nav
        aria-label="Primary"
        className={cn(
          'flex-1 flex flex-col justify-start gap-1 py-2 px-2 overflow-hidden',
          isCollapsed && !isMobile && 'items-center px-1.5 gap-1.5',
        )}
      >
        {/* Command Dashboard (Standalone direct item) */}
        <SidebarNavItem
          item={dashboardItem}
          active={isActivePath(pathname, dashboardItem.href)}
          collapsed={isCollapsed && !isMobile}
          onNavigate={handleNavigate}
        />

        {/* Thematic Groups */}
        {NAV_GROUPS.map((group) => {
          // Collapsed Rail Mode: Floating Flyout Popover
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

          // Expanded / Mobile Mode: Compact Group Header & Items
          return (
            <div key={group.id} className="flex flex-col mt-1">
              {/* Group Section Label */}
              <div className="px-2 py-0.5 text-[10px] font-bold tracking-wider uppercase text-muted-foreground/75">
                {group.label}
              </div>

              {/* Group Items */}
              <div className="flex flex-col gap-0.5">
                {group.items.map((item) => {
                  const active = isActivePath(pathname, item.href);
                  const badgeData = item.badgeKey ? telemetryBadges[item.badgeKey] : undefined;
                  return (
                    <SidebarNavItem
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
          );
        })}
      </nav>

      {/* 3. Bottom Operational Status Dock */}
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
