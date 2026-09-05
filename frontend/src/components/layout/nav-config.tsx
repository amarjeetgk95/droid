'use client';

import {
  LayoutDashboard,
  Star,
  Settings,
  Layers,
  TrendingUp,
  History,
  Bot,
  BarChart3,
  Radio,
  Brain,
  Wallet,
  Bitcoin,
  Compass,
  Zap,
  ArrowLeftRight,
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
        id: 'historical-intel',
        href: '/historical-intelligence',
        label: 'Historical Patterns',
        icon: History,
        description: 'What happened last time like this?',
        shortcut: '⌘4',
        keywords: ['history', 'similarity', 'patterns', 'backtest', 'scenarios'],
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
        id: 'ai-research',
        href: '/ai-analysis',
        label: 'AI Research',
        icon: Brain,
        description: 'AI explains market & risk',
        badgeKey: 'ai',
        shortcut: '⌘6',
        keywords: ['ai', 'gemini', 'ollama', 'openrouter', 'reasoning', 'sentiment', 'research'],
      },
      {
        id: 'ai-live',
        href: '/deep-insight',
        label: 'AI Live Calls',
        icon: Bot,
        description: 'Fast AI buy / sell / wait calls',
        shortcut: '⌘7',
        keywords: ['ai', 'signals', 'regime', 'scalping', 'intraday', 'decision', 'live'],
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
        shortcut: '⌘0',
        keywords: ['crypto', 'binance', 'btc', 'eth', 'futures', 'orderbook'],
      },
      {
        id: 'watchlists',
        href: '/watchlist',
        label: 'Watchlists',
        icon: Star,
        description: 'Your tracked stocks & price alerts',
        keywords: ['watchlist', 'favorites', 'instruments', 'baskets', 'tracking'],
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
