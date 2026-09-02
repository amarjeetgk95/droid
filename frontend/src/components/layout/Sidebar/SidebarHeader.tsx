'use client';

import { useState, useEffect } from 'react';
import {
  Sparkles,
  ChevronDown,
  PanelLeftClose,
  PanelLeftOpen,
  X,
  Check,
  Building2,
  Wallet,
  Coins,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';

const DESK_STORAGE_KEY = 'droid:active_desk';

export type DeskOption = {
  id: string;
  name: string;
  badge: string;
  type: 'paper' | 'live' | 'crypto';
  account: string;
  icon: typeof Building2;
};

const BROKER_DESK_MAP: Record<string, { id: string; name: string; account: string }> = {
  fyers: { id: 'fyers-live', name: 'Fyers Live Desk', account: 'FYERS • Institutional' },
  upstox: { id: 'upstox-live', name: 'Upstox Live Desk', account: 'UPSTOX • Official V2' },
  kotak_neo: { id: 'kotak-live', name: 'Kotak Neo Desk', account: 'KOTAK NEO • Session' },
};

function getDeskOptions(provider: string = 'fyers'): DeskOption[] {
  const liveInfo = BROKER_DESK_MAP[provider] || BROKER_DESK_MAP.fyers;
  return [
    {
      id: 'paper-sim',
      name: 'Paper Sim Desk',
      badge: 'SIM',
      type: 'paper',
      account: 'ACC-9842 • ₹10.0L',
      icon: Wallet,
    },
    {
      id: liveInfo.id,
      name: liveInfo.name,
      badge: 'LIVE',
      type: 'live',
      account: liveInfo.account,
      icon: Building2,
    },
    {
      id: 'binance-crypto',
      name: 'Binance USDT-M',
      badge: 'CRYPTO',
      type: 'crypto',
      account: 'BINANCE • Live Sub',
      icon: Coins,
    },
  ];
}

interface SidebarHeaderProps {
  collapsed: boolean;
  isMobile?: boolean;
  onToggleCollapse?: () => void;
  onCloseMobile?: () => void;
}

export function SidebarHeader({
  collapsed,
  isMobile,
  onToggleCollapse,
  onCloseMobile,
}: SidebarHeaderProps) {
  const [provider, setProvider] = useState<string>('fyers');
  const [selectedDeskId, setSelectedDeskId] = useState<string>('fyers-live');

  useEffect(() => {
    try {
      const s = localStorage.getItem('droid_app_settings_v1');
      if (s) {
        const parsed = JSON.parse(s);
        const p = parsed?.broker?.provider || 'fyers';
        setProvider(p);
        const liveInfo = BROKER_DESK_MAP[p] || BROKER_DESK_MAP.fyers;
        const saved = localStorage.getItem(DESK_STORAGE_KEY);
        setSelectedDeskId(saved && (saved === 'paper-sim' || saved === 'binance-crypto') ? saved : liveInfo.id);
      }
    } catch {}

    const onStorage = (e: StorageEvent) => {
      if (e.key === 'droid_app_settings_v1' && e.newValue) {
        try {
          const parsed = JSON.parse(e.newValue);
          const p = parsed?.broker?.provider || 'fyers';
          setProvider(p);
          const liveInfo = BROKER_DESK_MAP[p] || BROKER_DESK_MAP.fyers;
          const saved = localStorage.getItem(DESK_STORAGE_KEY);
          setSelectedDeskId(saved && (saved === 'paper-sim' || saved === 'binance-crypto') ? saved : liveInfo.id);
        } catch {}
      }
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const deskOptions = getDeskOptions(provider);

  const handleSelectDesk = (id: string) => {
    setSelectedDeskId(id);
    try {
      localStorage.setItem(DESK_STORAGE_KEY, id);
    } catch {}
  };

  const currentDesk = deskOptions.find((d) => d.id === selectedDeskId) || deskOptions[1];
  const DeskIcon = currentDesk.icon;

  return (
    <div
      className={cn(
        'flex h-14 shrink-0 items-center gap-2 border-b border-border/80 px-3 transition-all duration-200',
        collapsed && !isMobile && 'justify-center px-2',
      )}
    >
      {/* Brand Identity / Desk Selector */}
      {!collapsed || isMobile ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className={cn(
                'group flex flex-1 items-center gap-2.5 rounded-lg p-1.5 text-left transition-colors duration-150',
                'hover:bg-accent/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring min-w-0',
              )}
            >
              {/* Logo Hexagon / Shield */}
              <div className="relative flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground font-bold text-xs tracking-wider shadow-sm ring-1 ring-primary/30">
                <span>D</span>
                <span className="absolute -bottom-0.5 -right-0.5 flex h-2.5 w-2.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500" />
                </span>
              </div>

              {/* Title and Desk info */}
              <div className="flex flex-col min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <span className="font-bold tracking-tight text-xs text-foreground uppercase">
                    DROID
                  </span>
                  <span className="text-[9px] font-semibold uppercase tracking-wider px-1 py-0.2 rounded bg-primary/10 text-primary border border-primary/20">
                    PRO
                  </span>
                </div>
                <div className="flex items-center gap-1 text-[11px] text-muted-foreground truncate">
                  <span className="truncate max-w-[110px] font-medium text-foreground/80">
                    {currentDesk.name}
                  </span>
                  <ChevronDown className="w-3 h-3 shrink-0 opacity-60 group-hover:opacity-100 transition-opacity" />
                </div>
              </div>
            </button>
          </DropdownMenuTrigger>

          <DropdownMenuContent align="start" className="w-56 p-1.5 shadow-xl">
            <DropdownMenuLabel className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground px-2 py-1">
              Select Trading Desk
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            {deskOptions.map((desk) => {
              const Icon = desk.icon;
              const isSelected = desk.id === selectedDeskId;
              return (
                <DropdownMenuItem
                  key={desk.id}
                  onClick={() => handleSelectDesk(desk.id)}
                  className={cn(
                    'flex items-center gap-2.5 px-2.5 py-2 cursor-pointer rounded-md text-xs',
                    isSelected && 'bg-primary/10 text-primary font-medium',
                  )}
                >
                  <Icon className={cn('w-4 h-4 shrink-0', isSelected ? 'text-primary' : 'text-muted-foreground')} />
                  <div className="flex flex-col flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <span className="truncate">{desk.name}</span>
                      <span
                        className={cn(
                          'text-[9px] font-bold px-1 rounded',
                          desk.type === 'live'
                            ? 'bg-emerald-500/15 text-emerald-600'
                            : desk.type === 'crypto'
                            ? 'bg-amber-500/15 text-amber-600'
                            : 'bg-blue-500/15 text-blue-600',
                        )}
                      >
                        {desk.badge}
                      </span>
                    </div>
                    <span className="text-[10px] text-muted-foreground">{desk.account}</span>
                  </div>
                  {isSelected && <Check className="w-3.5 h-3.5 text-primary shrink-0 ml-1" />}
                </DropdownMenuItem>
              );
            })}
          </DropdownMenuContent>
        </DropdownMenu>
      ) : (
        /* Collapsed Logo */
        <Tooltip delayDuration={200}>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={onToggleCollapse}
              className="relative flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground font-bold text-xs tracking-wider shadow-sm ring-1 ring-primary/30"
            >
              <span>D</span>
              <span className="absolute -bottom-0.5 -right-0.5 flex h-2 w-2">
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
              </span>
            </button>
          </TooltipTrigger>
          <TooltipContent side="right" sideOffset={10}>
            <div className="flex flex-col gap-0.5">
              <span className="font-bold text-xs">DROID PRO TERMINAL</span>
              <span className="text-[10px] text-muted-foreground">{currentDesk.name}</span>
            </div>
          </TooltipContent>
        </Tooltip>
      )}

      {/* Desktop collapse toggle */}
      {!isMobile && !collapsed && (
        <Tooltip delayDuration={200}>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={onToggleCollapse}
              aria-label="Collapse sidebar (⌘B)"
              className={cn(
                'inline-flex items-center justify-center rounded-md h-7 w-7 shrink-0 border border-transparent',
                'text-muted-foreground hover:text-foreground hover:bg-accent/80 hover:border-border transition-colors',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
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

      {/* Mobile close */}
      {isMobile && (
        <button
          type="button"
          onClick={onCloseMobile}
          aria-label="Close navigation"
          className="ml-auto inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <X className="w-4 h-4" />
        </button>
      )}
    </div>
  );
}
