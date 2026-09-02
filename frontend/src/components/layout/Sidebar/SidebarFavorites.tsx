'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Star, X, Pin } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ALL_NAV_ITEMS, isActivePath, NavItem } from '../nav-config';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';

const PINNED_STORAGE_KEY = 'droid:sidebar:pinned_workspaces';
const DEFAULT_PINNED = ['/options', '/signals', '/algo-trading'];

interface SidebarFavoritesProps {
  collapsed: boolean;
  onNavigate?: () => void;
}

export function SidebarFavorites({ collapsed, onNavigate }: SidebarFavoritesProps) {
  const pathname = usePathname();
  const [pinnedHrefs, setPinnedHrefs] = useState<string[]>(DEFAULT_PINNED);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(PINNED_STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) {
          setPinnedHrefs(parsed);
        }
      }
    } catch {}
  }, []);

  const savePinned = useCallback((next: string[]) => {
    setPinnedHrefs(next);
    try {
      localStorage.setItem(PINNED_STORAGE_KEY, JSON.stringify(next));
    } catch {}
  }, []);

  const unpinItem = useCallback(
    (e: React.MouseEvent, href: string) => {
      e.preventDefault();
      e.stopPropagation();
      savePinned(pinnedHrefs.filter((h) => h !== href));
    },
    [pinnedHrefs, savePinned],
  );

  const pinnedItems: NavItem[] = pinnedHrefs
    .map((href) => ALL_NAV_ITEMS.find((item) => item.href === href))
    .filter((item): item is NavItem => item !== undefined);

  if (pinnedItems.length === 0) return null;

  if (collapsed) {
    return (
      <div className="flex flex-col items-center gap-1 w-full my-1">
        {pinnedItems.map((item, idx) => {
          const Icon = item.icon;
          const active = isActivePath(pathname, item.href);
          return (
            <Tooltip key={item.href} delayDuration={150}>
              <TooltipTrigger asChild>
                <Link
                  href={item.href}
                  onClick={onNavigate}
                  className={cn(
                    'relative flex h-8 w-8 items-center justify-center rounded-lg transition-all duration-150',
                    active
                      ? 'bg-primary text-primary-foreground shadow-sm ring-1 ring-primary/30'
                      : 'text-muted-foreground hover:bg-accent hover:text-foreground',
                  )}
                >
                  <Icon className="w-4 h-4" />
                  <span className="absolute -top-0.5 -right-0.5 text-[8px] font-bold text-amber-500">★</span>
                </Link>
              </TooltipTrigger>
              <TooltipContent side="right" sideOffset={10}>
                <div className="flex items-center gap-1.5">
                  <span className="font-semibold text-xs">{item.label}</span>
                  <span className="text-[10px] text-amber-500">Pinned (⌘{idx + 1})</span>
                </div>
              </TooltipContent>
            </Tooltip>
          );
        })}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1 px-3 py-1">
      <div className="flex items-center justify-between px-1.5 py-0.5 text-[10px] font-semibold tracking-wider uppercase text-muted-foreground">
        <span className="flex items-center gap-1">
          <Star className="w-3 h-3 text-amber-500 fill-amber-500/30" />
          Pinned Workspaces
        </span>
        <span className="text-[9px] opacity-60">⌘1 - ⌘{pinnedItems.length}</span>
      </div>

      <div className="flex flex-col gap-0.5">
        {pinnedItems.map((item, idx) => {
          const Icon = item.icon;
          const active = isActivePath(pathname, item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              className={cn(
                'group relative flex items-center justify-between gap-2.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-all duration-150',
                active
                  ? 'bg-primary/10 text-primary ring-1 ring-primary/15'
                  : 'text-muted-foreground hover:bg-accent/70 hover:text-foreground',
              )}
            >
              {active && (
                <span className="absolute left-0 top-1/2 -translate-y-1/2 h-4 w-0.5 rounded-full bg-primary" />
              )}
              <div className="flex items-center gap-2 min-w-0">
                <Icon className={cn('w-3.5 h-3.5 shrink-0', active ? 'text-primary' : 'opacity-80 group-hover:opacity-100')} />
                <span className="truncate">{item.label}</span>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <kbd className="text-[9px] font-mono px-1 py-0.2 rounded bg-muted/60 text-muted-foreground border border-border/40 group-hover:hidden">
                  ⌘{idx + 1}
                </kbd>
                <button
                  type="button"
                  onClick={(e) => unpinItem(e, item.href)}
                  title="Unpin"
                  className="hidden group-hover:flex items-center justify-center p-0.5 rounded text-muted-foreground hover:text-foreground hover:bg-muted"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
