'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { usePathname } from 'next/navigation';
import { Power } from 'lucide-react';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';
import { useSignalsStatus } from '@/hooks/useSignalsStatus';
import { useToast } from '@/components/ui/toast';
import { useOptionalMarketDataContext } from '@/context/MarketDataContext';
import { useStreamHealth } from '@/context/LiveMarketContext';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { StatusDot } from '@/components/ui/status-dot';
import { SidebarHeader } from './Sidebar/SidebarHeader';
import { SidebarNavItem } from './Sidebar/SidebarNavItem';
import { SidebarFlyout } from './Sidebar/SidebarFlyout';
import { SidebarStatusDock } from './Sidebar/SidebarStatusDock';
import { BOTTOM_ITEMS, NAV_GROUPS, isActivePath, type NavItem } from './nav-config';

interface SidebarProps {
  /** Desktop rail collapse (lg+ only). */
  collapsed?: boolean;
  onToggleCollapse?: () => void;
  /** Under-lg drawer visibility, controlled by the shell. */
  mobileOpen?: boolean;
  onCloseMobile?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  collapsed = false,
  onToggleCollapse,
  mobileOpen = false,
  onCloseMobile,
}) => {
  const pathname = usePathname();
  const toast = useToast();
  const market = useOptionalMarketDataContext();
  const { streamState } = useStreamHealth();
  // Shared app-wide /signals/status snapshot (single 30s owner + SSE refresh).
  const signalsCount = useSignalsStatus().active;

  const [killModalOpen, setKillModalOpen] = useState(false);
  const [isKilling, setIsKilling] = useState(false);
  const mobileDrawerRef = useRef<HTMLElement>(null);

  const provider = market?.health?.provider ?? market?.marketStatus?.provider ?? 'FYERS';

  const telemetryBadges = useMemo<
    Record<string, { label: string; color: string; pulse?: boolean }> | undefined
  >(() => {
    if (signalsCount === null || signalsCount <= 0) return undefined;
    return {
      signals: {
        label: String(signalsCount),
        color: 'bg-up-wash text-up-strong border-up-line',
        pulse: true,
      },
    };
  }, [signalsCount]);

  // Escape closes the mobile drawer; lock page scroll while it is open.
  // Focus moves into the drawer and is trapped there until it closes.
  useEffect(() => {
    if (!mobileOpen) return;
    const drawer = mobileDrawerRef.current;
    const previouslyFocused =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const focusable = (): HTMLElement[] => {
      if (!drawer) return [];
      return Array.from(
        drawer.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((el) => el.offsetParent !== null);
    };
    focusable()[0]?.focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onCloseMobile?.();
        return;
      }
      if (e.key !== 'Tab' || !drawer) return;
      const candidates = focusable();
      if (candidates.length === 0) return;
      const first = candidates[0];
      const last = candidates[candidates.length - 1];
      const active = document.activeElement;
      if (e.shiftKey) {
        if (active === first || !drawer.contains(active)) {
          e.preventDefault();
          last.focus();
        }
      } else if (active === last || !drawer.contains(active)) {
        e.preventDefault();
        first.focus();
      }
    };

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    document.addEventListener('keydown', onKey, true);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener('keydown', onKey, true);
      previouslyFocused?.focus();
    };
  }, [mobileOpen, onCloseMobile]);

  const handleKillSwitch = useCallback(async () => {
    if (isKilling) return;
    setIsKilling(true);
    const reason = 'Emergency operator kill switch triggered from Sidebar';
    let signalsHalted = false;
    try {
      await api.toggleSignalsKillSwitch(true, reason);
      signalsHalted = true;
      await api.triggerAlgoKillSwitch('FULL_EXECUTION_STOP', 'Sidebar emergency stop');
      toast.success('Kill switch engaged', 'Signals halted and all execution engines stopped.');
    } catch (err) {
      const detail = err instanceof Error && err.message ? err.message : 'Kill switch request failed.';
      if (signalsHalted) {
        toast.error('Execution stop failed', `Signals were halted, but the algo engine stop failed: ${detail}`);
      } else {
        toast.error('Kill switch failed', detail);
      }
      // Re-throw so ConfirmDialog keeps the dialog open and shows the failure.
      throw err instanceof Error ? err : new Error(detail);
    } finally {
      setIsKilling(false);
    }
  }, [isKilling, toast]);

  const badgeFor = useCallback(
    (item: NavItem) => (item.badgeKey ? telemetryBadges?.[item.badgeKey] : undefined),
    [telemetryBadges],
  );

  const renderNav = (railCollapsed: boolean) => {
    if (railCollapsed) {
      return (
        <nav
          className="flex-1 min-h-0 overflow-y-auto py-2 flex flex-col items-center gap-1"
          aria-label="Primary navigation"
        >
          {NAV_GROUPS.map((group) => (
            <SidebarFlyout
              key={group.id}
              group={group}
              onNavigate={onCloseMobile}
              telemetryBadges={telemetryBadges}
            />
          ))}
          <div className="my-1 h-px w-8 bg-border" aria-hidden />
          {BOTTOM_ITEMS.map((item) => (
            <SidebarNavItem
              key={item.href}
              item={item}
              active={isActivePath(pathname, item.href)}
              collapsed
              onNavigate={onCloseMobile}
              badgeData={badgeFor(item)}
            />
          ))}
        </nav>
      );
    }

    return (
      <nav className="flex-1 min-h-0 overflow-y-auto px-2 py-2 space-y-2.5" aria-label="Primary navigation">
        {NAV_GROUPS.map((group) => (
          <section key={group.id} aria-label={group.label}>
            <div className="px-2.5 pb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-4">
              {group.label}
            </div>
            <div className="space-y-0.5">
              {group.items.map((item) => (
                <SidebarNavItem
                  key={item.href}
                  item={item}
                  active={isActivePath(pathname, item.href)}
                  onNavigate={onCloseMobile}
                  badgeData={badgeFor(item)}
                />
              ))}
            </div>
          </section>
        ))}

        <section aria-label="System">
          <div className="px-2.5 pb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-4">System</div>
          <div className="space-y-0.5">
            {BOTTOM_ITEMS.map((item) => (
              <SidebarNavItem
                key={item.href}
                item={item}
                active={isActivePath(pathname, item.href)}
                onNavigate={onCloseMobile}
                badgeData={badgeFor(item)}
              />
            ))}
          </div>
        </section>
      </nav>
    );
  };

  const renderKillSwitch = (railCollapsed: boolean) => (
    <div className={cn('shrink-0 border-t border-border', railCollapsed ? 'p-1.5' : 'p-2.5')}>
      {railCollapsed ? (
        <button
          type="button"
          onClick={() => setKillModalOpen(true)}
          disabled={isKilling}
          aria-busy={isKilling}
          aria-label="Emergency kill switch"
          title="Emergency kill switch — halt all engines"
          className="mx-auto flex h-9 w-9 items-center justify-center rounded-lg border border-down-line bg-down-wash text-down-strong transition-colors hover:bg-down/15 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Power className="h-4 w-4" aria-hidden />
        </button>
      ) : (
        <button
          type="button"
          onClick={() => setKillModalOpen(true)}
          disabled={isKilling}
          aria-busy={isKilling}
          className="group flex w-full items-center justify-center gap-2 rounded-lg border border-down-line bg-down-wash px-3 py-1.5 font-mono text-xs font-semibold tracking-wider text-down-strong transition-colors hover:bg-down/15 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <StatusDot status="error" pulse={false} />
          <span>{isKilling ? 'HALTING…' : 'KILL SWITCH'}</span>
        </button>
      )}
    </div>
  );

  return (
    <>
      {/* Desktop rail (lg+) — collapse is always reversible here */}
      <aside
        className={cn(
          'hidden lg:flex h-full flex-col border-r border-border bg-card select-none transition-[width] duration-200',
          collapsed ? 'w-16' : 'w-64',
        )}
        aria-label="Primary navigation"
      >
        <SidebarHeader
          collapsed={collapsed}
          streamState={streamState}
          onToggleCollapse={onToggleCollapse}
        />
        {renderNav(collapsed)}
        {renderKillSwitch(collapsed)}
        <SidebarStatusDock
          collapsed={collapsed}
          provider={provider}
          streamState={streamState}
          onExpand={onToggleCollapse}
          showSettingsLink={false}
        />
      </aside>

      {/* Mobile drawer (<lg) — overlay + backdrop, never traps the user */}
      {mobileOpen && (
        <div className="fixed inset-0 z-[45] lg:hidden">
          <div className="absolute inset-0 bg-scrim" onClick={onCloseMobile} aria-hidden="true" />
          <aside
            ref={mobileDrawerRef}
            role="dialog"
            aria-modal="true"
            aria-label="Primary navigation"
            className="absolute inset-y-0 left-0 flex w-64 max-w-[85vw] flex-col border-r border-border bg-card shadow-lg animate-in slide-in-from-left duration-200"
          >
            <SidebarHeader
              collapsed={false}
              isMobile
              streamState={streamState}
              onCloseMobile={onCloseMobile}
            />
            {renderNav(false)}
            {renderKillSwitch(false)}
            <SidebarStatusDock
              collapsed={false}
              isMobile
              provider={provider}
              streamState={streamState}
              onNavigate={onCloseMobile}
              showSettingsLink={false}
            />
          </aside>
        </div>
      )}

      {/* Shared confirmation modal — rendered outside the drawer so its fixed
          overlay is never re-parented by the drawer's transform. */}
      <ConfirmDialog
        isOpen={killModalOpen}
        onClose={() => setKillModalOpen(false)}
        onConfirm={handleKillSwitch}
        title="EMERGENCY KILL SWITCH"
        message="Triggering the Global Kill Switch halts all execution engines, cancels outstanding orders, stops all auto-trading, and transitions signals to SAFE mode immediately. This affects all active desks."
        confirmLabel="HALT ALL ENGINES"
        destructive
        requireTypedConfirmation="KILL"
      />
    </>
  );
};
