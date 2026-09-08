'use client';

import { memo, useCallback } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { cn } from '@/lib/utils';
import { NavItem } from '../nav-config';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { navigationController } from '@/lib/navigationController';

interface SidebarNavItemProps {
  item: NavItem;
  active: boolean;
  collapsed?: boolean;
  onNavigate?: () => void;
  badgeData?: { label: string; color: string; pulse?: boolean };
}

const STATIC_BADGE_STYLES: Record<NonNullable<NavItem['badgeVariant']>, string> = {
  default: 'bg-muted text-muted-foreground border-border/60',
  success: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/30',
  warning: 'bg-amber-500/10 text-amber-600 border-amber-500/30',
  danger: 'bg-rose-500/10 text-rose-600 border-rose-500/30',
  purple: 'bg-purple-500/10 text-purple-600 border-purple-500/30',
  blue: 'bg-blue-500/10 text-blue-600 border-blue-500/30',
};

export const SidebarNavItem = memo(function SidebarNavItem({
  item,
  active,
  collapsed,
  onNavigate,
  badgeData,
}: SidebarNavItemProps) {
  const router = useRouter();
  const Icon = item.icon;

  const handleClick = useCallback(() => {
    if (!active) {
      navigationController.start();
    }
    onNavigate?.();
  }, [active, onNavigate]);

  const handleMouseEnter = useCallback(() => {
    if (!active) {
      router.prefetch(item.href);
    }
  }, [active, item.href, router]);

  const trailing = (
    <div className="flex items-center gap-1.5 shrink-0 ml-2">
      {badgeData ? (
        <span
          className={cn(
            'text-[9px] font-bold px-1.5 py-0.5 rounded-full border leading-none flex items-center gap-1 tabular-nums',
            badgeData.color,
          )}
        >
          {badgeData.pulse && (
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-current animate-pulse" aria-hidden />
          )}
          {badgeData.label}
        </span>
      ) : item.isBeta ? (
        <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-md border leading-none bg-amber-500/10 text-amber-600 border-amber-500/25 tracking-wide">
          BETA
        </span>
      ) : item.badge ? (
        <span
          className={cn(
            'text-[9px] font-bold px-1.5 py-0.5 rounded-full border leading-none tabular-nums',
            STATIC_BADGE_STYLES[item.badgeVariant ?? 'default'],
          )}
        >
          {item.badge}
        </span>
      ) : item.shortcut ? (
        <kbd className="hidden group-hover:inline-flex group-focus-visible:inline-flex text-[10px] font-mono px-1.5 py-0.5 rounded-md bg-muted text-muted-foreground border border-border/60 leading-none">
          {item.shortcut}
        </kbd>
      ) : null}
    </div>
  );

  const content = (
    <Link
      href={item.href}
      aria-current={active ? 'page' : undefined}
      title={item.description ?? item.label}
      onClick={handleClick}
      onMouseEnter={handleMouseEnter}
      onFocus={handleMouseEnter}
      className={cn(
        'group relative flex items-center gap-2.5 rounded-lg text-[13px] font-medium transition-colors duration-150 ease-out',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-0',
        collapsed ? 'justify-center w-9 h-9 mx-auto' : 'w-full px-2.5 py-2 min-h-9',
        active
          ? collapsed
            ? 'bg-primary text-primary-foreground shadow-sm ring-1 ring-primary/30'
            : 'bg-primary/[0.10] text-primary font-semibold ring-1 ring-primary/20'
          : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground active:bg-accent',
      )}
    >
      {/* Active left indicator pill when expanded */}
      {active && !collapsed && (
        <span
          className="absolute left-1 top-1/2 -translate-y-1/2 h-5 w-[3px] rounded-full bg-primary"
          aria-hidden
        />
      )}

      <Icon
        className={cn(
          'shrink-0 w-4 h-4 transition-colors duration-150',
          active
            ? collapsed
              ? 'text-primary-foreground'
              : 'text-primary'
            : 'opacity-70 group-hover:opacity-100 group-hover:text-foreground',
        )}
        aria-hidden
      />

      {!collapsed && (
        <div className="flex flex-1 items-center justify-between min-w-0">
          <span className="truncate leading-tight">{item.label}</span>
          {trailing}
        </div>
      )}
    </Link>
  );

  if (!collapsed) return content;

  return (
    <Tooltip delayDuration={100}>
      <TooltipTrigger asChild>{content}</TooltipTrigger>
      <TooltipContent side="right" sideOffset={10} className="flex flex-col gap-1 max-w-[220px] p-2.5">
        <div className="flex items-center justify-between gap-2">
          <span className="font-semibold text-xs text-foreground">{item.label}</span>
          {badgeData ? (
            <span className={cn('text-[9px] font-bold px-1.5 py-0.5 rounded-full border leading-none', badgeData.color)}>
              {badgeData.label}
            </span>
          ) : item.isBeta ? (
            <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-md border leading-none bg-amber-500/10 text-amber-600 border-amber-500/25">
              BETA
            </span>
          ) : item.badge ? (
            <span
              className={cn(
                'text-[9px] font-bold px-1.5 py-0.5 rounded-full border leading-none',
                STATIC_BADGE_STYLES[item.badgeVariant ?? 'default'],
              )}
            >
              {item.badge}
            </span>
          ) : item.shortcut ? (
            <kbd className="text-[10px] font-mono px-1.5 py-0.5 rounded-md bg-muted text-muted-foreground border border-border/60 leading-none">
              {item.shortcut}
            </kbd>
          ) : null}
        </div>
        {item.description && (
          <span className="text-[11px] text-muted-foreground leading-snug">{item.description}</span>
        )}
      </TooltipContent>
    </Tooltip>
  );
});
