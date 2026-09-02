'use client';

import { memo } from 'react';
import Link from 'next/link';
import { cn } from '@/lib/utils';
import { NavItem } from '../nav-config';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';

interface SidebarNavItemProps {
  item: NavItem;
  active: boolean;
  collapsed?: boolean;
  onNavigate?: () => void;
  badgeData?: { label: string; color: string; pulse?: boolean };
}

export const SidebarNavItem = memo(function SidebarNavItem({
  item,
  active,
  collapsed,
  onNavigate,
  badgeData,
}: SidebarNavItemProps) {
  const Icon = item.icon;

  const content = (
    <Link
      href={item.href}
      aria-current={active ? 'page' : undefined}
      onClick={onNavigate}
      className={cn(
        'group relative flex items-center gap-2.5 rounded-md text-xs font-medium transition-all duration-150 ease-out',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-0',
        collapsed
          ? 'justify-center w-9 h-9 mx-auto'
          : 'w-full px-2.5 py-1.5 h-8',
        active
          ? collapsed
            ? 'bg-primary text-primary-foreground shadow-xs ring-1 ring-primary/30'
            : 'bg-primary/10 text-primary font-semibold'
          : 'text-muted-foreground hover:bg-accent/70 hover:text-foreground',
      )}
    >
      {/* Active left indicator pill when expanded */}
      {active && !collapsed && (
        <span
          className="absolute left-0.5 top-1/2 -translate-y-1/2 h-4 w-0.5 rounded-full bg-primary"
          aria-hidden
        />
      )}

      <Icon
        className={cn(
          'shrink-0 transition-all duration-150',
          collapsed ? 'w-4.5 h-4.5' : 'w-4 h-4',
          active
            ? collapsed
              ? 'text-primary-foreground'
              : 'text-primary'
            : 'opacity-75 group-hover:opacity-100 group-hover:text-foreground',
        )}
      />

      {!collapsed && (
        <div className="flex flex-1 items-center justify-between min-w-0">
          <span className="truncate leading-tight">{item.label}</span>

          <div className="flex items-center gap-1.5 shrink-0 ml-1">
            {badgeData ? (
              <span
                className={cn(
                  'text-[9px] font-bold px-1.5 py-0.5 rounded-full border leading-tight flex items-center gap-1 tabular-nums',
                  badgeData.color,
                )}
              >
                {badgeData.pulse && (
                  <span className="inline-block h-1.5 w-1.5 rounded-full bg-current animate-pulse" />
                )}
                {badgeData.label}
              </span>
            ) : item.shortcut ? (
              <kbd className="hidden group-hover:inline-flex text-[9px] font-mono px-1 py-0.2 rounded bg-muted/70 text-muted-foreground border border-border/40">
                {item.shortcut}
              </kbd>
            ) : null}
          </div>
        </div>
      )}
    </Link>
  );

  if (!collapsed) return content;

  return (
    <Tooltip delayDuration={100}>
      <TooltipTrigger asChild>{content}</TooltipTrigger>
      <TooltipContent side="right" sideOffset={10} className="flex flex-col gap-0.5 max-w-[200px] p-2">
        <div className="flex items-center justify-between gap-2">
          <span className="font-semibold text-xs text-foreground">{item.label}</span>
          {badgeData ? (
            <span className={cn('text-[9px] font-bold px-1.5 py-0.2 rounded border', badgeData.color)}>
              {badgeData.label}
            </span>
          ) : item.shortcut ? (
            <kbd className="text-[9px] font-mono px-1 py-0.2 rounded bg-muted text-muted-foreground border">
              {item.shortcut}
            </kbd>
          ) : null}
        </div>
        {item.description && (
          <span className="text-[10px] text-muted-foreground leading-tight">{item.description}</span>
        )}
      </TooltipContent>
    </Tooltip>
  );
});
