'use client';

/**
 * Single source of truth for shell navigation (sidebar + breadcrumb +
 * command palette + global shortcuts).
 *
 * Every entry maps 1:1 to a real route under `src/app/(app)` — no dead links,
 * no split-brain sidebar. Groups render as labelled sections in the expanded
 * rail and as hover flyouts in the collapsed rail.
 */

import {
  Activity,
  Bot,
  BookOpenCheck,
  Compass,
  Crosshair,
  FlaskConical,
  Gauge,
  Hammer,
  Layers,
  LayoutDashboard,
  LineChart,
  Microscope,
  Radar,
  Radio,
  Rocket,
  ServerCog,
  Settings,
  ShieldAlert,
  TrendingUp,
  Zap,
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
  badgeVariant?: 'default' | 'success' | 'warning' | 'danger' | 'blue';
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
    id: 'command',
    label: 'Command',
    icon: Gauge,
    defaultOpen: true,
    items: [
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
    ],
  },
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
      {
        id: 'intel',
        href: '/intel',
        label: 'Intel Hub',
        icon: Radar,
        description: 'Market microstructure, regime & evidence',
        keywords: ['intel', 'intelligence', 'regime', 'evidence', 'flow', 'microstructure', 'breakout'],
      },
    ],
  },
  {
    id: 'signals',
    label: 'Signals',
    icon: Activity,
    defaultOpen: true,
    items: [
      {
        id: 'signals',
        href: '/signals',
        label: 'Signals',
        icon: Radio,
        description: 'Active setups & paper trades',
        badgeKey: 'signals',
        keywords: ['signals', 'setups', 'paper', 'trades', 'desk', 'scalp', 'intraday'],
      },
      {
        id: 'forge',
        href: '/forge',
        label: 'Signal Forge',
        icon: Hammer,
        description: 'Generate & confirm intraday setups',
        keywords: ['forge', 'generate', 'confirm', 'ai', 'workbench', 'scanner'],
      },
      {
        id: 'swing',
        href: '/swing',
        label: 'Swing Trading',
        icon: LineChart,
        description: 'Multi-day positional setups (2–20D)',
        shortcut: '⌘5',
        keywords: ['swing', 'positional', 'vcp', 'pullback', 'stage2', 'breakout', 'equities', 'delivery'],
      },
    ],
  },
  {
    id: 'execution',
    label: 'Execution & AI',
    icon: Rocket,
    defaultOpen: true,
    items: [
      {
        id: 'execute',
        href: '/execute',
        label: 'Execution Cockpit',
        icon: Crosshair,
        description: 'Orders, algo state, capital & safety',
        keywords: ['execute', 'execution', 'orders', 'algo', 'capital', 'limits', 'cockpit'],
      },
      {
        id: 'ai',
        href: '/ai',
        label: 'AI Copilot',
        icon: Bot,
        description: 'Chat, analysis, strategy & trade audit',
        shortcut: '⌘4',
        keywords: ['ai', 'copilot', 'chat', 'analysis', 'strategy', 'briefing', 'deep insight', 'validator'],
      },
    ],
  },
  {
    id: 'research',
    label: 'Research & Risk',
    icon: FlaskConical,
    defaultOpen: true,
    items: [
      {
        id: 'lab',
        href: '/lab',
        label: 'Research Lab',
        icon: Microscope,
        description: 'Indicators, experiments & model research',
        keywords: ['lab', 'research', 'experiment', 'indicator', 'backtest', 'models'],
      },
      {
        id: 'research',
        href: '/research',
        label: 'Financial Research',
        icon: BookOpenCheck,
        description: 'Fundamentals, filings & event studies',
        keywords: ['research', 'fundamental', 'financial', 'filings', 'events', 'quant'],
      },
      {
        id: 'risk',
        href: '/risk',
        label: 'Risk Matrix',
        icon: ShieldAlert,
        description: 'Portfolio risk, greeks & exposure',
        keywords: ['risk', 'portfolio', 'exposure', 'greeks', 'var', 'drawdown', 'matrix'],
      },
    ],
  },
];

/** Items pinned above the groups (none today — kept for API compatibility). */
export const STANDALONE_ITEMS: NavItem[] = [];

export const BOTTOM_ITEMS: NavItem[] = [
  {
    id: 'system',
    href: '/system',
    label: 'System Nerve',
    icon: ServerCog,
    description: 'Ops, providers & platform diagnostics',
    keywords: ['system', 'ops', 'config', 'providers', 'logs', 'health', 'diagnostics'],
  },
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

/** Resolve a shortcut label (e.g. `⌘2`) to its nav item, if one is bound. */
export function findNavItemByShortcut(shortcut: string): NavItem | undefined {
  return ALL_NAV_ITEMS.find((i) => i.shortcut === shortcut);
}
