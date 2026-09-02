import { STORAGE_KEY, STORAGE_KEY_V2, LEGACY_DEV_CONFIG_KEY, SECRET_FIELDS } from './settingsConstants';
import { DEFAULT_SETTINGS } from './settingsDefaults';
import { applyAllMigrations, mergeSection } from './settingsMigrations';
import type { AppSettings } from './settingsTypes';

function readRaw(key: string): string | null {
  if (typeof window === 'undefined') return null;
  try { return localStorage.getItem(key); } catch { return null; }
}

function writeRaw(key: string, value: string): void {
  if (typeof window === 'undefined') return;
  try { localStorage.setItem(key, value); } catch (e) { console.error('Failed to save settings:', e); }
}

export function getStoredSettings(): AppSettings {
  if (typeof window === 'undefined') return DEFAULT_SETTINGS;
  try {
    // Prefer v2, fallback to v1 with migration
    let raw = readRaw(STORAGE_KEY_V2);
    let isV1 = false;
    if (!raw) {
      raw = readRaw(STORAGE_KEY);
      isV1 = !!raw;
    }
    let settings: AppSettings;
    if (!raw) {
      settings = { ...DEFAULT_SETTINGS };
    } else {
      const parsed = JSON.parse(raw);
      settings = {
        schemaVersion: parsed.schemaVersion,
        broker: mergeSection(DEFAULT_SETTINGS.broker, parsed.broker),
        quantitative: mergeSection(DEFAULT_SETTINGS.quantitative, parsed.quantitative),
        ai: mergeSection(DEFAULT_SETTINGS.ai, parsed.ai),
        paper: mergeSection(DEFAULT_SETTINGS.paper, parsed.paper),
        preferences: mergeSection(DEFAULT_SETTINGS.preferences, parsed.preferences),
      } as AppSettings;
    }
    settings = applyAllMigrations(settings);
    // If we migrated from v1, eagerly write v2
    if (isV1) {
      try { writeRaw(STORAGE_KEY_V2, JSON.stringify(settings)); } catch {}
    }
    return settings;
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export function saveStoredSettings(settings: AppSettings): void {
  if (typeof window === 'undefined') return;
  try {
    const toSave = { ...settings, schemaVersion: 2 };
    writeRaw(STORAGE_KEY_V2, JSON.stringify(toSave));
    // Keep v1 mirror for one release cycle for downgrade safety, then drop
    writeRaw(STORAGE_KEY, JSON.stringify(toSave));
  } catch (err) {
    console.error('Failed to save settings to localStorage:', err);
  }
}

export function resetStoredSettings(): AppSettings {
  if (typeof window !== 'undefined') {
    try {
      localStorage.removeItem(STORAGE_KEY);
      localStorage.removeItem(STORAGE_KEY_V2);
      localStorage.removeItem(LEGACY_DEV_CONFIG_KEY);
    } catch {}
  }
  return DEFAULT_SETTINGS;
}

export function exportSettingsJson(
  settings: AppSettings,
  options?: { includeSecrets?: boolean }
): string {
  if (options?.includeSecrets) {
    return JSON.stringify(settings, null, 2);
  }
  const sanitized = JSON.parse(JSON.stringify(settings)) as AppSettings;
  const stripPath = (root: unknown, path: string) => {
    const parts = path.split('.');
    let cursor: unknown = root;
    for (let i = 0; i < parts.length - 1; i++) {
      if (!cursor || typeof cursor !== 'object') return;
      cursor = (cursor as Record<string, unknown>)[parts[i]];
    }
    if (cursor && typeof cursor === 'object') {
      (cursor as Record<string, unknown>)[parts[parts.length - 1]] = '';
    }
  };
  for (const field of SECRET_FIELDS.broker) stripPath(sanitized.broker, field);
  for (const field of SECRET_FIELDS.ai) stripPath((sanitized as unknown as Record<string, unknown>).ai, field);
  return JSON.stringify(sanitized, null, 2);
}

export function importSettingsJson(jsonStr: string): AppSettings {
  const parsed = JSON.parse(jsonStr);
  const merged: AppSettings = {
    schemaVersion: parsed.schemaVersion ?? 2,
    broker: mergeSection(DEFAULT_SETTINGS.broker, parsed.broker),
    quantitative: mergeSection(DEFAULT_SETTINGS.quantitative, parsed.quantitative),
    ai: mergeSection(DEFAULT_SETTINGS.ai, parsed.ai),
    paper: mergeSection(DEFAULT_SETTINGS.paper, parsed.paper),
    preferences: mergeSection(DEFAULT_SETTINGS.preferences, parsed.preferences),
  } as AppSettings;
  return applyAllMigrations(merged);
}
