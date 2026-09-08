'use client';

import { PanelLeftClose, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { StreamConnectionState } from '@/hooks/useMarketStream';

interface SidebarHeaderProps {
  collapsed: boolean;
  isMobile?: boolean;
  streamState?: StreamConnectionState;
  onToggleCollapse?: () => void;
  onCloseMobile?: () => void;
}

export function SidebarHeader({
  collapsed,
  isMobile,
  streamState = 'CONNECTED',
  onToggleCollapse,
  onCloseMobile,
}: SidebarHeaderProps) {
  const isLive = streamState === 'CONNECTED';
  const isConnecting = streamState === 'CONNECTING' || streamState === 'RECONNECTING';

  const dotColor = isLive
    ? 'bg-emerald-500'
    : isConnecting
    ? 'bg-amber-500'
    : 'bg-rose-500';

  const statusLabel = isLive ? 'Live' : isConnecting ? 'Syncing' : 'Offline';

  return (
    <div
      className={cn(
        'flex h-14 shrink-0 items-center justify-between border-b border-border/70 px-3 transition-all duration-150 select-none',
        collapsed && !isMobile && 'justify-center px-2',
      )}
    >
      {/* Expanded / Mobile: Brand Title + Status Dot */}
      {!collapsed || isMobile ? (
        <div className="flex items-center gap-2.5 min-w-0">
          {/* Logo icon with live pulse dot */}
          <div
            className="relative flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground font-extrabold text-sm tracking-tight shadow-sm"
            aria-hidden
          >
            <span>D</span>
            <span className="absolute -bottom-0.5 -right-0.5 flex h-2.5 w-2.5" title={`Feed ${statusLabel}`}>
              {isLive && (
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              )}
              <span className={cn('relative inline-flex rounded-full h-2.5 w-2.5 ring-2 ring-card', dotColor)} />
            </span>
          </div>

          <div className="flex items-center gap-1.5 min-w-0">
            <span className="font-bold tracking-tight text-[13px] text-foreground uppercase leading-none">
              Droid
            </span>
            <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-px rounded-md bg-primary/10 text-primary border border-primary/20 leading-none">
              Pro
            </span>
          </div>
        </div>
      ) : (
        /* Collapsed Mode: Logo only */
        <Tooltip delayDuration={100}>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={onToggleCollapse}
              aria-label="Expand sidebar (⌘B)"
              title="Expand sidebar (⌘B)"
              className="relative flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground font-extrabold text-sm tracking-tight shadow-sm cursor-pointer hover:brightness-105 active:brightness-95 transition"
            >
              <span>D</span>
              <span className="absolute -bottom-0.5 -right-0.5 flex h-2.5 w-2.5">
                {isLive && (
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                )}
                <span className={cn('relative inline-flex rounded-full h-2.5 w-2.5 ring-2 ring-card', dotColor)} />
              </span>
            </button>
          </TooltipTrigger>
          <TooltipContent side="right" sideOffset={10}>
            <div className="flex flex-col gap-0.5">
              <span className="font-bold text-xs">Droid Pro Terminal</span>
              <span className="text-[10px] text-muted-foreground">Feed {statusLabel} • Click or press ⌘B to expand</span>
            </div>
          </TooltipContent>
        </Tooltip>
      )}

      {/* Desktop Collapse Trigger (⌘B) */}
      {!isMobile && !collapsed && (
        <Tooltip delayDuration={150}>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={onToggleCollapse}
              aria-label="Collapse sidebar (⌘B)"
              title="Collapse sidebar (⌘B)"
              className={cn(
                'inline-flex items-center justify-center rounded-md h-7 w-7 shrink-0 text-muted-foreground hover:text-foreground hover:bg-accent transition-colors',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring cursor-pointer',
              )}
            >
              <PanelLeftClose className="w-4 h-4" />
            </button>
          </TooltipTrigger>
          <TooltipContent side="right" sideOffset={10}>
            Collapse sidebar <kbd className="ml-1 text-[10px] font-mono opacity-70">⌘B</kbd>
          </TooltipContent>
        </Tooltip>
      )}

      {/* Mobile Drawer Close Button */}
      {isMobile && (
        <button
          type="button"
          onClick={onCloseMobile}
          aria-label="Close navigation"
          className="ml-auto inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring cursor-pointer"
        >
          <X className="w-4 h-4" />
        </button>
      )}
    </div>
  );
}
