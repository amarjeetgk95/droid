import { DEFAULT_SETTINGS } from './settingsDefaults';
import { applyAllMigrations, deepMerge, mergeSection } from './settingsMigrations';
import { getStoredSettings } from './settingsStorage';
import type { AppSettings } from './settingsTypes';

/**
 * Merge a raw Supabase app_settings blob (Record) into a validated AppSettings.
 * Uses deepMerge so nested broker/ai partials don't drop sibling keys.
 * Never throws.
 */
export function mergeAppSettingsFromSupabase(raw: unknown): AppSettings {
  if (!raw || typeof raw !== 'object') return getStoredSettings();
  const parsed = raw as Partial<AppSettings>;
  const merged: AppSettings = {
    schemaVersion: (parsed as unknown as { schemaVersion?: number }).schemaVersion ?? 2,
    broker: deepMerge(DEFAULT_SETTINGS.broker, parsed.broker),
    quantitative: mergeSection(DEFAULT_SETTINGS.quantitative, parsed.quantitative),
    ai: deepMerge(DEFAULT_SETTINGS.ai, parsed.ai),
    paper: mergeSection(DEFAULT_SETTINGS.paper, parsed.paper),
    preferences: mergeSection(DEFAULT_SETTINGS.preferences, parsed.preferences),
  } as AppSettings;
  return applyAllMigrations(merged);
}

/**
 * Build the Supabase payload from AppSettings.
 * Keeps flat legacy columns in sync so old queries remain valid.
 */
export function toSupabasePayload(settings: AppSettings): Record<string, unknown> {
  return {
    theme: settings.preferences.theme,
    default_symbol: settings.preferences.defaultIndexSymbol,
    preferred_market_provider: settings.broker.provider,
    preferred_ai_provider: settings.ai.provider,
    preferred_ai_model: settings.ai.geminiModel,
    app_settings: { ...settings, schemaVersion: 2 },
  };
}
