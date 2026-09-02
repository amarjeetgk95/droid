// Shim — preserve `import { validateSettings } from '@/lib/settingsValidation'`.
// Canonical schemas now live in settingsSchema.ts. This file re-exports.

export {
  FyersCredentialsSchema,
  FlattradeCredentialsSchema,
  BinanceCredentialsSchema,
  BrokerSettingsSchema,
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
export { z } from './settingsSchema';
