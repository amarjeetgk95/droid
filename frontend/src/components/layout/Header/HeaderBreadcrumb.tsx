'use client';

import { usePathname } from 'next/navigation';
import { ChevronRight, LayoutDashboard } from 'lucide-react';
import { ALL_NAV_ITEMS, NAV_GROUPS, STANDALONE_ITEMS, NavItem } from '../nav-config';

interface BreadcrumbInfo {
  group: string | null;
  label: string;
  icon: typeof LayoutDashboard;
}

function resolveBreadcrumb(pathname: string): BreadcrumbInfo {
  // 1. Check standalone items (e.g. dashboard)
  const standalone = STANDALONE_ITEMS.find(
    (item) => item.href === pathname || (item.href !== '/' && pathname.startsWith(item.href)),
  );
  if (standalone) {
    return {
      group: null,
      label: standalone.label,
      icon: standalone.icon as typeof LayoutDashboard,
    };
  }

  // 2. Check grouped items
  for (const group of NAV_GROUPS) {
    const matchedItem = group.items.find(
      (item) => item.href === pathname || pathname.startsWith(item.href + '/'),
    );
    if (matchedItem) {
      return {
        group: group.label,
        label: matchedItem.label,
        icon: matchedItem.icon as typeof LayoutDashboard,
      };
    }
  }

  // 3. Check all nav items fallback
  const fallbackItem = ALL_NAV_ITEMS.find((item: NavItem) =>
    item.href === '/' ? pathname === '/' : pathname.startsWith(item.href),
  );
  if (fallbackItem) {
    return {
      group: null,
      label: fallbackItem.label,
      icon: fallbackItem.icon as typeof LayoutDashboard,
    };
  }

  // Default / Unknown route fallback
  const cleanSegment = pathname.replace(/^\//, '').split('/')[0];
  const formatted = cleanSegment
    ? cleanSegment.charAt(0).toUpperCase() + cleanSegment.slice(1).replace(/-/g, ' ')
    : 'Dashboard';

  return {
    group: null,
    label: formatted,
    icon: LayoutDashboard,
  };
}

export function HeaderBreadcrumb() {
  const pathname = usePathname();
  const breadcrumb = resolveBreadcrumb(pathname);
  const Icon = breadcrumb.icon;

  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-xs select-none min-w-0">
      {breadcrumb.group && (
        <>
          <span className="hidden xl:inline text-muted-foreground font-medium truncate max-w-[130px]">
            {breadcrumb.group}
          </span>
          <ChevronRight className="hidden xl:inline w-3 h-3 text-muted-foreground/50 shrink-0" />
        </>
      )}

      <div className="flex items-center gap-1.5 min-w-0">
        <div className="hidden sm:flex h-5 w-5 rounded items-center justify-center bg-secondary/80 text-foreground shrink-0 border border-border/60">
          <Icon className="w-3 h-3 text-primary" />
        </div>
        <span className="font-semibold text-foreground truncate tracking-tight text-xs sm:text-[13px]">
          {breadcrumb.label}
        </span>
      </div>
    </nav>
  );
}
