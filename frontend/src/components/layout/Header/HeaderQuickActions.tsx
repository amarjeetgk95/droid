'use client';

import { memo, useEffect, useState, useCallback } from 'react';
import { Maximize2, Minimize2, PanelBottomClose, PanelBottomOpen, RefreshCw } from 'lucide-react';
import { cn } from '@/lib/utils';

interface HeaderQuickActionsProps {
  tickerVisible?: boolean;
  onToggleTicker?: () => void;
}

function getPlatformTickerShortcut(): string {
  if (typeof window === 'undefined') return 'Ctrl+T';
  const isMac = /(Mac|iPhone|iPod|iPad)/i.test(navigator.userAgent);
  return isMac ? '⌘T' : 'Ctrl+T';
}

export function HeaderQuickActions({
  tickerVisible = true,
  onToggleTicker,
}: HeaderQuickActionsProps) {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [tickerShortcut] = useState<string>(getPlatformTickerShortcut);

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };

    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

  const toggleFullscreen = useCallback(async () => {
    try {
      if (!document.fullscreenElement) {
        await document.documentElement.requestFullscreen();
      } else {
        await document.exitFullscreen();
      }
    } catch {
      // Fullscreen not allowed or rejected by browser policy
    }
  }, []);

  const handleManualRefresh = useCallback(() => {
    setIsRefreshing(true);
    // Dispatch custom market reload event for data providers
    window.dispatchEvent(new CustomEvent('droid:feed:refresh'));
    setTimeout(() => {
      setIsRefreshing(false);
    }, 800);
  }, []);

  return (
    <div className="flex items-center gap-0.5">
      {/* Ticker Ribbon Toggle */}
      {onToggleTicker && (
        <button
          type="button"
          onClick={onToggleTicker}
          className={cn(
            'inline-flex items-center justify-center h-7 w-7 rounded-md transition-colors cursor-pointer outline-none focus-visible:ring-1 focus-visible:ring-ring select-none',
            tickerVisible
              ? 'text-foreground hover:bg-secondary/80'
              : 'text-muted-foreground/60 hover:text-foreground hover:bg-secondary/80',
          )}
          title={tickerVisible ? `Hide market marquee (${tickerShortcut})` : `Show market marquee (${tickerShortcut})`}
          aria-label={tickerVisible ? 'Hide market ticker' : 'Show market ticker'}
          aria-pressed={tickerVisible}
        >
          {tickerVisible ? (
            <PanelBottomClose className="w-3.5 h-3.5 text-foreground/80" />
          ) : (
            <PanelBottomOpen className="w-3.5 h-3.5 text-muted-foreground" />
          )}
        </button>
      )}

      {/* Manual Feed Refresh */}
      <button
        type="button"
        onClick={handleManualRefresh}
        disabled={isRefreshing}
        className="inline-flex items-center justify-center h-7 w-7 rounded-md text-muted-foreground hover:text-foreground hover:bg-secondary/80 transition-colors cursor-pointer outline-none focus-visible:ring-1 focus-visible:ring-ring select-none disabled:opacity-60"
        title="Refresh live market data feed"
        aria-label="Refresh market data feed"
      >
        <RefreshCw className={cn('w-3.5 h-3.5', isRefreshing && 'animate-spin text-primary')} />
      </button>

      {/* Fullscreen Mode Toggle */}
      <button
        type="button"
        onClick={toggleFullscreen}
        className="hidden sm:inline-flex items-center justify-center h-7 w-7 rounded-md text-muted-foreground hover:text-foreground hover:bg-secondary/80 transition-colors cursor-pointer outline-none focus-visible:ring-1 focus-visible:ring-ring select-none"
        title={isFullscreen ? 'Exit Zen / Fullscreen' : 'Enter Zen / Fullscreen'}
        aria-label="Toggle fullscreen mode"
      >
        {isFullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
      </button>
    </div>
  );
}

export const MemoizedHeaderQuickActions = memo(HeaderQuickActions);
