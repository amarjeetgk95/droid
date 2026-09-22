export type ModuleNavItem = {
  href: string;
  label: string;
  description: string;
};

export const MODULE_NAV: ModuleNavItem[] = [
  {
    href: '/',
    label: 'Dashboard',
    description: '1m–60m market forecast and context',
  },
  {
    href: '/signals',
    label: 'Signals & Ledger',
    description: 'Generate, execute and track paper P&L',
  },
  {
    href: '/swing',
    label: 'Swing Desk',
    description: 'Multi-day options setups, positions and risk',
  },
  {
    href: '/options',
    label: 'Options & Strategy',
    description: 'Chain, analytics, quant tools, strategies and futures',
  },
  {
    href: '/trade',
    label: 'Trade Ops',
    description: 'Broker orders, positions, sizing and audit',
  },
  {
    href: '/intel',
    label: 'Intel',
    description: 'Institutional flows, market intelligence and event risk',
  },
  {
    href: '/lab',
    label: 'Research Lab',
    description: 'Forecasts, indicators, experiments and ML models',
  },
  {
    href: '/historical-data',
    label: 'Historical Data',
    description: 'Market data acquisition, validation, storage & research',
  },
  {
    href: '/copilot',
    label: 'AI Copilot',
    description: 'Streaming copilot, briefings, analysis and trade audit',
  },
  {
    href: '/ops',
    label: 'Ops Console',
    description: 'Backend health, caches, breakers and pipeline tools',
  },
  {
    href: '/settings',
    label: 'Settings',
    description: 'Broker, quant, AI and paper configuration',
  },
];

export function isActivePath(pathname: string | null, href: string): boolean {
  if (!pathname) return false;
  if (href === '/') return pathname === '/';
  return pathname === href || pathname.startsWith(`${href}/`);
}
