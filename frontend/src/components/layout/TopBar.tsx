'use client';

import React, { useMemo } from 'react';
import { Bot } from 'lucide-react';
import { useInstrument } from '@/context/InstrumentContext';
import { useSignalStream } from '@/context/SignalStreamContext';
import { useOptionalMarketDataContext } from '@/context/MarketDataContext';
import { useStreamHealth } from '@/context/LiveMarketContext';
import { FreshnessClock } from '@/components/common/FreshnessClock';
import { StatusDot } from '../shared/StatusDot';
import { cn } from '@/lib/utils';
import { Header } from './Header/Header';

interface TopBarProps {
  onToggleCopilot: () => void;
  copilotOpen?: boolean;
  /** Toggles the desktop rail collapse / mobile drawer (⌘B). */
  onToggleSidebar: () => void;
  tickerVisible: boolean;
  onToggleTicker: () => void;
}

export const TopBar: React.FC<TopBarProps> = ({
  onToggleCopilot,
  copilotOpen = false,
  onToggleSidebar,
  tickerVisible,
  onToggleTicker,
}) => {
  const { instrument, setInstrument, timeframe, setTimeframe, allInstruments, allTimeframes } =
    useInstrument();
  const { connected: signalsConnected } = useSignalStream();
  const market = useOptionalMarketDataContext();
  const { streamState, ticksFresh } = useStreamHealth();

  const health = market?.health ?? null;
  const marketStatus = market?.marketStatus ?? null;
  const marketClosed = marketStatus?.session === 'CLOSED' || marketStatus?.is_trading_day === false;

  // Freshness truth: prefer the live tick clock, fall back to the REST
  // snapshot time. Never renders LIVE unless the evidence supports it.
  const lastAt = ticksFresh ? null : (market?.lastFetch ?? null);

  const contextControls = useMemo(
    () => (
      <>
        <div
          className="flex items-center rounded-[4px] border border-border bg-muted p-0.5"
          role="group"
          aria-label="Instrument selection"
        >
          {allInstruments.map((inst) => (
            <button
              key={inst}
              type="button"
              onClick={() => setInstrument(inst)}
              aria-pressed={instrument === inst}
              className={cn(
                'px-2 py-1 text-[11px] font-mono font-semibold rounded-sm transition-colors cursor-pointer',
                instrument === inst
                  ? 'bg-primary text-primary-foreground'
                  : 'text-ink-2 hover:text-foreground hover:bg-muted-strong/60',
              )}
            >
              {inst}
            </button>
          ))}
        </div>

        <div
          className="hidden 2xl:flex items-center rounded-[4px] border border-border bg-muted p-0.5"
          role="group"
          aria-label="Timeframe selection"
        >
          {allTimeframes.map((tf) => (
            <button
              key={tf}
              type="button"
              onClick={() => setTimeframe(tf)}
              aria-pressed={timeframe === tf}
              className={cn(
                'px-1.5 py-0.5 text-[10.5px] font-mono rounded-sm transition-colors cursor-pointer',
                timeframe === tf
                  ? 'bg-card text-accent-strong font-semibold shadow-xs'
                  : 'text-ink-3 hover:text-foreground',
              )}
            >
              {tf}
            </button>
          ))}
        </div>
      </>
    ),
    [allInstruments, allTimeframes, instrument, setInstrument, setTimeframe, timeframe],
  );

  const actions = useMemo(
    () => (
      <>
        {/* Market data freshness — derived from real stream/session state */}
        <div className="hidden lg:flex items-center">
          <FreshnessClock
            lastAt={lastAt}
            streamState={streamState}
            ticksFresh={ticksFresh}
            fetching={market?.loading}
            marketClosed={marketClosed}
            sourceLabel={streamState === 'CONNECTED' ? 'WS' : 'REST'}
          />
        </div>

        {/* Signals event stream (separate from the market feed) */}
        <div
          className="hidden min-[1800px]:flex items-center gap-1.5 font-mono text-[11px] text-ink-3"
          title={
            signalsConnected
              ? 'Signal event stream connected'
              : 'Signal event stream disconnected — reconnecting'
          }
        >
          <StatusDot status={signalsConnected ? 'live' : 'offline'} pulse={signalsConnected} />
          <span>{signalsConnected ? 'SIGNALS SSE' : 'SSE DOWN'}</span>
        </div>

        {/* AI Copilot trigger */}
        <button
          type="button"
          onClick={onToggleCopilot}
          aria-pressed={copilotOpen}
          aria-label={copilotOpen ? 'Close AI Copilot' : 'Open AI Copilot'}
          title="AI Copilot"
          className={cn(
            'inline-flex items-center gap-1.5 h-8 px-2 xl:px-2.5 rounded-[4px] border font-mono text-xs font-semibold transition-colors cursor-pointer shrink-0',
            copilotOpen
              ? 'bg-primary text-primary-foreground border-primary'
              : 'bg-accent-wash text-accent-strong border-accent-line hover:bg-accent/15',
          )}
        >
          <Bot className="w-3.5 h-3.5" aria-hidden />
          <span className="hidden xl:inline tracking-wide">COPILOT</span>
        </button>
      </>
    ),
    [
      copilotOpen,
      lastAt,
      market?.loading,
      marketClosed,
      onToggleCopilot,
      signalsConnected,
      streamState,
      ticksFresh,
    ],
  );

  return (
    <Header
      health={health}
      marketStatus={marketStatus}
      streamState={streamState}
      onToggleSidebar={onToggleSidebar}
      tickerVisible={tickerVisible}
      onToggleTicker={onToggleTicker}
      contextSlot={contextControls}
      actionsSlot={actions}
    />
  );
};
