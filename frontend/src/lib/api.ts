// Facade preserving `import { api } from '@/lib/api'`.
// Implementation lives in `./api/` by domain; this file only composes the singleton.
import { ApiCore, API_BASE } from './api/client';
import { createMarketsApi, type MarketsApi } from './api/markets';
import { createSystemApi, type SystemApi } from './api/system';
import { createOptionsApi, type OptionsApi } from './api/options';
import { createAiApi, type AiApi } from './api/ai';
import { createPaperApi, type PaperApi } from './api/paper';
import { createAccountApi, type AccountApi } from './api/account';
import { createInstitutionalApi, type InstitutionalApi } from './api/institutional';
import { createSignalsApi, type SignalsApi } from './api/signals';
import { createEventsApi, type EventsApi } from './api/events';
import { createIntelligenceApi, type IntelligenceApi } from './api/intelligence';

export type Api = ApiCore &
  MarketsApi &
  SystemApi &
  OptionsApi &
  AiApi &
  PaperApi &
  AccountApi &
  InstitutionalApi &
  SignalsApi &
  EventsApi &
  IntelligenceApi;

const core = new ApiCore(API_BASE);

export const api: Api = Object.assign(
  core,
  createMarketsApi(core),
  createSystemApi(core),
  createOptionsApi(core),
  createAiApi(core),
  createPaperApi(core),
  createAccountApi(core),
  createInstitutionalApi(core),
  createSignalsApi(core),
  createEventsApi(core),
  createIntelligenceApi(core),
);
/** Back-compat alias — no code constructs ApiClient directly (singleton `api` is the entrypoint). */
export type ApiClient = Api;
export { API_BASE };
export { ApiCore };
