import { z } from 'zod';

// ============================================================================
// Zod Schemas for Settings Validation
// ============================================================================

// --- Broker Settings ---
export const BrokerSettingsSchema = z.object({
  provider: z.enum(['mock', 'fyers', 'upstox', 'binance']),
  fyersAppId: z.string().max(100),
  fyersSecret: z.string().max(500),
  fyersRedirectUri: z.string().url('Invalid redirect URI').or(z.literal('')),
  upstoxApiKey: z.string().max(500),
  upstoxSecret: z.string().max(500),
  upstoxRedirectUri: z.string().url('Invalid redirect URI').or(z.literal('')),
  binanceApiKey: z.string().max(500),
  binanceSecretKey: z.string().max(500),
});

// --- Quantitative Settings ---
export const QuantitativeSettingsSchema = z.object({
  riskFreeRate: z.number().min(0, 'Rate must be ≥ 0').max(1, 'Rate must be ≤ 1 (100%)'),
  timeConvention: z.enum(['ACT365', 'ACT360', 'TradingDays252']),
  defaultPricingModel: z.enum(['FUTURES_BLACK76', 'SPOT_BLACK_SCHOLES']),
  ivMethod: z.enum(['BRENT', 'NEWTON_RAPHSON']),
  brokeragePerOrder: z.number().min(0).max(10000, 'Brokerage per order seems too high'),
  slippagePct: z.number().min(0).max(10, 'Slippage above 10% is extreme'),
});

// --- AI Settings ---
export const AISettingsSchema = z.object({
  provider: z.enum(['mock_ai', 'gemini', 'openrouter', 'ollama']),
  geminiApiKey: z.string().max(500).refine(
    (val) => val === '' || val.startsWith('AIza'),
    { message: 'Gemini API keys typically start with "AIza"' }
  ),
  geminiModel: z.string().max(100),
  openRouterApiKey: z.string().max(500).refine(
    (val) => val === '' || val.startsWith('sk-or-'),
    { message: 'OpenRouter keys typically start with "sk-or-"' }
  ),
  openRouterModel: z.string().max(200),
  ollamaBaseUrl: z.string().max(500),
  ollamaModel: z.string().max(200),
  persona: z.enum(['INSTITUTIONAL', 'MOMENTUM', 'OPTION_SELLER']),
  temperature: z.number().min(0, 'Temperature must be ≥ 0').max(2, 'Temperature must be ≤ 2'),
  cacheTtlSeconds: z.number().int().min(0).max(3600, 'Cache TTL must be ≤ 3600s (1hr)'),
}).superRefine((data, ctx) => {
  if (data.provider === 'gemini') {
    if (!data.geminiModel || data.geminiModel.trim() === '') {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['geminiModel'], message: 'Gemini model is required when provider is Gemini' });
    } else if (data.geminiModel.trim() !== '' && data.ollamaBaseUrl && !data.ollamaBaseUrl.startsWith('http') && data.provider === 'gemini') {
      // no-op
    }
    if (data.geminiApiKey !== '' && !data.geminiApiKey.startsWith('AIza')) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['geminiApiKey'], message: 'Gemini API keys typically start with "AIza"' });
    }
  }
  if (data.provider === 'openrouter') {
    if (data.openRouterApiKey !== '' && !data.openRouterApiKey.startsWith('sk-or-')) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['openRouterApiKey'], message: 'OpenRouter keys typically start with "sk-or-"' });
    }
  }
  if (data.provider === 'ollama') {
    if (!data.ollamaBaseUrl || data.ollamaBaseUrl.trim() === '') {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['ollamaBaseUrl'], message: 'Ollama URL is required when provider is Ollama' });
    } else {
      try { new URL(data.ollamaBaseUrl); } catch { ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['ollamaBaseUrl'], message: 'Invalid Ollama URL' }); }
    }
    if (!data.ollamaModel || data.ollamaModel.trim() === '') {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['ollamaModel'], message: 'Ollama model is required when provider is Ollama' });
    }
  }
  // mock_ai requires no additional fields
});

// --- Paper Trading Settings ---
export const PaperTradingSettingsSchema = z.object({
  initialCapital: z.number().int().min(10000, 'Minimum capital is ₹10,000').max(100000000, 'Maximum capital is ₹10Cr'),
  autoSquareOffTime: z.string().regex(
    /^([01]\d|2[0-3]):([0-5]\d)$/,
    'Must be in HH:mm format (e.g., 15:20)'
  ),
  maxCapitalPerTradePct: z.number().min(1, 'Min 1%').max(100, 'Max 100%'),
  maxDailyDrawdownHaltPct: z.number().min(1, 'Min 1%').max(100, 'Max 100%'),
  requireOrderConfirm: z.boolean(),
  allowOvernightPositions: z.boolean(),
});

// --- Preferences Settings ---
export const PreferencesSettingsSchema = z.object({
  theme: z.enum(['dark', 'light', 'system']),
  numberFormat: z.enum(['INDIAN', 'INTERNATIONAL']),
  defaultIndexSymbol: z.string().min(1).max(50),
});

// --- Full AppSettings ---
export const AppSettingsSchema = z.object({
  broker: BrokerSettingsSchema,
  quantitative: QuantitativeSettingsSchema,
  ai: AISettingsSchema,
  paper: PaperTradingSettingsSchema,
  preferences: PreferencesSettingsSchema,
});

// ============================================================================
// Validation Helpers
// ============================================================================

export interface ValidationError {
  path: string;
  message: string;
}

export interface ValidationResult {
  success: boolean;
  errors: ValidationError[];
}

/**
 * Validate a full AppSettings object. Returns structured errors per-field.
 */
export function validateSettings(settings: unknown): ValidationResult {
  const result = AppSettingsSchema.safeParse(settings);
  if (result.success) {
    return { success: true, errors: [] };
  }

  const errors: ValidationError[] = result.error.issues.map((issue) => ({
    path: issue.path.join('.'),
    message: issue.message,
  }));

  return { success: false, errors };
}

/**
 * Validate a single section of settings.
 */
export function validateSection<K extends keyof typeof sectionSchemas>(
  section: K,
  data: unknown
): ValidationResult {
  const schema = sectionSchemas[section];
  const result = schema.safeParse(data);
  if (result.success) {
    return { success: true, errors: [] };
  }

  const errors: ValidationError[] = result.error.issues.map((issue) => ({
    path: `${section}.${issue.path.join('.')}`,
    message: issue.message,
  }));

  return { success: false, errors };
}

const sectionSchemas = {
  broker: BrokerSettingsSchema,
  quantitative: QuantitativeSettingsSchema,
  ai: AISettingsSchema,
  paper: PaperTradingSettingsSchema,
  preferences: PreferencesSettingsSchema,
} as const;

/**
 * Get validation error for a specific field path (e.g. "ai.geminiApiKey")
 */
export function getFieldError(errors: ValidationError[], fieldPath: string): string | undefined {
  return errors.find((e) => e.path === fieldPath)?.message;
}
