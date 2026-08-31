'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  Activity,
  LineChart,
  Search,
  FileText,
  Star,
  Coins,
  Settings,
  ChevronDown,
  Layers,
} from 'lucide-react';
import { getStoredSettings } from '@/lib/settings';

type NavItem = { href: string; label: string };
type NavGroup = {
  id: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  items: NavItem[];
  defaultOpen?: boolean;
};

const GROUPS: NavGroup[] = [
  {
    id: 'intelligence',
    label: 'Intelligence',
    icon: Activity,
    defaultOpen: true,
    items: [
      { href: '/market-intelligence', label: 'Market Intelligence' },
      { href: '/markets', label: 'Regime & Levels' },
    ],
  },
  {
    id: 'analysis',
    label: 'Analysis',
    icon: LineChart,
    defaultOpen: true,
    items: [
      { href: '/chart-analysis', label: 'Chart Forecast' },
      { href: '/ai-analysis', label: 'AI Analysis' },
    ],
  },
  {
    id: 'derivatives',
    label: 'Derivatives',
    icon: Layers,
    defaultOpen: true,
    items: [
      { href: '/futures', label: 'Futures' },
      { href: '/options', label: 'Options' },
      { href: '/strategy', label: 'Strategy' },
    ],
  },
  {
    id: 'discover',
    label: 'Discover',
    icon: Search,
    defaultOpen: false,
    items: [
      { href: '/scanner', label: 'Scanner' },
      { href: '/backtesting', label: 'Backtesting' },
      { href: '/historical-intelligence', label: 'Historical Intel' },
    ],
  },
  {
    id: 'trading',
    label: 'Trading',
    icon: FileText,
    defaultOpen: true,
    items: [
      { href: '/paper-trading', label: 'Paper Trading' },
      { href: '/algo-trading', label: 'Algo Trading' },
    ],
  },
  {
    id: 'personal',
    label: 'Personal',
    icon: Star,
    defaultOpen: false,
    items: [
      { href: '/watchlist', label: 'Watchlist' },
      { href: '/alerts', label: 'Alerts' },
    ],
  },
];

function isGroupActive(pathname: string, group: NavGroup) {
  return group.items.some((i) => pathname === i.href || pathname.startsWith(i.href + '/'));
}

export function Sidebar() {
  const pathname = usePathname();
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});
  const [apiType, setApiType] = useState<string>('indian');

  useEffect(() => {
    try {
      const s = getStoredSettings();
      setApiType(s.broker.apiType);
    } catch {}
    // open groups that contain active route
    const initial: Record<string, boolean> = {};
    for (const g of GROUPS) {
      initial[g.id] = g.defaultOpen || isGroupActive(pathname, g);
    }
    setOpenGroups(initial);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  const toggle = (id: string) => setOpenGroups((p) => ({ ...p, [id]: !p[id] }));

  const isActive = (href: string) => pathname === href;

  return (
    <aside className="w-64 border-r border-border bg-card flex flex-col hidden md:flex shrink-0">
      <div className="h-14 flex items-center px-4 border-b border-border shrink-0">
        <h1 className="text-xl font-bold tracking-tight text-primary flex items-center gap-2">
          <span className="bg-primary text-primary-foreground p-1 rounded">D</span>
          DROID
        </h1>
        <span className="ml-auto text-xs bg-muted text-muted-foreground px-2 py-1 rounded-full font-medium">Phase 1</span>
      </div>

      <nav className="flex-1 overflow-y-auto p-3 space-y-3">
        {/* Dashboard — single primary */}
        <Link
          href="/"
          className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
            isActive('/') ? 'bg-secondary text-primary' : 'text-muted-foreground hover:bg-secondary/50 hover:text-foreground'
          }`}
        >
          <LayoutDashboard className="w-4 h-4" />
          Dashboard
        </Link>

        {/* Grouped navigation */}
        <div className="space-y-1">
          {GROUPS.map((group) => {
            const Icon = group.icon;
            const open = openGroups[group.id] ?? group.defaultOpen;
            const activeGroup = isGroupActive(pathname, group);
            return (
              <div key={group.id} className="space-y-1">
                <button
                  onClick={() => toggle(group.id)}
                  className={`w-full flex items-center gap-2 px-3 py-2 rounded-md text-xs font-semibold tracking-widest uppercase transition-colors ${
                    activeGroup ? 'text-foreground bg-secondary/50' : 'text-muted-foreground hover:bg-secondary/30 hover:text-foreground'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  <span className="flex-1 text-left">{group.label}</span>
                  <ChevronDown className={`w-3 h-3 transition-transform ${open ? 'rotate-180' : ''}`} />
                </button>
                {open && (
                  <div className="ml-2 pl-3 border-l border-border/60 space-y-0.5">
                    {group.items.map((item) => (
                      <Link
                        key={item.href}
                        href={item.href}
                        className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-colors ${
                          isActive(item.href) ? 'bg-secondary text-primary font-medium' : 'text-muted-foreground hover:bg-secondary/50 hover:text-foreground'
                        }`}
                      >
                        {item.label}
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Crypto — conditional, muted when indian */}
        <Link
          href="/crypto"
          className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
            isActive('/crypto')
              ? 'bg-secondary text-primary'
              : apiType === 'crypto'
                ? 'text-muted-foreground hover:bg-secondary/50 hover:text-foreground'
                : 'text-muted-foreground/60 hover:bg-secondary/30 hover:text-foreground'
          }`}
          title={apiType === 'crypto' ? 'Binance' : 'Switch to Crypto in Settings → Broker'}
        >
          <Coins className="w-4 h-4" />
          <span className="flex-1">Crypto</span>
          {apiType !== 'crypto' && <span className="text-[10px] bg-muted px-1.5 py-0.5 rounded">Binance</span>}
        </Link>

        {/* Settings — single */}
        <Link
          href="/settings"
          className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors mt-2 border-t border-border pt-3 ${
            isActive('/settings') ? 'bg-secondary text-primary' : 'text-muted-foreground hover:bg-secondary/50 hover:text-foreground'
          }`}
        >
          <Settings className="w-4 h-4" />
          Settings
        </Link>
      </nav>

      <div className="p-3 border-t border-border">
        <p className="text-[11px] text-muted-foreground leading-tight">17 → 8 menus grouped. Click group header to collapse. Crypto hidden when Broker = Indian.</p>
      </div>
    </aside>
  );
}
