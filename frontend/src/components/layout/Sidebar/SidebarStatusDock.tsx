'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Settings, PanelLeftOpen } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { StreamConnectionState } from '@/hooks/useMarketStream';

interface SidebarStatusDockProps {
  collapsed: boolean;
  isMobile?: boolean;
  apiType?: string;
  provider?: string;
  streamState?: StreamConnectionState;
  onExpand?: () => void;
  onNavigate?: () => void;
}

export function SidebarStatusDock({
  collapsed,
  isMobile,
  apiType = 'indian',
  provider = 'fyers',
  streamState = 'CONNECTED',
  onExpand,
  onNavigate,
}: SidebarStatusDockProps) {
  const pathname = usePathname();
  const isSettingsActive = pathname === '/settings' || pathname.startsWith('/settings/');
  const isStreamLive = streamState === 'CONNECTED';
  const isSyncing = streamState === 'CONNECTING' || streamState === 'RECONNECTING';

  const gatewayLabel =
    apiType === 'crypto'
      ? 'BINANCE'
      : `${(provider || 'fyers').toUpperCase()}`;

  const statusText = isStreamLive ? 'Live' : isSyncing ? 'Sync' : 'Off';
  const statusDot = isStreamLive ? 'bg-emerald-500' : isSyncing ? 'bg-amber-500' : 'bg-rose-500';
  const statusTextColor = isStreamLive
    ? 'text-emerald-600'
    : isSyncing
      ? 'text-amber-600'
      : 'text-rose-600';

  // Collapsed Mode Dock (Icon Stack) — keeps feed truth visible via status dot
  if (collapsed && !isMobile) {
    return (
      <div className="flex flex-col items-center gap-1 p-2 border-t border-border/70 shrink-0 select-none">
        <Tooltip delayDuration={100}>
          <TooltipTrigger asChild>
            <div
              className="flex h-6 items-center justify-center gap-1.5 cursor-default"
              role="status"
              aria-label={`Feed ${statusText}`}
              title={isStreamLive ? 'Market feed connected' : isSyncing ? 'Reconnecting…' : 'Feed offline'}
            >
              <span className="relative flex h-2 w-2" aria-hidden>
                {isStreamLive && (
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                )}
                <span className={cn('relative inline-flex rounded-full h-2 w-2', statusDot)} />
              </span>
            </div>
          </TooltipTrigger>
          <TooltipContent side="right" sideOffset={10}>
            <span className="font-semibold text-xs">{gatewayLabel} • {statusText}</span>
          </TooltipContent>
        </Tooltip>

        {/* Settings button */}
        <Tooltip delayDuration={100}>
          <TooltipTrigger asChild>
            <Link
              href="/settings"
              onClick={onNavigate}
              aria-label="Settings (⌘,)"
              title="Settings (⌘,)"
              aria-current={isSettingsActive ? 'page' : undefined}
              className={cn(
                'flex h-9 w-9 items-center justify-center rounded-lg text-muted-foreground transition-colors cursor-pointer',
                isSettingsActive
                  ? 'bg-primary/10 text-primary ring-1 ring-primary/20'
                  : 'hover:bg-accent hover:text-foreground',
              )}
            >
              <Settings className="w-4 h-4" aria-hidden />
            </Link>
          </TooltipTrigger>
          <TooltipContent side="right" sideOffset={10}>
            <span className="font-semibold text-xs">Settings</span>
          </TooltipContent>
        </Tooltip>

        {/* Expand button */}
        <Tooltip delayDuration={100}>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={onExpand}
              aria-label="Expand sidebar (⌘B)"
              title="Expand sidebar (⌘B)"
              className="flex h-9 w-9 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <PanelLeftOpen className="w-4 h-4" aria-hidden />
            </button>
          </TooltipTrigger>
          <TooltipContent side="right" sideOffset={10}>
            Expand sidebar <kbd className="ml-1 text-[10px] font-mono opacity-70">⌘B</kbd>
          </TooltipContent>
        </Tooltip>
      </div>
    );
  }

  // Expanded Mode Dock — status card + full-width Settings
  return (
    <div className="flex flex-col gap-2 p-3 border-t border-border/70 shrink-0 select-none bg-gradient-to-b from-transparent to-muted/40">
      {/* Gateway status line */}
      <Tooltip delayDuration={300}>
        <TooltipTrigger asChild>
          <div
            className="flex items-center justify-between gap-2 px-3 py-2 rounded-xl bg-card border border-border shadow-[0_1px_2px_rgb(15_30_51/0.05)] cursor-default min-h-9"
            role="status"
            aria-label={`${gatewayLabel} feed ${statusText}`}
          >
            <div className="flex items-center gap-1.5 min-w-0">
              <span className="relative flex h-2 w-2 shrink-0" aria-hidden>
                {isStreamLive && (
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                )}
                {isSyncing && (
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
                )}
                <span className={cn('relative inline-flex rounded-full h-2 w-2', statusDot)} />
              </span>
              <span className="text-[11px] font-semibold tracking-wide text-muted-foreground truncate tabular-nums">
                {gatewayLabel}
              </span>
            </div>
            <span className={cn('text-[10px] font-bold uppercase tracking-wider tabular-nums', statusTextColor)}>
              • {statusText}
            </span>
          </div>
        </TooltipTrigger>
        <TooltipContent side="top" align="center">
          {isStreamLive ? 'Market feed connected' : isSyncing ? 'Reconnecting…' : 'Feed offline'}
        </TooltipContent>
      </Tooltip>

      <Link
        href="/settings"
        onClick={onNavigate}
        aria-label="Settings (⌘,)"
        aria-current={isSettingsActive ? 'page' : undefined}
        title="Broker, AI models & app preferences"
        className={cn(
          'group flex items-center gap-2 w-full px-2.5 py-2 rounded-lg text-[13px] font-medium transition-colors cursor-pointer min-h-9',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
          isSettingsActive
            ? 'bg-primary/[0.10] text-primary font-semibold ring-1 ring-primary/20'
            : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground',
        )}
      >
        <Settings className="w-4 h-4 shrink-0 opacity-70 group-hover:opacity-100 transition-opacity" aria-hidden />
        <span className="flex-1 truncate leading-tight">Settings</span>
        <kbd className="hidden xl:inline-flex text-[10px] font-mono px-1.5 py-0.5 rounded-md bg-muted text-muted-foreground border border-border/60 leading-none">
          ⌘,
        </kbd>
      </Link>
    </div>
  );
}
