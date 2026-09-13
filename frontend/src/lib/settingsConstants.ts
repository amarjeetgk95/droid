// Single source of truth for settings-related constants.
// Extracted from settings.ts and BrokerConnectionTab.tsx to eliminate duplication.

export const CURRENT_SCHEMA_VERSION = 2;

export const STORAGE_KEY = 'droid_app_settings_v1';
export const STORAGE_KEY_V2 = 'droid_app_settings_v2';
export const LEGACY_DEV_CONFIG_KEY = 'droid_developer_api_config';

// Backend is localhost-only (FastAPI on http://127.0.0.1:8000).
// Frontend stays hosted on Firebase (https://fo-droid.web.app) —
// https -> http://127.0.0.1 is allowed as secure context, CORS allows Firebase origin.
export const DEFAULT_BACKEND_BASE = 'http://127.0.0.1:8000';
export const BACKEND_BASE =
  (typeof process !== 'undefined' &&
  process.env.NEXT_PUBLIC_API_URL &&
  !process.env.NEXT_PUBLIC_API_URL.includes('trycloudflare.com')
    ? String(process.env.NEXT_PUBLIC_API_URL).replace(/\/+$/, '')
    : DEFAULT_BACKEND_BASE) || DEFAULT_BACKEND_BASE;

export const REDIRECT_BASE = `${DEFAULT_BACKEND_BASE}/api/v1/tokens`;


// Secrets that must be stripped on export unless includeSecrets:true
export const SECRET_FIELDS: Record<string, string[]> = {
  broker: [
    'fyers.secret',
    'fyers.accessToken',
  ],
  ai: [
    'geminiApiKey',
    'openRouterApiKey',
    'openaiApiKey',
    'novitaApiKey',
    'nvidiaApiKey',
    'customOpenaiApiKey',
  ],
};

// Max JSON payload to guard Supabase JSONB bloat
export const MAX_APP_SETTINGS_BYTES = 16 * 1024;
