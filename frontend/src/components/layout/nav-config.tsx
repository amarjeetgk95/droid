'use client';

import {
  LayoutDashboard,
  Settings,
  Layers,
  TrendingUp,
  Compass,
  Zap,
  Bot,
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
    id: 'context',
    label: 'Context',
    icon: Compass,
    defaultOpen: true,
    items: [
      {
        id: 'markets',
        href: '/markets',
        label: 'Market Context',
        icon: TrendingUp,
        description: 'Trend direction & support / resistance',
        shortcut: '⌘2',
        keywords: ['markets', 'regime', 'levels', 'support', 'resistance', 'trend', 'volatility'],
      },
      {
        id: 'options',
        href: '/options',
        label: 'Derivatives',
        icon: Layers,
        description: 'Option chain, pain points & volatility',
        shortcut: '⌘3',
        keywords: ['options', 'derivatives', 'chain', 'oi', 'greeks', 'iv', 'delta', 'gamma', 'straddle'],
      },
    ],
  },
];

export const STANDALONE_ITEMS: NavItem[] = [
  {
    id: 'war-room',
    href: '/war-room',
    label: 'War Room',
    icon: Zap,
    description: 'Fast single-screen trading desk',
    shortcut: '⌘0',
    badge: 'FAST',
    badgeVariant: 'success',
    keywords: ['war room', 'fast', 'glance', 'verdict', 'trend', 'signals'],
  },
  {
    id: 'forecast',
    href: '/',
    label: 'Tactical Bias',
    icon: LayoutDashboard,
    description: '60-minute tactical directional bias',
    shortcut: '⌘1',
    keywords: ['tactical', 'bias', 'horizon', '60m', 'forecast', 'home', 'overview'],
  },
  {
    id: 'signals',
    href: '/signals',
    label: 'Signals',
    icon: Zap,
    description: 'Active setups & paper trades',
    badgeKey: 'signals',
    keywords: ['signals', 'setups', 'paper', 'trades', 'desk', 'scalp', 'intraday'],
  },
  {
    id: 'swing',
    href: '/swing',
    label: 'Swing Trading',
    icon: TrendingUp,
    description: 'Multi-day positional setups (2–20D)',
    shortcut: '⌘5',
    keywords: ['swing', 'positional', 'vcp', 'pullback', 'stage2', 'breakout', 'equities', 'delivery'],
  },
  {
    id: 'ai',
    href: '/ai',
    label: 'AI Copilot',
    icon: Bot,
    description: 'Chat, analysis, strategy & trade audit',
    shortcut: '⌘4',
    badgeKey: 'ai',
    keywords: ['ai', 'copilot', 'chat', 'analysis', 'strategy', 'briefing', 'deep insight', 'validator'],
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
