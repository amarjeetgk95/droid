'use client';

import React, { Suspense, useCallback, useEffect, useState } from 'react';
import {
  InstrumentProvider,
  useInstrument,
  type SupportedInstrument,
} from '@/context/InstrumentContext';
import { MarketSessionProvider } from '@/context/MarketSessionContext';
import { SignalStreamProvider } from '@/context/SignalStreamContext';
import { MarketDataProvider } from '@/context/MarketDataContext';
import { LiveMarketProvider } from '@/context/LiveMarketContext';
import { TooltipProvider } from '@/components/ui/tooltip';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { MarketTicker } from './MarketTicker';
import { RouteProgress } from './RouteProgress';
import { FloatingAICopilot } from './FloatingAICopilot';
import { loadTickerVisible, saveTickerVisible } from './Header/Header';
import { isMinimalUi } from '@/lib/featureFlags';

/**
 * Shell z-index scale (agreed, ascending). Shell overlays NEVER sit above
 * module drawers or toasts:
 *   30  shell header + desktop sidebar rail
 *   40  AI copilot scrim + panel
 *   45  mobile navigation drawer/scrim (primary nav stays reachable)
 *   50  command palette, modals, radix dropdowns/tooltips
 *   60  module drawers (`.sg-ovl`, globals.css)
 *   70  toasts (`.toast-host`, globals.css)
 *  100  route progress bar
 */
interface AppShellProps {
  children: React.ReactNode;
}

/**
 * Required provider nesting:
 * Instrument > MarketSession > SignalStream > MarketData > LiveMarket.
 * MarketDataProvider owns the single market WebSocket + REST snapshot;
 * LiveMarketProvider merges ticks without opening a second socket.
 */
export const AppShell: React.FC<AppShellProps> = ({ children }) => {
  return (
    <InstrumentProvider>
      <MarketSessionProvider>
        <SignalStreamProvider>
          <MarketDataProvider refreshInterval={5000} useSummaryEndpoint>
            <LiveMarketProvider>
              <TooltipProvider delayDuration={150}>
                <AppShellFrame>{children}</AppShellFrame>
              </TooltipProvider>
            </LiveMarketProvider>
          </MarketDataProvider>
        </SignalStreamProvider>
      </MarketSessionProvider>
    </InstrumentProvider>
  );
};

const SHELL_INSTRUMENTS: SupportedInstrument[] = ['NIFTY', 'BANKNIFTY', 'SENSEX'];

function AppShellFrame({ children }: AppShellProps) {
  const { setInstrument } = useInstrument();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [copilotOpen, setCopilotOpen] = useState(false);
  const [tickerVisible, setTickerVisible] = useState(true);
  // P2-5: the minimal shell folds market status into the Command ribbon, so
  // the standalone marquee is not mounted. The component + its test remain.
  const minimal = isMinimalUi();

  // Hydrate ticker visibility after mount so SSR and first client render match.
  useEffect(() => {
    setTickerVisible(loadTickerVisible());
  }, []);

  const toggleTicker = useCallback(() => {
    setTickerVisible((prev) => {
      const next = !prev;
      saveTickerVisible(next);
      return next;
    });
  }, []);

  // ⌘B / hamburger: collapse the rail on desktop, open the drawer below lg.
  const toggleSidebar = useCallback(() => {
    if (typeof window !== 'undefined' && window.matchMedia('(min-width: 1024px)').matches) {
      setSidebarCollapsed((prev) => !prev);
    } else {
      setMobileNavOpen((prev) => !prev);
    }
  }, []);

  const handleSelectTickerSymbol = useCallback(
    (symbol: string) => {
      if ((SHELL_INSTRUMENTS as string[]).includes(symbol)) {
        setInstrument(symbol as SupportedInstrument);
      }
    },
    [setInstrument],
  );

  return (
    <div className="flex h-dvh w-full overflow-hidden bg-surface-subtle text-foreground font-sans antialiased">
      {/* Route transition feedback (fixed overlay, z-100) */}
      <Suspense fallback={null}>
        <RouteProgress />
      </Suspense>

      {/* Navigation rail (desktop) + drawer (mobile) */}
      <Sidebar
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed((prev) => !prev)}
        mobileOpen={mobileNavOpen}
        onCloseMobile={() => setMobileNavOpen(false)}
      />

      {/* Main application column */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        <TopBar
          onToggleCopilot={() => setCopilotOpen((prev) => !prev)}
          copilotOpen={copilotOpen}
          onToggleSidebar={toggleSidebar}
          tickerVisible={tickerVisible}
          onToggleTicker={toggleTicker}
        />

        {/* Live index ribbon — legacy shell only (minimal folds it into the ribbon) */}
        {!minimal && tickerVisible && (
          <div className="shrink-0">
            <MarketTicker onSelectSymbol={handleSelectTickerSymbol} />
          </div>
        )}

        {/* Scrollable page content */}
        <main className="flex-1 overflow-y-auto p-4 sm:p-6">
          <div className="max-w-[1600px] mx-auto space-y-6">{children}</div>
        </main>
      </div>

      {/* Shell-level AI drawer (z-40, below module drawers) */}
      <FloatingAICopilot isOpen={copilotOpen} onClose={() => setCopilotOpen(false)} />
    </div>
  );
}
