import type { ApiCore } from './client';

export interface TelegramLinkStatus {
  linked: boolean;
  telegram_chat_id: string | null;
  linked_at: number | null;
  status: string;
}

export interface TelegramWebhookSetup {
  webhook_url: string;
  result: Record<string, unknown>;
}

export function createTelegramApi(core: ApiCore) {
  return {
    getTelegramLinkStatus: () =>
      core.request<TelegramLinkStatus>('/api/v1/telegram/link/status'),

    setupTelegramWebhook: () =>
      core.request<TelegramWebhookSetup>('/api/v1/telegram/webhook/setup', {
        method: 'POST',
      }),
  };
}

export type TelegramApi = ReturnType<typeof createTelegramApi>;
