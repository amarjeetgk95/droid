'use client';

import { useRef, useState } from 'react';
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
  const openTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeGroup = isGroupActive(pathname, group);
  const GroupIcon = group.icon;
  const hasLiveBadge = group.items.some((i) => i.badgeKey && telemetryBadges?.[i.badgeKey]);

  const scheduleOpen = () => {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    if (open) return;
    if (openTimer.current) clearTimeout(openTimer.current);
    openTimer.current = setTimeout(() => setOpen(true), 150);
  };

  const scheduleClose = () => {
    if (openTimer.current) clearTimeout(openTimer.current);
    if (closeTimer.current) clearTimeout(closeTimer.current);
    closeTimer.current = setTimeout(() => setOpen(false), 100);
  };

  const cancelTimers = () => {
    if (openTimer.current) clearTimeout(openTimer.current);
    if (closeTimer.current) clearTimeout(closeTimer.current);
  };

  return (
    <div onMouseEnter={scheduleOpen} onMouseLeave={scheduleClose}>
    <DropdownMenu open={open} onOpenChange={(v) => { cancelTimers(); setOpen(v); }}>
      <Tooltip delayDuration={200}>
        <TooltipTrigger asChild>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              aria-label={`${group.label} menu`}
              aria-expanded={open}
              aria-haspopup="menu"
              onFocus={scheduleOpen}
              className={cn(
                'group relative flex h-9 w-9 items-center justify-center rounded-lg transition-all duration-150',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-0 cursor-pointer',
                activeGroup
                  ? 'bg-primary text-primary-foreground shadow-xs ring-1 ring-primary/30'
                  : 'text-muted-foreground hover:bg-accent/80 hover:text-foreground',
              )}
            >
              <GroupIcon className="w-[18px] h-[18px] shrink-0 transition-transform duration-150 group-hover:scale-105" />
              {activeGroup && (
                <span className="absolute -left-[7px] top-1/2 -translate-y-1/2 h-5 w-[3px] rounded-r-full bg-primary" />
              )}
              {hasLiveBadge && !activeGroup && (
                <span className="absolute top-1 right-1 h-1.5 w-1.5 rounded-full bg-emerald-500 ring-2 ring-card" aria-hidden />
              )}
            </button>
          </DropdownMenuTrigger>
        </TooltipTrigger>
        {!open && (
          <TooltipContent side="right" sideOffset={10}>
            <span className="font-semibold text-xs">{group.label}</span>
            <span className="block text-[10px] text-muted-foreground">{group.items.length} pages • hover to preview</span>
          </TooltipContent>
        )}
      </Tooltip>

      <DropdownMenuContent
        side="right"
        sideOffset={12}
        align="start"
        onMouseEnter={cancelTimers}
        onMouseLeave={scheduleClose}
        className="w-60 p-1.5 shadow-lg rounded-xl border border-border bg-popover"
      >
        <DropdownMenuLabel className="flex items-center justify-between px-2 py-1.5 text-xs font-bold text-foreground">
          <span className="flex items-center gap-1.5">
            <GroupIcon className="w-3.5 h-3.5 text-primary" />
            {group.label}
          </span>
          <span className="text-[10px] font-normal text-muted-foreground">
            {group.items.length} pages
          </span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator className="my-1" />

        <div className="flex flex-col gap-0.5 py-0.5">
          {group.items.map((item) => {
            const ItemIcon = item.icon;
            const active = isActivePath(pathname, item.href);
            const badge = item.badgeKey ? telemetryBadges?.[item.badgeKey] : undefined;

            return (
              <DropdownMenuItem key={item.href} asChild onSelect={() => setOpen(false)}>
                <Link
                  href={item.href}
                  aria-current={active ? 'page' : undefined}
                  onClick={() => {
                    setOpen(false);
                    if (onNavigate) onNavigate();
                  }}
                  className={cn(
                    'flex items-center justify-between gap-2 px-2 py-2 rounded-lg cursor-pointer text-[13px] transition-colors',
                    active
                      ? 'bg-primary/[0.12] text-primary font-semibold ring-1 ring-primary/20'
                      : 'text-foreground/80 hover:bg-accent hover:text-foreground',
                  )}
                >
                  <span className="flex items-center gap-2 min-w-0">
                    <ItemIcon
                      className={cn(
                        'w-4 h-4 shrink-0',
                        active ? 'text-primary' : 'text-muted-foreground group-hover:text-foreground',
                      )}
                    />
                    <span className="truncate">{item.label}</span>
                  </span>

                  {badge ? (
                    <span
                      className={cn(
                        'text-[10px] font-bold px-1.5 py-0.5 rounded-full border shrink-0 tabular-nums',
                        badge.color,
                      )}
                    >
                      {badge.label}
                    </span>
                  ) : item.shortcut ? (
                    <kbd className="text-[10px] font-mono px-1.5 py-0.5 rounded-md bg-muted text-muted-foreground border border-border/50 shrink-0">
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
    </div>
  );
}
