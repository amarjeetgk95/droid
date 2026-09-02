import { LEGACY_DEV_CONFIG_KEY, CURRENT_SCHEMA_VERSION } from './settingsConstants';
import { DEFAULT_SETTINGS } from './settingsDefaults';
import type { AISettings, AppSettings, BrokerProviderId } from './settingsTypes';

/**
 * Merge a partial section onto its defaults, ignoring null/undefined values
 * so legacy or partial stored data can never wipe out a default with null.
 * Empty string for non-secret fields is also ignored to avoid clobbering.
 */
export function mergeSection<T>(defaults: T, incoming: unknown): T {
  const source = (incoming && typeof incoming === 'object' ? incoming : {}) as Record<string, unknown>;
  const clean: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(source)) {
    if (value === null || value === undefined) continue;
    clean[key] = value;
  }
  return { ...(defaults as object), ...clean } as T;
}

/**
 * Deep merge for nested objects — used for Supabase/backend payloads where
 * shallow merge would drop nested broker/ai fields on second save.
 */
export function deepMerge<T>(defaults: T, incoming: unknown): T {
  const source = (incoming && typeof incoming === 'object' ? incoming : {}) as Record<string, unknown>;
  const out: Record<string, unknown> = { ...(defaults as object) };
  for (const [key, value] of Object.entries(source)) {
    if (value === null || value === undefined) continue;
    const prev = out[key];
    if (
      prev &&
      typeof prev === 'object' &&
      !Array.isArray(prev) &&
      value &&
      typeof value === 'object' &&
      !Array.isArray(value)
    ) {
      out[key] = deepMerge(prev as object, value as object);
    } else {
      out[key] = value;
    }
  }
  return out as T;
}

/**
 * Migrate legacy DeveloperApiConfig localStorage key into canonical AppSettings.
 */
export function migrateLegacyDevConfig(settings: AppSettings): AppSettings {
  if (typeof window === 'undefined') return settings;
  try {
    const legacyRaw = localStorage.getItem(LEGACY_DEV_CONFIG_KEY);
    if (!legacyRaw) return settings;

    const legacy = JSON.parse(legacyRaw);
    const merged = { ...settings } as AppSettings;

    if (legacy.geminiApiKey) merged.ai = { ...merged.ai, geminiApiKey: legacy.geminiApiKey };
    if (legacy.geminiModel) merged.ai = { ...merged.ai, geminiModel: legacy.geminiModel };
    if (legacy.openRouterApiKey) merged.ai = { ...merged.ai, openRouterApiKey: legacy.openRouterApiKey };
    if (legacy.openRouterModel) merged.ai = { ...merged.ai, openRouterModel: legacy.openRouterModel };
    if (legacy.ollamaBaseUrl) merged.ai = { ...merged.ai, ollamaBaseUrl: legacy.ollamaBaseUrl };
    if (legacy.ollamaModel) merged.ai = { ...merged.ai, ollamaModel: legacy.ollamaModel };
    if (legacy.aiTemperature !== undefined) merged.ai = { ...merged.ai, temperature: legacy.aiTemperature };
    if (legacy.aiAnalysisStyle) {
      const personaMap: Record<string, AISettings['persona']> = {
        institutional: 'INSTITUTIONAL',
        momentum: 'MOMENTUM',
        options_greek: 'OPTION_SELLER',
        conservative: 'INSTITUTIONAL',
      };
      merged.ai = { ...merged.ai, persona: personaMap[legacy.aiAnalysisStyle] || 'INSTITUTIONAL' };
    }

    if (legacy.fyersAppId) {
      merged.broker = { ...merged.broker, fyers: { ...merged.broker.fyers, appId: legacy.fyersAppId } };
    }
    if (legacy.fyersSecretKey) {
      merged.broker = { ...merged.broker, fyers: { ...merged.broker.fyers, secret: legacy.fyersSecretKey } };
    }
    if (legacy.fyersRedirectUri) {
      merged.broker = { ...merged.broker, fyers: { ...merged.broker.fyers, redirectUri: legacy.fyersRedirectUri } };
    }
    if (legacy.binanceApiKey) {
      merged.broker = { ...merged.broker, binance: { ...merged.broker.binance, apiKey: legacy.binanceApiKey } };
    }
    if (legacy.binanceSecretKey) {
      merged.broker = { ...merged.broker, binance: { ...merged.broker.binance, apiSecret: legacy.binanceSecretKey } };
    }

    try { localStorage.removeItem(LEGACY_DEV_CONFIG_KEY); } catch {}
    return merged;
  } catch {
    return settings;
  }
}

export function migrateMockAI(settings: AppSettings): AppSettings {
  if ((settings.ai as unknown as { provider?: string })?.provider === 'mock_ai' || (settings.ai as unknown as { provider?: string })?.provider === 'mock') {
    // compat: mock_ai -> openrouter (backend now treats mock_ai as openrouter; frontend defaults to openrouter)
    return { ...settings, ai: { ...settings.ai, provider: 'openrouter' as const, connectionMode: 'OpenRouter' as const } };
  }
  return settings;
}

export function migrateMockProvider(settings: AppSettings): AppSettings {
  const legacyProvider = (settings.broker as unknown as { provider?: string })?.provider;
  if (!legacyProvider || legacyProvider === 'mock' || legacyProvider === 'mock_ai' || legacyProvider === 'upstox' || legacyProvider === 'kotak_neo') {
    return {
      ...settings,
      broker: { ...settings.broker, provider: 'fyers' as BrokerProviderId },
    };
  }
  return settings;
}

export function migrateConnectionMode(settings: AppSettings): AppSettings {
  if (!settings.ai.connectionMode) {
    const p = (settings.ai.provider || '').toLowerCase();
    if (p === 'openrouter') (settings.ai as unknown as { connectionMode: string }).connectionMode = 'OpenRouter';
    else if (p === 'ollama') (settings.ai as unknown as { connectionMode: string }).connectionMode = 'Local Ollama';
    else if (['openai', 'novita', 'nvidia', 'custom'].includes(p) || (settings.ai as unknown as { directProvider?: string }).directProvider) (settings.ai as unknown as { connectionMode: string }).connectionMode = 'Direct Provider';
    else (settings.ai as unknown as { connectionMode: string }).connectionMode = 'OpenRouter';
  }
  if (!settings.ai.taskModels) {
    settings.ai.taskModels = { ...DEFAULT_SETTINGS.ai.taskModels };
  } else {
    for (const k of Object.keys(DEFAULT_SETTINGS.ai.taskModels) as Array<keyof typeof DEFAULT_SETTINGS.ai.taskModels>) {
      if (!(k in settings.ai.taskModels)) settings.ai.taskModels[k] = DEFAULT_SETTINGS.ai.taskModels[k];
    }
  }
  if (!settings.ai.routingMode) (settings.ai as unknown as { routingMode: string }).routingMode = DEFAULT_SETTINGS.ai.routingMode;
  if (!settings.ai.directProvider) (settings.ai as unknown as { directProvider: string }).directProvider = DEFAULT_SETTINGS.ai.directProvider;
  return settings;
}

export function migrateSchemaVersion(settings: AppSettings): AppSettings {
  const v = (settings as unknown as { schemaVersion?: number }).schemaVersion ?? 1;
  if (v >= CURRENT_SCHEMA_VERSION) {
    return { ...settings, schemaVersion: CURRENT_SCHEMA_VERSION };
  }
  // v1 → v2: add schemaVersion, ensure broker.flattrade exists, ensure taskModels etc.
  let out = { ...settings, schemaVersion: CURRENT_SCHEMA_VERSION } as AppSettings;
  // Ensure flattrade branch exists (some v1 exports lacked it)
  if (!out.broker.flattrade) {
    out = { ...out, broker: { ...out.broker, flattrade: DEFAULT_SETTINGS.broker.flattrade } };
  }
  if (!out.broker.binance) {
    out = { ...out, broker: { ...out.broker, binance: DEFAULT_SETTINGS.broker.binance } };
  }
  out = migrateConnectionMode(out);
  return out;
}

export function applyAllMigrations(settings: AppSettings): AppSettings {
  let s = migrateLegacyDevConfig(settings);
  s = migrateMockProvider(s);
  s = migrateMockAI(s);
  s = migrateConnectionMode(s);
  s = migrateSchemaVersion(s);
  return s;
}
