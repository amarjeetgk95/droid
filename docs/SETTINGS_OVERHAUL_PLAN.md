# Settings Overhaul Plan — Droid Terminal Configuration

Status: In Progress  
Owner: frontend/src/lib/settings.ts:1, backend/app/api/settings.py:1  
Date: 2026-09-02

## 0. Summary
Unified overhaul of the Terminal Configuration (settings) surface: type-safety, modularity, secret-safety, per-section persistence, and UX hardening. Implemented in 5 phases with backward-compatible migrations.

## 1. Problems Observed
- Monolithic `settings.ts` 509 LOC mixes types + defaults + migrations + storage + supabase `frontend/src/lib/settings.ts:245`
- `SettingsProvider.tsx:105` dirty = `JSON.stringify(settings) !== snapshot` on every render, single global save
- `AIEngineTab.tsx:723` and `BrokerConnectionTab.tsx:817` each >700 LOC with `as any` branches
- Duplicated `BACKEND_BASE`/`REDIRECT_BASE` in broker tab and defaults `frontend/src/components/settings/BrokerConnectionTab.tsx:37` vs `frontend/src/lib/settings.ts:162`
- Telegram `TelegramTab.tsx` not in `AppSettings` but rendered as a settings tab `frontend/src/app/(app)/settings/page.tsx:44`
- Backend shallow merge drops nested keys `backend/app/api/settings.py:98`, in-memory `_dev_settings_store:19` hides DB errors, no audit/version
- `localStorage` + Supabase JSONB dual-write without `schema_version`, 4 ad-hoc migrations run on every load `frontend/src/lib/settings.ts:369`

## 2. Goals / Non-Goals
- Goals: versioned schema, discriminated unions for broker/AI, per-section save, <250 LOC per panel, no `any`, secret-aware export, deep merge, audit.
- Non-goals: changing market-data providers, external vault, email notifications.

## 3. Architecture
```
frontend/src/lib/
  settings.ts              // barrel re-export (compat)
  settingsTypes.ts         // ApiType, BrokerSettings, AISettings, AppSettings (+schemaVersion)
  settingsConstants.ts     // STORAGE_KEYS, SECRET_FIELDS, CURRENT_SCHEMA_VERSION, BACKEND_BASE
  settingsDefaults.ts      // DEFAULT_SETTINGS, SUPPORTED_*MODELS
  settingsMigrations.ts    // migrateLegacyDevConfig, migrateMock*, migrateConnectionMode, migrateSchemaVersion
  settingsStorage.ts       // getStoredSettings, saveStoredSettings, export/import
  settingsSupabase.ts      // mergeAppSettingsFromSupabase, toSupabasePayload
  settingsSchema.ts        // Zod schemas (discriminated), validateSettings, validateSection
  settingsValidation.ts    // shim re-export for backward compat
frontend/src/components/settings/
  SettingsProvider.tsx     // reducer + patchSection + isDirtySection + debounced persist
  ai/ConnectionModeSelector.tsx, RoutingModeSelector.tsx, TaskRoutingGrid.tsx,
     OpenRouterPanel.tsx, DirectProviderPanel.tsx, OllamaPanel.tsx,
     PersonaControls.tsx, LiveVerification.tsx
  broker/ApiTypeSelector.tsx, ProviderGrid.tsx, RenderIntegrationCard.tsx,
         TelemetryCard.tsx, AdvancedDrawer.tsx, constants.ts
backend/app/
  models/database.py       // user_settings.schema_version, encrypted_secrets (future)
  api/settings.py          // deep merge, remove _dev_settings_store, add /schema, audit
  core/broker_runtime.py   // only reconfigure on broker section change
```
Types after:
```ts
type BrokerSettings =
 | { apiType:'indian', provider:'fyers', fyers:{...} }
 | { apiType:'indian', provider:'flattrade', flattrade:{...} }
 | { apiType:'crypto', provider:'binance', binance:{...} }
type AISettings = 
 | { connectionMode:'OpenRouter', openRouter:{...}, routingMode, taskModels }
 | { connectionMode:'Direct Provider', directProvider, openai|novita|nvidia|gemini|custom }
 | { connectionMode:'Local Ollama', ollama:{...} }
```

## 4. Migration
- `schemaVersion:1` implicit → `2` explicit; migrations idempotent.
- `localStorage` read: try `droid_app_settings_v2`, fallback `v1` + migrate, delete `v1` after save.
- Backend backfill Alembic no-op (JSONB tolerant) — reads default to `1` if missing.
- `droid_developer_api_config` legacy merged once then removed `frontend/src/lib/settings.ts:242`.

## 5. Phases
| Phase | Deliverable | Verify |
|-------|-------------|--------|
| 0 Prep | plan doc, build baseline | `npm run build` passes |
| 1 Schema split | 6 new modules + barrel, add schemaVersion | `npm run build`, existing tabs still import from `@/lib/settings` |
| 2 Provider rewrite | reducer, per-section dirty, patch API, keep legacy update* shims | Settings page: edit paper capital, switch tab, no full re-render |
| 3 Tab decomposition | split AI/Broker into subpanels <250 LOC each, extract constants | `npm run build`, visual check |
| 4 Backend hardening | deep merge, remove dev fallback, add /schema, audit | `pytest`, `curl /api/v1/settings/schema` |
| 5 UX polish | per-tab save indicators, debounced autosave, unified TestConnectionButton | E2E: change AI key → Test → Save → reload persists in Supabase |

## 6. Risks
- Secret wipe on save if `""` overwrites stored secret — guard: `mergeSection` skips `""` for secret paths.
- Stream restart storm on every PATCH — backend only restarts when `broker` section diff non-empty.
- Supabase payload >16KB — add server-side size guard.

## 7. Open Qs Resolved for Now
- Secrets stay in `app_settings` JSONB this cycle; `encrypted_secrets` column reserved.
- Telegram stays as Notifications tab but remains API-driven, not in AppSettings.
- `backend/app/core/config.py:14 backend_public_url` becomes canonical REDIRECT_BASE source next cycle; hardcoded Render URL kept with single constant.

## 8. File References
- Frontend entry: `frontend/src/app/(app)/settings/page.tsx:300`
- Provider: `frontend/src/components/settings/SettingsProvider.tsx:91`
- AI: `frontend/src/components/settings/AIEngineTab.tsx:58`
- Broker: `frontend/src/components/settings/BrokerConnectionTab.tsx:83`
- Backend settings: `backend/app/api/settings.py:1`, `backend/app/models/database.py:36`
