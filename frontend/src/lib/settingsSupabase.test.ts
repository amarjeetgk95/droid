import { describe, expect, it } from 'vitest';
import { DEFAULT_SETTINGS } from './settingsDefaults';
import { mergeAppSettingsFromSupabase, toSupabasePayload } from './settingsSupabase';
import type { AppSettings } from './settingsTypes';

function withAiKey(key: string): AppSettings {
  return {
    ...DEFAULT_SETTINGS,
    ai: { ...DEFAULT_SETTINGS.ai, openRouterApiKey: key },
  };
}

describe('supabase settings payload (cross-device key sync)', () => {
  it('omits empty-string secrets so they never wipe the stored key', () => {
    const payload = toSupabasePayload(withAiKey(''));
    const app = payload.app_settings as Record<string, unknown>;
    const ai = app.ai as Record<string, unknown>;
    expect('openRouterApiKey' in ai).toBe(false);
    // non-secret AI prefs still sync
    expect(ai.provider).toBe('openrouter');
  });

  it('keeps non-empty secrets so entering/rotating a key persists', () => {
    const payload = toSupabasePayload(withAiKey('sk-or-live'));
    const app = payload.app_settings as Record<string, unknown>;
    expect((app.ai as Record<string, unknown>).openRouterApiKey).toBe('sk-or-live');
  });

  it('restores a stored key when hydrating on another device', () => {
    const merged = mergeAppSettingsFromSupabase({
      ai: { openRouterApiKey: 'sk-or-live', provider: 'openrouter' },
    });
    expect(merged.ai.openRouterApiKey).toBe('sk-or-live');
  });
});
