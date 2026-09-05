'use client';

import {
  LayoutDashboard,
  Star,
  Coins,
  Settings,
  Layers,
  TrendingUp,
  Sparkles,
  History,
  Bot,
  BarChart3,
  Radio,
  FileText,
  Activity,
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
    id: 'intelligence',
    label: 'Alpha & Intelligence',
    icon: Sparkles,
    defaultOpen: true,
    items: [
      {
        id: 'market-intel',
        href: '/market-intelligence',
        label: 'Market Intelligence',
        icon: BarChart3,
        description: '4-asset macro breadth & institutional flows',
        keywords: ['breadth', 'fii', 'dii', 'macro', 'nifty', 'banknifty', 'sector'],
      },
      {
        id: 'regime-levels',
        href: '/markets',
        label: 'Regime & Levels',
        icon: TrendingUp,
        description: 'Multi-TF regime classification & pivot targets',
        keywords: ['regime', 'levels', 'support', 'resistance', 'trend', 'volatility'],
      },
      {
        id: 'ai-insights',
        href: '/ai-analysis',
        label: 'AI Deep Insights',
        icon: Sparkles,
        description: 'GenAI reasoning, risk bias & synthesis',
        badgeKey: 'ai',
        keywords: ['ai', 'gemini', 'ollama', 'openrouter', 'reasoning', 'sentiment'],
      },
      {
        id: 'ai-deep-insight',
        href: '/deep-insight',
        label: 'AI Deep Insight v2',
        icon: Bot,
        description: 'Fast signal evaluation, regime-aware trading decisions',
        keywords: ['ai', 'signals', 'regime', 'scalping', 'intraday', 'decision'],
      },
      {
        id: 'historical-intel',
        href: '/historical-intelligence',
        label: 'Historical Patterns',
        icon: History,
        description: 'Historical similarity & forward scenario engine',
        keywords: ['history', 'similarity', 'patterns', 'backtest', 'scenarios'],
      },
    ],
  },
  {
    id: 'execution',
    label: 'Execution & Strategy',
    icon: Activity,
    defaultOpen: true,
    items: [
      {
        id: 'options-desk',
        href: '/options',
        label: 'Options & Greeks',
        icon: Layers,
        description: 'Live option chain, Black-76, Max Pain & PCR',
        shortcut: '⌘2',
        keywords: ['options', 'chain', 'oi', 'greeks', 'iv', 'delta', 'gamma', 'straddle'],
      },
      {
        id: 'signal-center',
        href: '/signals',
        label: 'Signal Center',
        icon: Radio,
        description: 'Real-time multi-strategy alpha alerts',
        badgeKey: 'signals',
        shortcut: '⌘3',
        keywords: ['signals', 'alerts', 'momentum', 'breakout', 'mean-reversion'],
      },
      {
        id: 'paper-trading',
        href: '/paper-trading',
        label: 'Paper Trading',
        icon: FileText,
        description: 'Simulated execution & virtual portfolio',
        shortcut: '⌘4',
        keywords: ['paper', 'sim', 'virtual', 'orders', 'positions', 'pnl'],
      },
    ],
  },
  {
    id: 'assets',
    label: 'Markets & Assets',
    icon: Coins,
    defaultOpen: false,
    items: [
      {
        id: 'crypto-futures',
        href: '/crypto',
        label: 'Crypto Derivatives',
        icon: Coins,
        description: 'Binance USDT-M Futures & live orderbook',
        keywords: ['crypto', 'binance', 'btc', 'eth', 'futures', 'orderbook'],
      },
      {
        id: 'watchlists',
        href: '/watchlist',
        label: 'Watchlists & Baskets',
        icon: Star,
        description: 'Tracked instruments & custom price alerts',
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
    label: 'Settings & Gateways',
    icon: Settings,
    description: 'Broker API, AI model routing & quant params',
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
