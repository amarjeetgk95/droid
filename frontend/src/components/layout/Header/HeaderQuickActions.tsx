'use client';

import { memo, useEffect, useState, useCallback } from 'react';
import { Eye, EyeOff, Maximize2, Minimize2, RefreshCw } from 'lucide-react';
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
    <div className="flex items-center gap-1">
      {/* Ticker Marquee Toggle */}
      {onToggleTicker && (
        <button
          type="button"
          onClick={onToggleTicker}
          className={cn(
            'inline-flex items-center justify-center h-8 w-8 rounded-lg border transition-all cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-ring shadow-2xs select-none',
            tickerVisible
              ? 'border-border/80 bg-card text-foreground hover:bg-secondary'
              : 'border-dashed border-border bg-secondary/50 text-muted-foreground hover:bg-secondary hover:text-foreground',
          )}
          title={tickerVisible ? `Hide market marquee (${tickerShortcut})` : `Show market marquee (${tickerShortcut})`}
          aria-label={tickerVisible ? 'Hide market ticker' : 'Show market ticker'}
          aria-pressed={tickerVisible}
        >
          {tickerVisible ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
        </button>
      )}

      {/* Manual Feed Refresh */}
      <button
        type="button"
        onClick={handleManualRefresh}
        disabled={isRefreshing}
        className="hidden xl:inline-flex items-center justify-center h-8 w-8 rounded-lg border border-border/80 bg-card hover:bg-secondary text-muted-foreground hover:text-foreground transition-all cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-ring shadow-2xs select-none disabled:opacity-60"
        title="Refresh live market data feed"
        aria-label="Refresh market data feed"
      >
        <RefreshCw className={cn('w-3.5 h-3.5', isRefreshing && 'animate-spin text-primary')} />
      </button>

      {/* Fullscreen Mode Toggle */}
      <button
        type="button"
        onClick={toggleFullscreen}
        className="hidden lg:inline-flex items-center justify-center h-8 w-8 rounded-lg border border-border/80 bg-card hover:bg-secondary text-muted-foreground hover:text-foreground transition-all cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-ring shadow-2xs select-none"
        title={isFullscreen ? 'Exit Zen / Fullscreen' : 'Enter Zen / Fullscreen'}
        aria-label="Toggle fullscreen mode"
      >
        {isFullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
      </button>
    </div>
  );
}

export const MemoizedHeaderQuickActions = memo(HeaderQuickActions);
