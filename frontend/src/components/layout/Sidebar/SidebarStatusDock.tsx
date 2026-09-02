'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Settings, ShieldCheck, Wifi, Sparkles, Activity, PanelLeftOpen } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { StreamConnectionState } from '@/hooks/useMarketStream';

interface SidebarStatusDockProps {
  collapsed: boolean;
  isMobile?: boolean;
  apiType: string;
  provider?: string;
  streamState?: StreamConnectionState;
  onExpand?: () => void;
  onNavigate?: () => void;
}

export function SidebarStatusDock({
  collapsed,
  isMobile,
  apiType,
  provider = 'fyers',
  streamState = 'CONNECTED',
  onExpand,
  onNavigate,
}: SidebarStatusDockProps) {
  const pathname = usePathname();
  const isSettingsActive = pathname === '/settings';

  const isStreamLive = streamState === 'CONNECTED';

  const gatewayLabel =
    apiType === 'crypto'
      ? 'BINANCE FUTURES'
      : `${(provider || 'fyers').replace('_', ' ').toUpperCase()} GATEWAY`;

  if (collapsed && !isMobile) {
    return (
      <div className="flex flex-col items-center gap-2 p-2 border-t border-border/80">
        {/* Settings button */}
        <Tooltip delayDuration={150}>
          <TooltipTrigger asChild>
            <Link
              href="/settings"
              onClick={onNavigate}
              className={cn(
                'flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground transition-colors',
                isSettingsActive
                  ? 'bg-primary/10 text-primary ring-1 ring-primary/20'
                  : 'hover:bg-accent hover:text-foreground',
              )}
            >
              <Settings className="w-4 h-4" />
            </Link>
          </TooltipTrigger>
          <TooltipContent side="right" sideOffset={10}>
            <div className="flex flex-col gap-0.5">
              <span className="font-semibold text-xs">Settings & Gateways</span>
              <span className="text-[10px] text-muted-foreground">Broker, AI & Quant configuration</span>
            </div>
          </TooltipContent>
        </Tooltip>

        {/* Expand button */}
        <Tooltip delayDuration={150}>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={onExpand}
              className="flex h-8 w-8 items-center justify-center rounded-lg bg-secondary/80 hover:bg-accent border border-border/60 text-muted-foreground hover:text-foreground transition-colors"
            >
              <PanelLeftOpen className="w-4 h-4" />
            </button>
          </TooltipTrigger>
          <TooltipContent side="right" sideOffset={10}>
            Expand sidebar (⌘B)
          </TooltipContent>
        </Tooltip>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2 p-3 border-t border-border/80 bg-secondary/20">
      {/* Real-time Gateway Telemetry Pill */}
      <div className="flex items-center justify-between px-2 py-1.5 rounded-lg bg-card/60 border border-border/50 shadow-sm">
        <div className="flex items-center gap-2 min-w-0">
          <span className="relative flex h-2 w-2 shrink-0">
            {isStreamLive && (
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            )}
            <span
              className={cn(
                'relative inline-flex rounded-full h-2 w-2',
                isStreamLive ? 'bg-emerald-500' : 'bg-amber-500',
              )}
            />
          </span>
          <div className="flex flex-col min-w-0">
            <span className="text-[10px] font-bold tracking-wider uppercase text-foreground/90 truncate">
              {gatewayLabel}
            </span>
            <span className="text-[9px] text-muted-foreground font-mono">
              {isStreamLive ? 'Live Feed • 14ms' : 'Connecting...'}
            </span>
          </div>
        </div>

        <span
          className={cn(
            'text-[9px] font-bold px-1.5 py-0.5 rounded border',
            isStreamLive
              ? 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20'
              : 'bg-amber-500/10 text-amber-600 border-amber-500/20',
          )}
        >
          {isStreamLive ? 'HEALTHY' : 'SYNC'}
        </span>
      </div>

      {/* Settings Navigation Link */}
      <Link
        href="/settings"
        onClick={onNavigate}
        className={cn(
          'group flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors',
          isSettingsActive
            ? 'bg-primary/10 text-primary ring-1 ring-primary/20'
            : 'text-muted-foreground hover:bg-accent hover:text-foreground',
        )}
      >
        <div className="flex items-center gap-2 min-w-0">
          <Settings className="w-3.5 h-3.5 shrink-0 group-hover:rotate-45 transition-transform duration-200" />
          <span className="truncate">Settings & Gateways</span>
        </div>
        <kbd className="text-[9px] font-mono px-1 py-0.2 rounded bg-muted/70 border border-border/40 text-muted-foreground">
          ⚙
        </kbd>
      </Link>
    </div>
  );
}
