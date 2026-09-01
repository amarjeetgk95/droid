'use client';

import {
  LayoutDashboard,
  Activity,
  LineChart,
  Search,
  FileText,
  Star,
  Coins,
  Settings,
  Layers,
  TrendingUp,
  Sparkles,
  History,
  Bot,
  BarChart3,
  Zap,
  Radio,
} from 'lucide-react';
import type { ComponentType } from 'react';

export type NavItem = {
  href: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  description?: string;
  badge?: string;
  keywords?: string[];
};

export type NavGroup = {
  id: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  items: NavItem[];
  defaultOpen?: boolean;
};

export const NAV_GROUPS: NavGroup[] = [
  {
    id: 'intelligence',
    label: 'Intelligence',
    icon: Activity,
    defaultOpen: true,
    items: [
      { href: '/market-intelligence', label: 'Market Intelligence', icon: BarChart3, description: '4-asset universe' },
      { href: '/markets', label: 'Regime & Levels', icon: TrendingUp, description: 'Levels & regime' },
    ],
  },
  {
    id: 'analysis',
    label: 'Analysis',
    icon: LineChart,
    defaultOpen: true,
    items: [
      { href: '/ai-analysis', label: 'AI Analysis', icon: Sparkles, description: 'AI insights' },
    ],
  },
  {
    id: 'derivatives',
    label: 'Derivatives',
    icon: Layers,
    defaultOpen: true,
    items: [
      { href: '/options', label: 'Options', icon: Layers, description: 'Chain & IV' },
    ],
  },
  {
    id: 'signals',
    label: 'Signals',
    icon: Zap,
    defaultOpen: true,
    items: [
      { href: '/signals', label: 'Signal Center', icon: Radio, description: 'Generate & dispatch' },
    ],
  },
  {
    id: 'discover',
    label: 'Discover',
    icon: Search,
    defaultOpen: false,
    items: [
      { href: '/historical-intelligence', label: 'Historical Intel', icon: History, description: 'Similarity & scenarios' },
    ],
  },
  {
    id: 'trading',
    label: 'Trading',
    icon: FileText,
    defaultOpen: true,
    items: [
      { href: '/paper-trading', label: 'Paper Trading', icon: FileText, description: 'Virtual P&L' },
      { href: '/algo-trading', label: 'Algo Trading', icon: Bot, description: 'Automated' },
    ],
  },
  {
    id: 'personal',
    label: 'Personal',
    icon: Star,
    defaultOpen: false,
    items: [
      { href: '/watchlist', label: 'Watchlist', icon: Star, description: 'Tracked instruments' },
    ],
  },
];

export const STANDALONE_ITEMS: NavItem[] = [
  { href: '/', label: 'Dashboard', icon: LayoutDashboard, description: 'Overview' },
];

export const BOTTOM_ITEMS: NavItem[] = [
  { href: '/crypto', label: 'Crypto', icon: Coins, description: 'Binance live' },
  { href: '/settings', label: 'Settings', icon: Settings, description: 'Preferences & broker' },
];

export function isGroupActive(pathname: string, group: NavGroup): boolean {
  return group.items.some((i) => pathname === i.href || pathname.startsWith(i.href + '/'));
}

export function isActivePath(pathname: string, href: string): boolean {
  if (href === '/') return pathname === '/';
  return pathname === href || pathname.startsWith(href + '/');
}

export const ALL_NAV_HREFS = [
  ...STANDALONE_ITEMS.map((i) => i.href),
  ...NAV_GROUPS.flatMap((g) => g.items.map((i) => i.href)),
  ...BOTTOM_ITEMS.map((i) => i.href),
];
