import type { ApiCore } from './client';

export function createAccountApi(core: ApiCore) {
  return {
    async bulkTelegramPreferences(enable: boolean) {
    return core.request<import('../types').TelegramPreferences>('/api/v1/telegram/preferences/bulk', {
      method: 'POST',
      body: JSON.stringify({ enable }),
    });
  },

    async createSettings(settings: import('../types').UserSettingsUpdate) {
    return core.request<import('../types').UserSettingsResponse>('/api/v1/settings', {
      method: 'POST',
      body: JSON.stringify(settings),
    });
  },

    async devPublishTelegramEvent(event: Record<string, unknown>) {
    return core.request<{ status: string; notification_ids: string[] }>('/api/v1/telegram/dev/publish-event', {
      method: 'POST',
      body: JSON.stringify(event),
    });
  },

    async generateTelegramLink() {
    return core.request<{ url: string; ttl_seconds: number; bot_username: string }>(
      '/api/v1/telegram/link/generate',
      { method: 'POST' },
    );
  },

    async getFullProfile() {
    return core.request<import('../types').ProfileResponse>('/api/v1/auth/profile/full');
  },

    async getProfile() {
    return core.request<{ user_id: string; email: string | null; role: string }>('/api/v1/auth/profile');
  },

    async getSettings() {
    return core.request<import('../types').UserSettingsResponse>('/api/v1/settings');
  },

    async getTelegramAudit(limit = 50) {
    return core.request<{ records: Record<string, unknown>[] }>(
      `/api/v1/telegram/audit?limit=${limit}`,
    );
  },

    async getTelegramPreferences() {
    return core.request<import('../types').TelegramPreferences>('/api/v1/telegram/preferences');
  },

    async getTelegramStats() {
    return core.request<{ notification_queue: Record<string, unknown>; outbound_queue_size: number; link_count: number }>(
      '/api/v1/telegram/stats',
    );
  },

    async getTelegramStatus() {
    return core.request<{
      bot_configured: boolean;
      bot_username: string | null;
      webhook_configured: boolean;
      binding: { linked: boolean; telegram_chat_id: string | null; linked_at: number | null; status: string };
      environment: string;
      queue_stats: Record<string, unknown>;
    }>('/api/v1/telegram/status');
  },

    async previewTelegramEvent(event: Record<string, unknown>) {
    return core.request<{ event_type: string; instrument: string; preview: string }>('/api/v1/telegram/dev/preview', {
      method: 'POST',
      body: JSON.stringify(event),
    });
  },

    async quickTestTelegram(params: { instrument: string; event_type: string; candle_timeframe: string; direction: string; setup_type?: string }) {
    const qs = new URLSearchParams({
      instrument: params.instrument,
      event_type: params.event_type,
      candle_timeframe: params.candle_timeframe,
      direction: params.direction,
      setup_type: params.setup_type || (params.direction === 'BEARISH' ? 'BREAKDOWN' : 'BREAKOUT'),
    }).toString();
    return core.request<{ status: string; notification_ids: string[]; signal_id: string; preview: string; event: Record<string, unknown> }>(
      `/api/v1/telegram/dev/quick-test?${qs}`,
      { method: 'POST' },
    );
  },

    async resetTelegramPreferences() {
    return core.request<import('../types').TelegramPreferences>('/api/v1/telegram/preferences/reset', { method: 'POST' });
  },

    async revokeTelegramLink() {
    return core.request<{ status: string }>('/api/v1/telegram/link/revoke', { method: 'POST' });
  },

    async sendTelegramTestMessage() {
    return core.request<{ status: string; notification_id: string }>('/api/v1/telegram/test', {
      method: 'POST',
    });
  },

    async updateProfile(display_name: string | null) {
    return core.request<import('../types').ProfileResponse>('/api/v1/auth/profile', {
      method: 'PATCH',
      body: JSON.stringify({ display_name }),
    });
  },

    async updateSettings(settings: Partial<import('../types').UserSettingsUpdate>) {
    return core.request<import('../types').UserSettingsResponse>('/api/v1/settings', {
      method: 'PATCH',
      body: JSON.stringify(settings),
    });
  },

    async updateTelegramPreferences(prefs: import('../types').TelegramPreferences) {
    return core.request<import('../types').TelegramPreferences>('/api/v1/telegram/preferences', {
      method: 'PUT',
      body: JSON.stringify(prefs),
    });
  },
  };
}

export type AccountApi = ReturnType<typeof createAccountApi>;
