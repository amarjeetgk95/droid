export type ApiType = 'indian' | 'crypto';
export type IndianProviderId = 'fyers' | 'upstox' | 'kotak_neo';
export type CryptoProviderId = 'binance';
export type BrokerProviderId = IndianProviderId | CryptoProviderId;

export interface FyersCredentials {
  appId: string;
  secret: string;
  redirectUri: string;
}

export interface UpstoxCredentials {
  apiKey: string;
  secret: string;
  redirectUri: string;
}

export interface KotakNeoCredentials {
  apiKey: string;      // UCC (Unique Client Code, 5 chars)
  apiSecret: string;   // Access Token from Neo API Dashboard
  mobileNumber: string;
  mpin: string;
  totp: string;        // Runtime TOTP from authenticator app (rotates every 30s)
}

export interface BinanceCredentials {
  apiKey: string;
  apiSecret: string;
}

export interface BrokerSettings {
  apiType: ApiType;
  provider: BrokerProviderId;
  fyers: FyersCredentials;
  upstox: UpstoxCredentials;
  kotakNeo: KotakNeoCredentials;
  binance: BinanceCredentials;
}

export interface QuantitativeSettings {
  riskFreeRate: number; // e.g. 0.0675 (6.75%)
  timeConvention: 'ACT365' | 'ACT360' | 'TradingDays252';
  defaultPricingModel: 'FUTURES_BLACK76' | 'SPOT_BLACK_SCHOLES';
  ivMethod: 'BRENT' | 'NEWTON_RAPHSON';
  brokeragePerOrder: number; // 20
  slippagePct: number; // 0.05%
}

export type AIConnectionMode = 'OpenRouter' | 'Direct Provider' | 'Local Ollama';
export type DirectProviderId = 'OpenAI' | 'Novita AI' | 'NVIDIA' | 'Google Gemini' | 'Custom OpenAI-Compatible';
export type AIRoutingMode = 'Manual' | 'Task Optimized' | 'Best Available' | 'Cost Optimized';
export type AITaskId = 'INTRADAY_ANALYSIS' | 'NEWS_ANALYSIS' | 'DEEP_RESEARCH' | 'MTF_SYNTHESIS' | 'CHART_EXPLANATION' | 'FINAL_REVIEW';

export interface AISettings {
  // Legacy provider (kept for backward compat) — maps to connectionMode
  provider: 'gemini' | 'openrouter' | 'ollama' | 'mock_ai' | 'openai' | 'novita' | 'nvidia' | 'custom';
  // §8 Three Connection Modes (primary)
  connectionMode: AIConnectionMode;
  directProvider: DirectProviderId;
  routingMode: AIRoutingMode;
  // Provider keys
  geminiApiKey: string;
  geminiModel: string;
  openRouterApiKey: string;
  openRouterModel: string;
  ollamaBaseUrl: string;
  ollamaModel: string;
  // Direct provider keys (§11, §34)
  openaiApiKey: string;
  openaiModel: string;
  novitaApiKey: string;
  novitaModel: string;
  nvidiaApiKey: string;
  nvidiaModel: string;
  customOpenaiApiKey: string;
  customOpenaiBaseUrl: string;
  customOpenaiModel: string;
  // Task-specific model routing (§14)
  taskModels: Record<AITaskId, string>;
  // Direct-provider base URLs where applicable
  openaiBaseUrl: string;
  novitaBaseUrl: string;
  nvidiaBaseUrl: string;
  geminiBaseUrl: string;

  persona: 'INSTITUTIONAL' | 'MOMENTUM' | 'OPTION_SELLER';
  temperature: number;
  cacheTtlSeconds: number;
  // Dynamic OpenRouter Free-Model System
  openRouterFreeOnly: boolean;
  openRouterPricingFilter: 'FREE' | 'PAID' | 'ALL';
  openRouterSelectedModel: string; // 'auto' or model id
  openRouterAllowPaid: boolean;
  // Fallback (§16)
  fallbackEnabled: boolean;
  fallbackOllamaModel: string;
}

export interface PaperTradingSettings {
  initialCapital: number;
  autoSquareOffTime: string;
  maxCapitalPerTradePct: number;
  maxDailyDrawdownHaltPct: number;
  requireOrderConfirm: boolean;
  allowOvernightPositions: boolean;
}

export interface PreferencesSettings {
  theme: 'dark' | 'light' | 'system';
  numberFormat: 'INDIAN' | 'INTERNATIONAL';
  defaultIndexSymbol: string;
}

export interface AppSettings {
  broker: BrokerSettings;
  quantitative: QuantitativeSettings;
  ai: AISettings;
  paper: PaperTradingSettings;
  preferences: PreferencesSettings;
}

export interface SupportedModelOption {
  id: string;
  name: string;
  provider: 'gemini' | 'openrouter' | 'ollama';
  tag: string;
  description: string;
}

export const SUPPORTED_GEMINI_MODELS: SupportedModelOption[] = [
  { id: 'gemini-2.5-flash', name: 'Gemini 2.5 Flash', provider: 'gemini', tag: 'Fast & High IQ (Recommended)', description: 'Low latency, advanced reasoning, multimodal and structured JSON' },
  { id: 'gemini-2.5-pro', name: 'Gemini 2.5 Pro', provider: 'gemini', tag: 'Deep Reasoning', description: 'Deep quantitative analysis, market thesis generation' },
  { id: 'gemini-2.0-flash', name: 'Gemini 2.0 Flash', provider: 'gemini', tag: 'Realtime JSON', description: 'Ultra-fast structured outputs and live market feed analysis' },
  { id: 'gemini-2.0-flash-lite', name: 'Gemini 2.0 Flash-Lite', provider: 'gemini', tag: 'Cost Effective', description: 'High throughput, cost-optimized streaming analysis' },
  { id: 'gemini-1.5-pro', name: 'Gemini 1.5 Pro', provider: 'gemini', tag: '2M Context', description: 'Massive context window for full-day tick summaries' },
  { id: 'gemini-1.5-flash', name: 'Gemini 1.5 Flash', provider: 'gemini', tag: 'Balanced', description: 'Lightweight and fast standard model' },
];

export const SUPPORTED_OPENROUTER_MODELS: SupportedModelOption[] = [
  { id: 'anthropic/claude-3.7-sonnet', name: 'Claude 3.7 Sonnet', provider: 'openrouter', tag: 'Top Tier Reasoning', description: 'Hybrid reasoning and leading quantitative synthesis' },
  { id: 'anthropic/claude-3.5-sonnet', name: 'Claude 3.5 Sonnet', provider: 'openrouter', tag: 'Industry Benchmark', description: 'State-of-the-art coding and financial analysis' },
  { id: 'deepseek/deepseek-r1', name: 'DeepSeek R1', provider: 'openrouter', tag: 'Chain-of-Thought', description: 'Open weights reasoning model with deep mathematical thinking' },
  { id: 'deepseek/deepseek-chat', name: 'DeepSeek V3', provider: 'openrouter', tag: 'High Speed & Value', description: 'Ultra-fast and economical for high-frequency scan queries' },
  { id: 'openai/gpt-4o', name: 'OpenAI GPT-4o', provider: 'openrouter', tag: 'Flagship Omni', description: 'Strong multi-modal and fast structured data extraction' },
  { id: 'openai/gpt-4o-mini', name: 'OpenAI GPT-4o Mini', provider: 'openrouter', tag: 'Lightweight Fast', description: 'Extremely fast and budget-friendly' },
  { id: 'google/gemini-2.5-pro-preview', name: 'Gemini 2.5 Pro (OpenRouter)', provider: 'openrouter', tag: 'Preview', description: 'Google flagship reasoning via OpenRouter API' },
  { id: 'meta-llama/llama-3.3-70b-instruct', name: 'Llama 3.3 70B Instruct', provider: 'openrouter', tag: 'Open Weight', description: 'Meta high-capacity open model' },
  { id: 'qwen/qwen-2.5-72b-instruct', name: 'Qwen 2.5 72B Instruct', provider: 'openrouter', tag: 'Math & Quantitative', description: 'Superb numerical math and complex derivatives logic' },
];

export const SUPPORTED_OLLAMA_MODELS: SupportedModelOption[] = [
  { id: 'deepseek-r1:8b', name: 'DeepSeek-R1 8B', provider: 'ollama', tag: 'Local CoT', description: 'High efficiency local reasoning model' },
  { id: 'deepseek-r1:14b', name: 'DeepSeek-R1 14B', provider: 'ollama', tag: 'High Precision', description: 'Balanced memory footprint and analytical depth' },
  { id: 'llama3.3:70b', name: 'Llama 3.3 70B', provider: 'ollama', tag: 'Full Local Power', description: 'Requires 40GB+ VRAM or quantized setup' },
  { id: 'llama3.1:8b', name: 'Llama 3.1 8B', provider: 'ollama', tag: 'Light & Fast', description: 'Runs on standard consumer GPUs (8GB VRAM)' },
  { id: 'qwen2.5:7b', name: 'Qwen 2.5 7B', provider: 'ollama', tag: 'Fast Math', description: 'Specialized in numbers, tables, and quantitative parsing' },
  { id: 'qwen2.5:14b', name: 'Qwen 2.5 14B', provider: 'ollama', tag: 'Math Balanced', description: 'Robust local quantitative reasoning' },
  { id: 'mistral:7b', name: 'Mistral 7B', provider: 'ollama', tag: 'Compact Fast', description: 'Fast local instruct model' },
];

export const DEFAULT_SETTINGS: AppSettings = {
  broker: {
    apiType: 'indian',
    provider: 'fyers',
    fyers: {
      appId: '',
      secret: '',
      redirectUri: 'https://droid-backend-emeq.onrender.com/api/v1/tokens/fyers/callback',
    },
    upstox: {
      apiKey: '',
      secret: '',
      redirectUri: 'https://droid-backend-emeq.onrender.com/api/v1/tokens/upstox/callback',
    },
    kotakNeo: {
      apiKey: '',
      apiSecret: '',
      mobileNumber: '',
      mpin: '',
      totp: '',
    },
    binance: {
      apiKey: '',
      apiSecret: '',
    },
  },
  quantitative: {
    riskFreeRate: 0.0675,
    timeConvention: 'ACT365',
    defaultPricingModel: 'FUTURES_BLACK76',
    ivMethod: 'BRENT',
    brokeragePerOrder: 20,
    slippagePct: 0.05,
  },
  ai: {
    provider: 'gemini',
    connectionMode: 'OpenRouter',
    directProvider: 'OpenAI',
    routingMode: 'Task Optimized',
    geminiApiKey: '',
    geminiModel: 'gemini-2.5-flash',
    openRouterApiKey: '',
    openRouterModel: 'anthropic/claude-3.7-sonnet',
    ollamaBaseUrl: 'http://localhost:11434',
    ollamaModel: 'deepseek-r1:8b',
    openaiApiKey: '',
    openaiModel: 'gpt-4o-mini',
    novitaApiKey: '',
    novitaModel: 'meta-llama/llama-3.3-70b-instruct',
    nvidiaApiKey: '',
    nvidiaModel: 'meta/llama-3.1-70b-instruct',
    customOpenaiApiKey: '',
    customOpenaiBaseUrl: '',
    customOpenaiModel: 'custom-model',
    taskModels: {
      INTRADAY_ANALYSIS: 'auto',
      NEWS_ANALYSIS: 'auto',
      DEEP_RESEARCH: 'auto',
      MTF_SYNTHESIS: 'auto',
      CHART_EXPLANATION: 'auto',
      FINAL_REVIEW: 'auto',
    },
    openaiBaseUrl: 'https://api.openai.com/v1',
    novitaBaseUrl: 'https://api.novita.ai/v3/openai',
    nvidiaBaseUrl: 'https://integrate.api.nvidia.com/v1',
    geminiBaseUrl: 'https://generativelanguage.googleapis.com/v1beta',
    persona: 'INSTITUTIONAL',
    temperature: 0.2,
    cacheTtlSeconds: 60,
    openRouterFreeOnly: true,
    openRouterPricingFilter: 'FREE',
    openRouterSelectedModel: 'auto',
    openRouterAllowPaid: false,
    fallbackEnabled: false,
    fallbackOllamaModel: 'deepseek-r1:8b',
  },
  paper: {
    initialCapital: 1000000,
    autoSquareOffTime: '15:20',
    maxCapitalPerTradePct: 20,
    maxDailyDrawdownHaltPct: 10,
    requireOrderConfirm: true,
    allowOvernightPositions: true,
  },
  preferences: {
    theme: 'dark',
    numberFormat: 'INDIAN',
    defaultIndexSymbol: 'NIFTY 50',
  },
};

const STORAGE_KEY = 'droid_app_settings_v1';
const LEGACY_DEV_CONFIG_KEY = 'droid_developer_api_config';

const SECRET_FIELDS: Record<string, string[]> = {
  broker: [
    'fyers.secret',
    'upstox.secret',
    'kotakNeo.apiSecret',
    'kotakNeo.mpin',
    'kotakNeo.totp',
    'binance.apiSecret',
  ],
  ai: ['geminiApiKey', 'openRouterApiKey', 'openaiApiKey', 'novitaApiKey', 'nvidiaApiKey', 'customOpenaiApiKey'],
};

/**
 * Migrate legacy DeveloperApiConfig localStorage key into the canonical AppSettings.
 * This handles the architectural debt of the dual settings system.
 */
function migrateLegacyDevConfig(settings: AppSettings): AppSettings {
  if (typeof window === 'undefined') return settings;
  try {
    const legacyRaw = localStorage.getItem(LEGACY_DEV_CONFIG_KEY);
    if (!legacyRaw) return settings;

    const legacy = JSON.parse(legacyRaw);
    const merged = { ...settings };

    // Merge AI keys — legacy takes precedence if non-empty (user entered them there)
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

    // Merge Broker keys (legacy flat fields → nested provider objects)
    if (legacy.fyersAppId) {
      merged.broker = { ...merged.broker, fyers: { ...merged.broker.fyers, appId: legacy.fyersAppId } };
    }
    if (legacy.fyersSecretKey) {
      merged.broker = { ...merged.broker, fyers: { ...merged.broker.fyers, secret: legacy.fyersSecretKey } };
    }
    if (legacy.fyersRedirectUri) {
      merged.broker = { ...merged.broker, fyers: { ...merged.broker.fyers, redirectUri: legacy.fyersRedirectUri } };
    }
    if (legacy.upstoxApiKey) {
      merged.broker = { ...merged.broker, upstox: { ...merged.broker.upstox, apiKey: legacy.upstoxApiKey } };
    }
    if (legacy.upstoxSecretKey) {
      merged.broker = { ...merged.broker, upstox: { ...merged.broker.upstox, secret: legacy.upstoxSecretKey } };
    }
    if (legacy.upstoxRedirectUri) {
      merged.broker = { ...merged.broker, upstox: { ...merged.broker.upstox, redirectUri: legacy.upstoxRedirectUri } };
    }
    if (legacy.binanceApiKey) {
      merged.broker = { ...merged.broker, binance: { ...merged.broker.binance, apiKey: legacy.binanceApiKey } };
    }
    if (legacy.binanceSecretKey) {
      merged.broker = { ...merged.broker, binance: { ...merged.broker.binance, apiSecret: legacy.binanceSecretKey } };
    }

    // Remove legacy key after successful migration
    localStorage.removeItem(LEGACY_DEV_CONFIG_KEY);
    return merged;
  } catch {
    return settings;
  }
}

/**
 * Merge a partial section onto its defaults, ignoring null/undefined values
 * so legacy or partial stored data can never wipe out a default with null.
 */
function mergeSection<T>(defaults: T, incoming: unknown): T {
  const source = (incoming && typeof incoming === 'object' ? incoming : {}) as Record<string, unknown>;
  const clean: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(source)) {
    if (value === null || value === undefined) continue;
    clean[key] = value;
  }
  return { ...(defaults as object), ...clean } as T;
}

function migrateMockAI(settings: AppSettings): AppSettings {
  if ((settings.ai as any).provider === 'mock_ai' || (settings.ai as any).provider === 'mock') {
    return { ...settings, ai: { ...settings.ai, provider: 'gemini' as const } };
  }
  return settings;
}

function migrateMockProvider(settings: AppSettings): AppSettings {
  // Legacy "mock" provider is no longer supported. Default any historical
  // mock selection to a sensible Indian broker default.
  const legacyProvider = (settings.broker as unknown as { provider?: string }).provider;
  if (legacyProvider === 'mock' || legacyProvider === 'mock_ai') {
    return {
      ...settings,
      broker: { ...settings.broker, provider: 'fyers' as BrokerProviderId },
    };
  }
  return settings;
}

function migrateConnectionMode(settings: AppSettings): AppSettings {
  // Derive connectionMode from legacy provider if missing
  if (!settings.ai.connectionMode) {
    const p = (settings.ai.provider || '').toLowerCase();
    if (p === 'openrouter') settings.ai.connectionMode = 'OpenRouter';
    else if (p === 'ollama') settings.ai.connectionMode = 'Local Ollama';
    else if (['openai', 'novita', 'nvidia', 'custom'].includes(p) || (settings.ai as any).directProvider) settings.ai.connectionMode = 'Direct Provider';
    else settings.ai.connectionMode = 'OpenRouter';
  }
  // Ensure taskModels exists
  if (!settings.ai.taskModels) {
    settings.ai.taskModels = { ...DEFAULT_SETTINGS.ai.taskModels };
  } else {
    // Merge missing tasks
    for (const k of Object.keys(DEFAULT_SETTINGS.ai.taskModels) as Array<keyof typeof DEFAULT_SETTINGS.ai.taskModels>) {
      if (!(k in settings.ai.taskModels)) settings.ai.taskModels[k] = DEFAULT_SETTINGS.ai.taskModels[k];
    }
  }
  // Ensure routingMode
  if (!settings.ai.routingMode) settings.ai.routingMode = DEFAULT_SETTINGS.ai.routingMode;
  if (!settings.ai.directProvider) settings.ai.directProvider = DEFAULT_SETTINGS.ai.directProvider;
  return settings;
}

export function getStoredSettings(): AppSettings {
  if (typeof window === 'undefined') return DEFAULT_SETTINGS;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    let settings: AppSettings;

    if (!raw) {
      settings = DEFAULT_SETTINGS;
    } else {
      const parsed = JSON.parse(raw);
      settings = {
        broker: mergeSection(DEFAULT_SETTINGS.broker, parsed.broker),
        quantitative: mergeSection(DEFAULT_SETTINGS.quantitative, parsed.quantitative),
        ai: mergeSection(DEFAULT_SETTINGS.ai, parsed.ai),
        paper: mergeSection(DEFAULT_SETTINGS.paper, parsed.paper),
        preferences: mergeSection(DEFAULT_SETTINGS.preferences, parsed.preferences),
      };
    }

    // Migrate any legacy DeveloperApiConfig into canonical settings
    settings = migrateLegacyDevConfig(settings);
    // Normalize legacy "mock" provider selection to fyers
    settings = migrateMockProvider(settings);
    // Remove mock_ai provision entirely – migrate to gemini
    settings = migrateMockAI(settings);
    settings = migrateConnectionMode(settings);

    return settings;
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export function saveStoredSettings(settings: AppSettings): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch (err) {
    console.error('Failed to save settings to localStorage:', err);
  }
}

export function resetStoredSettings(): AppSettings {
  if (typeof window !== 'undefined') {
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(LEGACY_DEV_CONFIG_KEY);
  }
  return DEFAULT_SETTINGS;
}

/**
 * Export settings as JSON.
 * By default, strips API keys/secrets for safety.
 * Pass `includeSecrets: true` to include them.
 */
export function exportSettingsJson(
  settings: AppSettings,
  options?: { includeSecrets?: boolean }
): string {
  if (options?.includeSecrets) {
    return JSON.stringify(settings, null, 2);
  }

  const sanitized = JSON.parse(JSON.stringify(settings)) as AppSettings;

  const stripPath = (root: any, path: string) => {
    const parts = path.split('.');
    let cursor = root;
    for (let i = 0; i < parts.length - 1; i++) {
      if (!cursor || typeof cursor !== 'object') return;
      cursor = cursor[parts[i]];
    }
    if (cursor && typeof cursor === 'object') {
      cursor[parts[parts.length - 1]] = '';
    }
  };

  for (const field of SECRET_FIELDS.broker) stripPath(sanitized.broker, field);
  for (const field of SECRET_FIELDS.ai) stripPath(sanitized.ai, field);

  return JSON.stringify(sanitized, null, 2);
}

/**
 * Import settings from JSON string with validation.
 * Merges with defaults so missing fields don't break the app.
 * Throws if the JSON is completely unparseable.
 */
export function importSettingsJson(jsonStr: string): AppSettings {
  const parsed = JSON.parse(jsonStr);

  // Gracefully merge with defaults — even if imported JSON is partial
  const merged: AppSettings = {
    broker: mergeSection(DEFAULT_SETTINGS.broker, parsed.broker),
    quantitative: mergeSection(DEFAULT_SETTINGS.quantitative, parsed.quantitative),
    ai: mergeSection(DEFAULT_SETTINGS.ai, parsed.ai),
    paper: mergeSection(DEFAULT_SETTINGS.paper, parsed.paper),
    preferences: mergeSection(DEFAULT_SETTINGS.preferences, parsed.preferences),
  };

  return merged;
}

// ---------------------------------------------------------------------------
// Supabase sync helpers — RECTIFY: Supabase (via backend) is source of truth
// ---------------------------------------------------------------------------

/**
 * Merge a raw Supabase app_settings blob (Record) into a validated AppSettings.
 * Uses DEFAULT_SETTINGS as fallback for missing fields; never throws.
 */
export function mergeAppSettingsFromSupabase(raw: unknown): AppSettings {
  if (!raw || typeof raw !== 'object') return getStoredSettings();
  const parsed = raw as Partial<AppSettings>;
  const merged: AppSettings = {
    broker: mergeSection(DEFAULT_SETTINGS.broker, parsed.broker),
    quantitative: mergeSection(DEFAULT_SETTINGS.quantitative, parsed.quantitative),
    ai: mergeSection(DEFAULT_SETTINGS.ai, parsed.ai),
    paper: mergeSection(DEFAULT_SETTINGS.paper, parsed.paper),
    preferences: mergeSection(DEFAULT_SETTINGS.preferences, parsed.preferences),
  };
  let m = migrateMockProvider(merged);
  m = migrateMockAI(m);
  m = migrateConnectionMode(m);
  return m;
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
    app_settings: settings,
  };
}
