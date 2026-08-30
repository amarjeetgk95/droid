import { z } from 'zod';

// ============================================================================
// Zod Schemas for Settings Validation
// ============================================================================

// --- Broker Settings ---
export const BrokerSettingsSchema = z.object({
  provider: z.enum(['mock', 'fyers', 'upstox', 'binance']),
  fyersAppId: z.string().trim().max(100),
  fyersSecret: z.string().trim().max(500),
  fyersRedirectUri: z.string().trim().url('Invalid redirect URI').or(z.literal('')),
  upstoxApiKey: z.string().trim().max(500),
  upstoxSecret: z.string().trim().max(500),
  upstoxRedirectUri: z.string().trim().url('Invalid redirect URI').or(z.literal('')),
  binanceApiKey: z.string().trim().max(500),
  binanceSecretKey: z.string().trim().max(500),
});

// --- Quantitative Settings ---
export const QuantitativeSettingsSchema = z.object({
  riskFreeRate: z.coerce.number().min(0, 'Rate must be ≥ 0').max(1, 'Rate must be ≤ 1 (100%)'),
  timeConvention: z.enum(['ACT365', 'ACT360', 'TradingDays252']),
  defaultPricingModel: z.enum(['FUTURES_BLACK76', 'SPOT_BLACK_SCHOLES']),
  ivMethod: z.enum(['BRENT', 'NEWTON_RAPHSON']),
  brokeragePerOrder: z.coerce.number().min(0).max(10000, 'Brokerage per order seems too high'),
  slippagePct: z.coerce.number().min(0).max(10, 'Slippage above 10% is extreme'),
});

// --- AI Settings ---
export const AISettingsSchema = z.object({
  provider: z.enum(['gemini', 'openrouter', 'ollama']),
  geminiApiKey: z.string().trim().max(500),
  geminiModel: z.string().trim().max(100),
  openRouterApiKey: z.string().trim().max(500),
  openRouterModel: z.string().trim().max(200),
  ollamaBaseUrl: z.string().trim().max(500),
  ollamaModel: z.string().trim().max(200),
  persona: z.enum(['INSTITUTIONAL', 'MOMENTUM', 'OPTION_SELLER']),
  temperature: z.coerce.number().min(0, 'Temperature must be ≥ 0').max(2, 'Temperature must be ≤ 2'),
  cacheTtlSeconds: z.coerce.number().int().min(0).max(3600, 'Cache TTL must be ≤ 3600s (1hr)'),
}).superRefine((data, ctx) => {
  if (data.provider === 'gemini') {
    if (!data.geminiModel || data.geminiModel.trim() === '') {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['geminiModel'], message: 'Gemini model is required when provider is Gemini' });
    }
    // Prefix hints for Gemini/OpenRouter are shown as UI warnings, not blocking validation.
    // Empty keys are allowed (user can save without configuring AI).
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
  initialCapital: z.coerce.number().int().min(10000, 'Minimum capital is ₹10,000').max(100000000, 'Maximum capital is ₹10Cr'),
  autoSquareOffTime: z.string().trim().regex(
    /^([01]\d|2[0-3]):([0-5]\d)$/,
    'Must be in HH:mm format (e.g., 15:20)'
  ),
  maxCapitalPerTradePct: z.coerce.number().min(1, 'Min 1%').max(100, 'Max 100%'),
  maxDailyDrawdownHaltPct: z.coerce.number().min(1, 'Min 1%').max(100, 'Max 100%'),
  requireOrderConfirm: z.boolean(),
  allowOvernightPositions: z.boolean(),
});

// --- Preferences Settings ---
export const PreferencesSettingsSchema = z.object({
  theme: z.enum(['dark', 'light', 'system']),
  numberFormat: z.enum(['INDIAN', 'INTERNATIONAL']),
  defaultIndexSymbol: z.string().trim().min(1).max(50),
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
