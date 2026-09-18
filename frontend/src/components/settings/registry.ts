'use client';

import {
  Palette,
  Bot,
  KeyRound,
  Sliders,
  FileText,
  Send,
  Activity,
  BrainCircuit,
  type LucideIcon,
} from 'lucide-react';

export type SettingsTabId =
  | 'preferences'
  | 'ai'
  | 'broker'
  | 'quantitative'
  | 'paper'
  | 'telegram'
  | 'monitoring'
  | 'ml'
  | 'system';

/** Sections persisted through SettingsProvider. Telegram, monitoring, ml and system manage themselves. */
export type SettingsSaveableId = Exclude<SettingsTabId, 'telegram' | 'monitoring' | 'ml' | 'system'>;

export interface SettingsTabDef {
  id: SettingsTabId;
  label: string;
  description: string;
  icon: LucideIcon;
  /** Extra search terms — field labels and aliases living inside each tab. */
  keywords: string[];
}

export const SETTINGS_TABS: readonly SettingsTabDef[] = [
  {
    id: 'preferences',
    label: 'Preferences',
    description: 'Display formatting, number systems & configuration backups',
    icon: Palette,
    keywords: [
      'theme', 'dark', 'light', 'appearance', 'number format', 'indian', 'international',
      'lakh', 'crore', 'currency', 'benchmark', 'index', 'nifty', 'banknifty', 'sensex',
      'export', 'import', 'backup', 'restore', 'reset', 'defaults', 'snapshot',
    ],
  },
  {
    id: 'ai',
    label: 'AI Engine',
    description: 'Inference runtime, model routing & analyst persona',
    icon: Bot,
    keywords: [
      'openrouter', 'model', 'api key', 'ollama', 'gemini', 'openai', 'novita', 'nvidia',
      'custom', 'provider', 'routing', 'task', 'persona', 'temperature', 'fallback',
      'cache', 'ttl', 'inference', 'analyst', 'local',
    ],
  },
  {
    id: 'broker',
    label: 'Broker Gateways',
    description: 'Market universe, OAuth exchanges & live execution sessions',
    icon: KeyRound,
    keywords: [
      'fyers', 'oauth', 'login', 'gateway', 'session', 'access token', 'app id', 'secret',
      'redirect', 'telemetry', 'connection', 'credentials', 'broker', 'live status',
    ],
  },
  {
    id: 'quantitative',
    label: 'Quant Valuation',
    description: 'Options pricing models, Greeks solvers & transaction friction',
    icon: Sliders,
    keywords: [
      'black scholes', 'black76', 'black-76', 'greeks', 'iv', 'implied volatility',
      'brent', 'newton', 'newton-raphson', 'risk free rate', 'time convention',
      'brokerage', 'slippage', 'charges', 'stt', 'gst', 'sebi', 'stamp duty',
      'pricing', 'expiry', 'turnover',
    ],
  },
  {
    id: 'paper',
    label: 'Paper Trading',
    description: 'Virtual capital, risk boundaries & execution guardrails',
    icon: FileText,
    keywords: [
      'capital', 'virtual', 'margin', 'drawdown', 'circuit breaker', 'square off',
      'risk', 'guardrails', 'overnight', 'nrml', 'order confirm', 'reset account',
      'pnl', 'allocation', 'exposure',
    ],
  },
  {
    id: 'telegram',
    label: 'Telegram Alerts',
    description: 'Signal notification routing & personal chat delivery',
    icon: Send,
    keywords: [
      'telegram', 'alerts', 'notifications', 'bot', 'chat', 'link', 'unlink',
      'test alert', 'subscriptions', 'events', 'instruments', 'timeframes',
      'audit', 'queue', 'delivery', 'probe', 'simulator',
    ],
  },
  {
    id: 'monitoring',
    label: 'System Health',
    description: 'Forecast health, circuit breaker controls, cache & telemetry',
    icon: Activity,
    keywords: [
      'monitoring', 'health', 'circuit breaker', 'cache', 'pipeline', 'staleness',
      'diagnostics', 'telemetry', 'forecast health', 'system', 'latency',
    ],
  },
  {
    id: 'ml',
    label: 'ML Operations',
    description: 'Gradient boosted ensembles, calibration curves & challenger tournaments',
    icon: BrainCircuit,
    keywords: [
      'ml', 'machine learning', 'xgboost', 'lightgbm', 'ensemble', 'calibration',
      'champion', 'challenger', 'brier', 'settlement', 'probabilities', 'targets',
    ],
  },
  {
    id: 'system',
    label: 'System Nerve',
    description: 'Operational telemetry, broker session, notifications & diagnostics',
    icon: Activity,
    keywords: [
      'system', 'nerve', 'telemetry', 'broker session', 'token', 'diagnostics',
      'drift', 'cache', 'subsystems', 'operational', 'notifications',
    ],
  },
] as const;

export const SETTINGS_TAB_IDS: readonly SettingsTabId[] = SETTINGS_TABS.map((t) => t.id);

export const DEFAULT_SETTINGS_TAB: SettingsTabId = 'preferences';

export function getTabDef(id: SettingsTabId): SettingsTabDef {
  return SETTINGS_TABS.find((t) => t.id === id) ?? SETTINGS_TABS[0];
}

export function isSaveableTab(id: SettingsTabId): id is SettingsSaveableId {
  return id !== 'telegram' && id !== 'monitoring' && id !== 'ml' && id !== 'system';
}

/** Case-insensitive match across label, description and keywords. */
export function matchTab(tab: SettingsTabDef, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  if (tab.label.toLowerCase().includes(q)) return true;
  if (tab.description.toLowerCase().includes(q)) return true;
  return tab.keywords.some((k) => k.includes(q));
}

export function searchTabs(query: string): SettingsTabDef[] {
  if (!query.trim()) return [...SETTINGS_TABS];
  return SETTINGS_TABS.filter((t) => matchTab(t, query));
}
