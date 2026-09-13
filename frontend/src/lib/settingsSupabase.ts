import { DEFAULT_SETTINGS } from './settingsDefaults';
import { SECRET_FIELDS } from './settingsConstants';
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

function resolvePreferredModel(ai: AppSettings['ai']): string {
  switch (ai.provider) {
    case 'openrouter':
      return ai.openRouterSelectedModel || ai.openRouterModel || '';
    case 'openai':
      return ai.openaiModel || '';
    case 'novita':
      return ai.novitaModel || '';
    case 'nvidia':
      return ai.nvidiaModel || '';
    case 'ollama':
      return ai.ollamaModel || '';
    case 'custom':
      return ai.customOpenaiModel || '';
    case 'gemini':
    default:
      return ai.geminiModel || '';
  }
}

/**
 * Remove empty-string secrets from a settings section copy before upload.
 * An empty key field means "not set on this device" — sending it would
 * deep-merge "" over the secret stored in Supabase and wipe it for every
 * other device (e.g. saving any setting from the phone before its first
 * sync would erase the key saved from the PC). Non-empty secrets are sent
 * normally, so entering/rotating a key still persists everywhere.
 */
function stripEmptySecrets(section: Record<string, unknown>, fields: string[]): void {
  for (const path of fields) {
    const parts = path.split('.');
    let cursor: unknown = section;
    for (let i = 0; i < parts.length - 1; i++) {
      if (!cursor || typeof cursor !== 'object') { cursor = null; break; }
      cursor = (cursor as Record<string, unknown>)[parts[i]];
    }
    if (cursor && typeof cursor === 'object') {
      const leaf = parts[parts.length - 1];
      if ((cursor as Record<string, unknown>)[leaf] === '') {
        delete (cursor as Record<string, unknown>)[leaf];
      }
    }
  }
}

/**
 * Build the Supabase payload from AppSettings.
 * Keeps flat legacy columns in sync so old queries remain valid.
 */
export function toSupabasePayload(settings: AppSettings): Record<string, unknown> {
  const appSettings = JSON.parse(JSON.stringify({ ...settings, schemaVersion: 2 })) as Record<string, unknown>;
  if (appSettings.ai && typeof appSettings.ai === 'object') {
    stripEmptySecrets(appSettings.ai as Record<string, unknown>, SECRET_FIELDS.ai);
  }
  if (appSettings.broker && typeof appSettings.broker === 'object') {
    stripEmptySecrets(appSettings.broker as Record<string, unknown>, SECRET_FIELDS.broker);
  }
  return {
    theme: settings.preferences.theme,
    default_symbol: settings.preferences.defaultIndexSymbol,
    preferred_market_provider: settings.broker.provider,
    preferred_ai_provider: settings.ai.provider,
    preferred_ai_model: resolvePreferredModel(settings.ai),
    app_settings: appSettings,
  };
}
