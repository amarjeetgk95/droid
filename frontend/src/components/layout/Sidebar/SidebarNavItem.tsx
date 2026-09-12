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
        'group relative flex items-center gap-2.5 text-[12.5px] font-medium transition-colors duration-120 select-none',
        'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary',
        collapsed ? 'justify-center w-8 h-8 mx-auto rounded-[4px]' : 'w-full px-2.5 py-1.5 min-h-[34px] rounded-[4px]',
        active
          ? collapsed
            ? 'text-white bg-primary shadow-xs'
            : 'bg-[#edf4fc] text-[#387ed1] font-semibold border-l-2 border-[#387ed1] rounded-r-[4px] rounded-l-none'
          : 'text-[#666666] hover:bg-[#f7f7f7] hover:text-[#333333] active:bg-[#f0f0f0]',
      )}
    >
      <Icon
        className={cn(
          'shrink-0 w-4 h-4 transition-colors duration-120',
          active
            ? collapsed
              ? 'text-white'
              : 'text-[#387ed1]'
            : 'text-[#888888] group-hover:text-[#333333]',
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
