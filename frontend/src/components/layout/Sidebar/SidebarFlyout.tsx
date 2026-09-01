'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ChevronRight, ArrowUpRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { NavGroup, NavItem, isActivePath, isGroupActive } from '../nav-config';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';

interface SidebarFlyoutProps {
  group: NavGroup;
  onNavigate?: () => void;
  telemetryBadges?: Record<string, { label: string; color: string; pulse?: boolean }>;
}

export function SidebarFlyout({ group, onNavigate, telemetryBadges }: SidebarFlyoutProps) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const activeGroup = isGroupActive(pathname, group);
  const GroupIcon = group.icon;

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <Tooltip delayDuration={150}>
        <TooltipTrigger asChild>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className={cn(
                'group relative flex h-10 w-10 items-center justify-center rounded-xl transition-all duration-150',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-0',
                activeGroup
                  ? 'bg-primary text-primary-foreground shadow-md ring-1 ring-primary/30'
                  : 'text-muted-foreground hover:bg-accent/80 hover:text-foreground',
              )}
            >
              <GroupIcon className={cn('w-5 h-5 shrink-0 transition-transform duration-150 group-hover:scale-105')} />
              {activeGroup && (
                <span className="absolute -left-1 top-1/2 -translate-y-1/2 h-5 w-1 rounded-r-full bg-primary" />
              )}
            </button>
          </DropdownMenuTrigger>
        </TooltipTrigger>
        {!open && (
          <TooltipContent side="right" sideOffset={10}>
            <span className="font-semibold text-xs">{group.label}</span>
          </TooltipContent>
        )}
      </Tooltip>

      <DropdownMenuContent
        side="right"
        sideOffset={14}
        align="start"
        className="w-64 p-2 shadow-2xl rounded-xl border border-border/80 bg-popover/95 backdrop-blur-md animate-in fade-in-50 zoom-in-95"
      >
        <DropdownMenuLabel className="flex items-center justify-between px-2 py-1.5 text-xs font-bold text-foreground">
          <span className="flex items-center gap-1.5">
            <GroupIcon className="w-4 h-4 text-primary" />
            {group.label}
          </span>
          <span className="text-[10px] font-normal text-muted-foreground">
            {group.items.length} tools
          </span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />

        <div className="flex flex-col gap-1 py-1">
          {group.items.map((item) => {
            const ItemIcon = item.icon;
            const active = isActivePath(pathname, item.href);
            const badge = item.badgeKey ? telemetryBadges?.[item.badgeKey] : undefined;

            return (
              <DropdownMenuItem key={item.href} asChild>
                <Link
                  href={item.href}
                  onClick={() => {
                    setOpen(false);
                    if (onNavigate) onNavigate();
                  }}
                  className={cn(
                    'group flex items-start gap-2.5 p-2 rounded-lg cursor-pointer transition-all duration-150',
                    active
                      ? 'bg-primary/15 text-primary font-medium'
                      : 'hover:bg-accent hover:text-foreground',
                  )}
                >
                  <ItemIcon
                    className={cn(
                      'w-4 h-4 mt-0.5 shrink-0 transition-colors',
                      active ? 'text-primary' : 'text-muted-foreground group-hover:text-foreground',
                    )}
                  />
                  <div className="flex flex-col flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-1">
                      <span className={cn('text-xs font-medium truncate', active && 'text-primary')}>
                        {item.label}
                      </span>
                      {badge ? (
                        <span
                          className={cn(
                            'text-[9px] font-bold px-1.5 py-0.2 rounded-full border',
                            badge.color,
                          )}
                        >
                          {badge.label}
                        </span>
                      ) : item.shortcut ? (
                        <kbd className="text-[9px] font-mono px-1 py-0.2 rounded bg-muted/70 text-muted-foreground border border-border/50">
                          {item.shortcut}
                        </kbd>
                      ) : null}
                    </div>
                    {item.description && (
                      <span className="text-[10px] text-muted-foreground leading-tight mt-0.5 line-clamp-1">
                        {item.description}
                      </span>
                    )}
                  </div>
                </Link>
              </DropdownMenuItem>
            );
          })}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
