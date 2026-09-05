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

  // Collapsed Mode Dock (Icon Stack)
  if (collapsed && !isMobile) {
    return (
      <div className="flex flex-col items-center gap-1.5 p-2 border-t border-border/80 shrink-0 select-none">
        {/* Settings button */}
        <Tooltip delayDuration={100}>
          <TooltipTrigger asChild>
            <Link
              href="/settings"
              onClick={onNavigate}
              aria-label="Settings (⌘,)"
              className={cn(
                'flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors cursor-pointer',
                isSettingsActive
                  ? 'bg-primary/10 text-primary ring-1 ring-primary/20'
                  : 'hover:bg-accent hover:text-foreground',
              )}
            >
              <Settings className="w-4 h-4" />
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
              className="flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors cursor-pointer"
            >
              <PanelLeftOpen className="w-4 h-4" />
            </button>
          </TooltipTrigger>
          <TooltipContent side="right" sideOffset={10}>
            Expand sidebar <kbd className="ml-1 text-[10px] font-mono opacity-70">⌘B</kbd>
          </TooltipContent>
        </Tooltip>
      </div>
    );
  }

  // Expanded Mode Dock — compact single-line status + Settings (header owns full health pill)
  return (
    <div className="flex flex-col gap-1 p-2 border-t border-border/80 shrink-0 select-none">
      {/* Gateway status line */}
      <div
        className="flex items-center justify-between px-2 py-1.5 rounded-lg"
        title={isStreamLive ? 'Market feed connected' : isSyncing ? 'Reconnecting…' : 'Feed offline'}
      >
        <div className="flex items-center gap-1.5 min-w-0">
          <span className="relative flex h-2 w-2 shrink-0" aria-hidden>
            {isStreamLive && (
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            )}
            {isSyncing && (
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
            )}
            <span
              className={cn(
                'relative inline-flex rounded-full h-2 w-2',
                isStreamLive ? 'bg-emerald-500' : isSyncing ? 'bg-amber-500' : 'bg-rose-500',
              )}
            />
          </span>
          <span className="text-[11px] font-semibold tracking-wide text-muted-foreground truncate">
            {gatewayLabel}
          </span>
          <span
            className={cn(
              'text-[10px] font-bold uppercase tracking-wider',
              isStreamLive ? 'text-emerald-600' : isSyncing ? 'text-amber-600' : 'text-rose-600',
            )}
          >
            {isStreamLive ? '• Live' : isSyncing ? '• Sync' : '• Off'}
          </span>
        </div>

        <Link
          href="/settings"
          onClick={onNavigate}
          aria-label="Settings (⌘,)"
          aria-current={isSettingsActive ? 'page' : undefined}
          className={cn(
            'group flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium transition-colors cursor-pointer shrink-0',
            isSettingsActive
              ? 'bg-primary/[0.12] text-primary font-semibold ring-1 ring-primary/20'
              : 'text-muted-foreground hover:bg-accent hover:text-foreground',
          )}
        >
          <Settings className="w-3.5 h-3.5 shrink-0 opacity-75 group-hover:opacity-100 group-hover:rotate-45 transition-transform duration-200" />
          <span>Settings</span>
          <kbd className="hidden xl:inline text-[10px] font-mono px-1 rounded bg-muted text-muted-foreground border border-border/40">
            ⌘,
          </kbd>
        </Link>
      </div>
    </div>
  );
}
