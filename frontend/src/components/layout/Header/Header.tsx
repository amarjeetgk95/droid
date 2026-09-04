'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { MarketHealthStatus, MarketStatusResponse } from '@/lib/types';
import { StreamConnectionState } from '@/hooks/useMarketStream';
import { Menu } from 'lucide-react';
import { HeaderBreadcrumb } from './HeaderBreadcrumb';
import { HeaderSearch } from './HeaderSearch';
import { CommandPalette } from './CommandPalette';
import { HeaderMarketSession } from './HeaderMarketSession';
import { HeaderBrokerGateway } from './HeaderBrokerGateway';
import { HeaderNotifications } from './HeaderNotifications';
import { HeaderQuickActions } from './HeaderQuickActions';
import { HeaderUserProfile } from './HeaderUserProfile';
import { MarketHealthModal } from '@/components/dashboard/MarketHealthModal';

const TICKER_VISIBLE_KEY = 'droid:ticker:visible';

export interface HeaderProps {
  health: MarketHealthStatus | null;
  marketStatus: MarketStatusResponse | null;
  streamState: StreamConnectionState;
  onMenuClick?: () => void;
  tickerVisible?: boolean;
  onToggleTicker?: () => void;
}

function HeaderInner({
  health,
  marketStatus,
  streamState,
  onMenuClick,
  tickerVisible = true,
  onToggleTicker,
}: HeaderProps) {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [showHealthModal, setShowHealthModal] = useState(false);

  // Global keyboard shortcuts (Ctrl+K/⌘K for search, Ctrl+T/⌘T for ticker)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Avoid firing when user is typing in form inputs (unless it's the search shortcut)
      const target = e.target as HTMLElement | null;
      const isInput = target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable);

      // Search Palette: Ctrl+K or ⌘K
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPaletteOpen((prev) => !prev);
        return;
      }

      // Marquee Ticker Toggle: Ctrl+T or ⌘T (only when not in text input)
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 't' && !isInput && onToggleTicker) {
        e.preventDefault();
        onToggleTicker();
        return;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onToggleTicker]);

  const openDiagnostics = useCallback(() => {
    setShowHealthModal(true);
  }, []);

  return (
    <>
      <header
        className="sticky top-0 z-30 h-14 shrink-0 border-b border-border bg-card/95 backdrop-blur flex items-center justify-between px-3 md:px-4 select-none [contain:paint]"
        style={{ contentVisibility: 'auto', containIntrinsicSize: '0 56px' } as React.CSSProperties}
      >
        {/* ================================================================= */}
        {/* LEFT ZONE: Navigation Toggle, Breadcrumb & Spotlight Search       */}
        {/* ================================================================= */}
        <div className="flex items-center gap-2 sm:gap-3 min-w-0">
          {onMenuClick && (
            <button
              type="button"
              onClick={onMenuClick}
              aria-label="Open mobile navigation"
              className="md:hidden inline-flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-card text-foreground hover:bg-secondary transition-colors shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring shadow-2xs cursor-pointer"
            >
              <Menu className="w-4 h-4" />
            </button>
          )}

          {/* Dynamic Breadcrumbs / Spatial Context */}
          <div className="min-w-0 pr-1">
            <HeaderBreadcrumb />
          </div>

          {/* Global Spotlight Search Bar */}
          <HeaderSearch onOpen={() => setPaletteOpen(true)} />
        </div>

        {/* ================================================================= */}
        {/* CENTER ZONE: Precision IST Clock & Indian Market Session Station   */}
        {/* ================================================================= */}
        <div className="hidden md:flex items-center justify-center shrink-0 px-2">
          <HeaderMarketSession marketStatus={marketStatus} />
        </div>

        {/* ================================================================= */}
        {/* RIGHT ZONE: Gateway Health, Quick Actions, Alerts & User Profile  */}
        {/* ================================================================= */}
        <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
          {/* Consolidated Broker & System Status Pill */}
          <HeaderBrokerGateway
            health={health}
            marketStatus={marketStatus}
            streamState={streamState}
            onOpenDiagnostics={openDiagnostics}
          />

          {/* Terminal Workspace Controls (Ticker Marquee, Refresh, Zen Mode) */}
          <HeaderQuickActions
            tickerVisible={tickerVisible}
            onToggleTicker={onToggleTicker}
          />

          {/* Active Alpha Signals & Live Notifications Drawer */}
          <HeaderNotifications />

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
    return true;
  }
}

export function saveTickerVisible(v: boolean) {
  try {
    localStorage.setItem(TICKER_VISIBLE_KEY, v ? '1' : '0');
  } catch {}
}
