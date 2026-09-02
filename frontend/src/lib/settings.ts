// Barrel re-export — preserves `import {...} from '@/lib/settings'` compatibility.
// Implementation split into focused modules for maintainability.
// See: settingsTypes.ts, settingsConstants.ts, settingsDefaults.ts,
//      settingsMigrations.ts, settingsStorage.ts, settingsSupabase.ts, settingsSchema.ts

export * from './settingsTypes';
export * from './settingsConstants';
export * from './settingsDefaults';
export * from './settingsMigrations';
export * from './settingsStorage';
export * from './settingsSupabase';

// Re-export validation helpers from schema module for convenience
export {
  BrokerSettingsSchema,
  FyersCredentialsSchema,
  FlattradeCredentialsSchema,
  BinanceCredentialsSchema,
  QuantitativeSettingsSchema,
  AISettingsSchema,
  PaperTradingSettingsSchema,
  PreferencesSettingsSchema,
  AppSettingsSchema,
  validateSettings,
  validateSection,
  getFieldError,
} from './settingsSchema';
export type { ValidationError, ValidationResult } from './settingsSchema';
