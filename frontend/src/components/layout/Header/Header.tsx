'use client';

import { memo, useCallback, useEffect, useState, type ReactNode } from 'react';
import { useRouter } from 'next/navigation';
import { MarketHealthStatus, MarketStatusResponse } from '@/lib/types';
import { StreamConnectionState } from '@/hooks/useMarketStream';
import { Menu } from 'lucide-react';
import { HeaderBreadcrumb } from './HeaderBreadcrumb';
import { CommandPalette } from './CommandPalette';
import { HeaderMarketSession } from './HeaderMarketSession';
import { HeaderBrokerGateway } from './HeaderBrokerGateway';
import { HeaderNotifications } from './HeaderNotifications';
import { HeaderQuickActions } from './HeaderQuickActions';
import { HeaderUserProfile } from './HeaderUserProfile';
import { MarketHealthModal } from '@/components/dashboard/MarketHealthModal';
import { findNavItemByShortcut } from '../nav-config';

const TICKER_VISIBLE_KEY = 'droid:ticker:visible';

export interface HeaderProps {
  health: MarketHealthStatus | null;
  marketStatus: MarketStatusResponse | null;
  streamState: StreamConnectionState;
  /** Mobile/tablet drawer trigger (<lg). */
  onToggleSidebar?: () => void;
  tickerVisible?: boolean;
  onToggleTicker?: () => void;
  /** Context controls (instrument / timeframe selectors) injected by TopBar. */
  contextSlot?: ReactNode;
  /** Telemetry + actions (freshness, copilot) injected by TopBar. */
  actionsSlot?: ReactNode;
}

const MODIFIER_SHORTCUT_KEYS = ['0', '1', '2', '3', '4', '5', ','] as const;

function HeaderInner({
  health,
  marketStatus,
  streamState,
  onToggleSidebar,
  tickerVisible = true,
  onToggleTicker,
  contextSlot,
  actionsSlot,
}: HeaderProps) {
  const router = useRouter();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [showHealthModal, setShowHealthModal] = useState(false);

  // Global keyboard shortcuts. Every advertised shortcut is wired here:
  // ⌘K palette · ⌘T ticker · ⌘B sidebar · ⌘0–⌘5 + ⌘, navigation.
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const isInput =
        target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable);
      if (!(e.metaKey || e.ctrlKey)) return;
      const key = e.key.toLowerCase();

      // Search Palette: Ctrl+K or ⌘K (works while typing too).
      if (key === 'k') {
        e.preventDefault();
        setPaletteOpen((prev) => !prev);
        return;
      }

      if (isInput) return;

      // Ticker Ribbon: Ctrl+T or ⌘T
      if (key === 't' && onToggleTicker) {
        e.preventDefault();
        onToggleTicker();
        return;
      }

      // Sidebar collapse/drawer: Ctrl+B or ⌘B
      if (key === 'b' && onToggleSidebar) {
        e.preventDefault();
        onToggleSidebar();
        return;
      }

      // Page jumps: Ctrl+0–5 / Ctrl+, or their ⌘ equivalents.
      if ((MODIFIER_SHORTCUT_KEYS as readonly string[]).includes(e.key)) {
        const item = findNavItemByShortcut(`⌘${e.key}`);
        if (item) {
          e.preventDefault();
          router.push(item.href);
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onToggleTicker, onToggleSidebar, router]);

  const openDiagnostics = useCallback(() => {
    setShowHealthModal(true);
  }, []);

  return (
    <>
      <header className="sticky top-0 z-30 h-14 shrink-0 border-b border-border bg-card flex items-center justify-between gap-2 px-3 sm:px-4 md:px-6 select-none">
        {/* ================================================================= */}
        {/* LEFT ZONE: Navigation Toggle, Breadcrumb & Context Controls       */}
        {/* ================================================================= */}
        <div className="flex items-center gap-2 sm:gap-3 min-w-0">
          {onToggleSidebar && (
            <button
              type="button"
              onClick={onToggleSidebar}
              aria-label="Toggle navigation"
              title="Toggle navigation (⌘B)"
              className="lg:hidden inline-flex h-8 w-8 items-center justify-center rounded-[4px] border border-border bg-card text-foreground hover:bg-secondary transition-colors shrink-0 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring cursor-pointer"
            >
              <Menu className="w-4 h-4" />
            </button>
          )}

          {/* Dynamic Breadcrumbs / Spatial Context */}
          <div className="min-w-0">
            <HeaderBreadcrumb />
          </div>

          {contextSlot ? (
            <div className="hidden md:flex items-center gap-2 min-w-0">{contextSlot}</div>
          ) : null}
        </div>

        {/* ================================================================= */}
        {/* CENTER ZONE: Precision IST Clock & Indian Market Session Station   */}
        {/* ================================================================= */}
        <div className="hidden xl:flex items-center justify-center shrink-0 px-2">
          <HeaderMarketSession marketStatus={marketStatus} />
        </div>

        {/* ================================================================= */}
        {/* RIGHT ZONE: Freshness, Copilot, Gateway Health, Alerts & Profile  */}
        {/* ================================================================= */}
        <div className="flex items-center gap-2 shrink-0">
          {actionsSlot}

          {/* Consolidated Broker & System Status Pill */}
          <HeaderBrokerGateway
            health={health}
            marketStatus={marketStatus}
            streamState={streamState}
            onOpenDiagnostics={openDiagnostics}
          />

          {/* Unified Toolset Pod: Ticker Toggle, Refresh, Zen Mode, Signals Bell */}
          <div className="flex items-center gap-0.5 p-0.5 rounded-[4px] border border-border bg-card">
            <HeaderQuickActions
              tickerVisible={tickerVisible}
              onToggleTicker={onToggleTicker}
            />
            <HeaderNotifications />
          </div>

          {/* Clean Visual Divider */}
          <div className="h-5 w-px bg-border/80 mx-0.5 hidden sm:block" />

          {/* User Account & Session Profile */}
          <HeaderUserProfile />
        </div>
      </header>

      {/* Global Command Palette (Ctrl+K / ⌘K) */}
      {paletteOpen && (
        <CommandPalette
          open={paletteOpen}
          onClose={() => setPaletteOpen(false)}
          onOpenDiagnostics={openDiagnostics}
          onToggleTicker={onToggleTicker}
          tickerVisible={tickerVisible}
        />
      )}

      {/* Deep Ingestion Diagnostics Telemetry Modal */}
      <MarketHealthModal
        isOpen={showHealthModal}
        onClose={() => setShowHealthModal(false)}
        health={health}
        streamState={streamState}
      />
    </>
  );
}

export const Header = memo(HeaderInner);

// ---------------------------------------------------------------------------
// Helpers for persistent ticker visibility
// ---------------------------------------------------------------------------
export function loadTickerVisible(): boolean {
  if (typeof window === 'undefined') return true;
  try {
    const v = localStorage.getItem(TICKER_VISIBLE_KEY);
    return v === null ? true : v === '1';
  } catch {
    // localStorage unavailable (privacy mode) — default to visible.
    return true;
  }
}

export function saveTickerVisible(v: boolean) {
  try {
    localStorage.setItem(TICKER_VISIBLE_KEY, v ? '1' : '0');
  } catch {
    // Best-effort persistence only.
  }
}
