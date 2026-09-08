'use client';

import {
  LayoutDashboard,
  Settings,
  Layers,
  TrendingUp,
  BarChart3,
  Radio,
  Brain,
  Wallet,
  Bitcoin,
  Compass,
  Zap,
  ArrowLeftRight,
  Calendar,
  FlaskConical,
  Gauge,
} from 'lucide-react';
import type { ComponentType } from 'react';

export type NavItem = {
  id: string;
  href: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  description?: string;
  shortcut?: string;
  badge?: string;
  badgeKey?: 'signals' | 'ai' | 'broker';
  badgeVariant?: 'default' | 'success' | 'warning' | 'danger' | 'purple' | 'blue';
  keywords?: string[];
  isBeta?: boolean;
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
    id: 'analyze',
    label: 'Analyze',
    icon: Compass,
    defaultOpen: true,
    items: [
      {
        id: 'market-intel',
        href: '/market-intelligence',
        label: 'Market Intelligence',
        icon: BarChart3,
        description: 'Market breadth & big-player flows',
        shortcut: '⌘2',
        keywords: ['breadth', 'fii', 'dii', 'macro', 'nifty', 'banknifty', 'sector'],
      },
      {
        id: 'regime-levels',
        href: '/markets',
        label: 'Regime & Levels',
        icon: TrendingUp,
        description: 'Trend direction & support / resistance',
        shortcut: '⌘3',
        keywords: ['regime', 'levels', 'support', 'resistance', 'trend', 'volatility'],
      },
      {
        id: 'event-intelligence',
        href: '/events',
        label: 'Event Intelligence',
        icon: Calendar,
        description: 'RBI policy, macro events, impact & setup',
        shortcut: '⌘0',
        keywords: ['events', 'rbi', 'mpc', 'macro', 'policy', 'calendar', 'impact'],
      },
      {
        id: 'research-lab',
        href: '/research',
        label: 'Indicator Research Lab',
        icon: FlaskConical,
        description: 'Proprietary OMPI & cheap validation gate',
        shortcut: '⌘4',
        keywords: ['research', 'indicators', 'ompi', 'backtest', 'lab', 'prediction', 'validation'],
        isBeta: true,
      },
    ],
  },
  {
    id: 'decide',
    label: 'Decide',
    icon: Zap,
    defaultOpen: true,
    items: [
      {
        id: 'signal-center',
        href: '/signals',
        label: 'Signal Center',
        icon: Radio,
        description: 'Live trade ideas & alerts',
        badgeKey: 'signals',
        shortcut: '⌘5',
        keywords: ['signals', 'alerts', 'momentum', 'breakout', 'mean-reversion'],
      },
      {
        id: 'ai-command-center',
        href: '/ai-command-center',
        label: 'AI Command Center',
        icon: Brain,
        description: 'Live AI calls, deep research & strategy tools',
        badgeKey: 'ai',
        shortcut: '⌘6',
        keywords: ['ai', 'signals', 'live calls', 'gemini', 'openrouter', 'reasoning', 'research', 'deep insight', 'command center'],
      },
      {
        id: 'options-intelligence',
        href: '/options-intelligence',
        label: 'Options Intelligence',
        icon: Gauge,
        description: 'AI Research, Greeks, Expected Move & Portfolio Risk',
        shortcut: '⌘7',
        keywords: ['options', 'intelligence', 'greeks', 'expected move', 'contradiction', 'simulation', 'portfolio'],
      },
      {
        id: 'options-desk',
        href: '/options',
        label: 'Options & Greeks',
        icon: Layers,
        description: 'Option chain, pain points & volatility',
        shortcut: '⌘8',
        keywords: ['options', 'chain', 'oi', 'greeks', 'iv', 'delta', 'gamma', 'straddle'],
      },
    ],
  },
  {
    id: 'trade',
    label: 'Trade',
    icon: ArrowLeftRight,
    defaultOpen: true,
    items: [
      {
        id: 'paper-trading',
        href: '/paper-trading',
        label: 'Paper Trading',
        icon: Wallet,
        description: 'Practice trading with virtual money',
        shortcut: '⌘9',
        keywords: ['paper', 'sim', 'virtual', 'orders', 'positions', 'pnl'],
      },
      {
        id: 'crypto-futures',
        href: '/crypto',
        label: 'Crypto Derivatives',
        icon: Bitcoin,
        description: 'Bitcoin & crypto futures orderbook',
        keywords: ['crypto', 'binance', 'btc', 'eth', 'futures', 'orderbook'],
      },
    ],
  },
];

export const STANDALONE_ITEMS: NavItem[] = [
  {
    id: 'dashboard',
    href: '/',
    label: 'Command Dashboard',
    icon: LayoutDashboard,
    description: 'Executive overview, index cards & market health',
    shortcut: '⌘1',
    keywords: ['dashboard', 'home', 'overview', 'indices', 'market status'],
  },
];

export const BOTTOM_ITEMS: NavItem[] = [
  {
    id: 'settings',
    href: '/settings',
    label: 'Settings',
    icon: Settings,
    description: 'Broker, AI models & app preferences',
    shortcut: '⌘,',
    keywords: ['settings', 'config', 'broker', 'fyers', 'api', 'keys', 'models'],
  },
];

export const ALL_NAV_ITEMS: NavItem[] = [
  ...STANDALONE_ITEMS,
  ...NAV_GROUPS.flatMap((g) => g.items),
  ...BOTTOM_ITEMS,
];

export const ALL_NAV_HREFS = ALL_NAV_ITEMS.map((i) => i.href);

export function isGroupActive(pathname: string, group: NavGroup): boolean {
  return group.items.some((i) => isActivePath(pathname, i.href));
}

export function isActivePath(pathname: string, href: string): boolean {
  if (href === '/') return pathname === '/';
  return pathname === href || pathname.startsWith(href + '/');
}

export function findNavItemByHref(href: string): NavItem | undefined {
  return ALL_NAV_ITEMS.find((i) => i.href === href);
}
