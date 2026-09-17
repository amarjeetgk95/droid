'use client';

/** Static catalogs backing the Telegram notification filters and probe simulator. */

export interface TelegramStatus {
  bot_configured: boolean;
  bot_username: string | null;
  webhook_configured: boolean;
  binding: {
    linked: boolean;
    telegram_chat_id: string | null;
    linked_at: number | null;
    status: string;
  };
  environment: string;
  queue_stats?: Record<string, unknown>;
}

export const INSTRUMENTS = ['NIFTY', 'BANKNIFTY', 'SENSEX', 'BTCUSD'] as const;

export const TIMEFRAMES = ['1M', '5M'] as const;

export const EVENT_GROUPS: { group: string; items: { key: string; label: string }[] }[] = [
  {
    group: 'Signals',
    items: [
      { key: 'SIGNAL_TRIGGERED', label: '1M / 5M Breakout Triggered' },
      { key: 'SIGNAL_CONFIRMED', label: '1M / 5M Breakout Confirmed' },
      { key: 'POSSIBLE_SETUP', label: 'Possible Setup (Developing)' },
    ],
  },
  {
    group: 'Pipeline',
    items: [
      { key: 'AI_CONFIRMED', label: 'AI Confirmation' },
      { key: 'RISK_APPROVED', label: 'Risk Approval' },
      { key: 'RISK_REJECTED', label: 'Risk Rejected' },
    ],
  },
  {
    group: 'Execution & Result',
    items: [
      { key: 'EXECUTED', label: 'Execution' },
      { key: 'PARTIALLY_FILLED', label: 'Partial Fill' },
      { key: 'TARGET_HIT', label: 'Target Hit' },
      { key: 'STOP_HIT', label: 'Stop Hit' },
      { key: 'SIGNAL_RESULT', label: 'Signal Result' },
    ],
  },
  {
    group: 'Lifecycle',
    items: [
      { key: 'SIGNAL_EXPIRED', label: 'Expired' },
      { key: 'SIGNAL_INVALIDATED', label: 'Invalidated' },
    ],
  },
];

/** Flat event key list — derived so the simulator can never drift from the filters. */
export const SAMPLE_EVENTS: string[] = EVENT_GROUPS.flatMap((g) => g.items.map((i) => i.key));
