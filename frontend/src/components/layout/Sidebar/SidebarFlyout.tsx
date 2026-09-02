'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';
import { NavGroup, isActivePath, isGroupActive } from '../nav-config';
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
      <Tooltip delayDuration={100}>
        <TooltipTrigger asChild>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className={cn(
                'group relative flex h-9 w-9 items-center justify-center rounded-md transition-all duration-150',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-0 cursor-pointer',
                activeGroup
                  ? 'bg-primary text-primary-foreground shadow-xs ring-1 ring-primary/30'
                  : 'text-muted-foreground hover:bg-accent/80 hover:text-foreground',
              )}
            >
              <GroupIcon className="w-4.5 h-4.5 shrink-0 transition-transform duration-150 group-hover:scale-105" />
              {activeGroup && (
                <span className="absolute -left-1 top-1/2 -translate-y-1/2 h-4 w-1 rounded-r-full bg-primary" />
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
        sideOffset={12}
        align="start"
        className="w-56 p-1.5 shadow-lg rounded-lg border border-border bg-popover animate-in fade-in-50 zoom-in-95"
      >
        <DropdownMenuLabel className="flex items-center justify-between px-2 py-1 text-[11px] font-bold text-foreground">
          <span className="flex items-center gap-1.5">
            <GroupIcon className="w-3.5 h-3.5 text-primary" />
            {group.label}
          </span>
          <span className="text-[10px] font-normal text-muted-foreground">
            {group.items.length} tools
          </span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator className="my-1" />

        <div className="flex flex-col gap-0.5 py-0.5">
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
                    'group flex items-center justify-between gap-2 px-2 py-1.5 rounded-md cursor-pointer text-xs transition-colors',
                    active
                      ? 'bg-primary/10 text-primary font-medium'
                      : 'text-foreground/80 hover:bg-accent hover:text-foreground',
                  )}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <ItemIcon
                      className={cn(
                        'w-3.5 h-3.5 shrink-0',
                        active ? 'text-primary' : 'text-muted-foreground group-hover:text-foreground',
                      )}
                    />
                    <span className="truncate">{item.label}</span>
                  </div>

                  {badge ? (
                    <span
                      className={cn(
                        'text-[9px] font-bold px-1.5 py-0.2 rounded-full border shrink-0',
                        badge.color,
                      )}
                    >
                      {badge.label}
                    </span>
                  ) : item.shortcut ? (
                    <kbd className="text-[9px] font-mono px-1 py-0.2 rounded bg-muted text-muted-foreground border border-border/50 shrink-0">
                      {item.shortcut}
                    </kbd>
                  ) : null}
                </Link>
              </DropdownMenuItem>
            );
          })}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
