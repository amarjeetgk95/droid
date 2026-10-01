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
import { createAlgoApi, type AlgoApi } from './api/algo';
import { createMlApi, type MlApi } from './api/ml';
import { createStrategyApi, type StrategyApi } from './api/strategy';
import { createTelegramApi, type TelegramApi } from './api/telegram';
import { createTokensApi, type TokensApi } from './api/tokens';
import { createVortexApi, type VortexApi } from './api/vortex';
import { createHistoricalApi, type HistoricalApi } from './api/historical';
import { createPapApi, type PapApi } from './api/pap';
import { createFisherMacdApi, type FisherMacdApi } from './api/fisherMacd';
import { createIndicatorResearchApi, type IndicatorResearchApi } from './api/indicatorResearch';

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
  IntelligenceApi &
  AlgoApi &
  MlApi &
  StrategyApi &
  TelegramApi &
  TokensApi &
  VortexApi &
  HistoricalApi &
  PapApi &
  FisherMacdApi &
  IndicatorResearchApi;

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
  createAlgoApi(core),
  createMlApi(core),
  createStrategyApi(core),
  createTelegramApi(core),
  createTokensApi(core),
  createVortexApi(core),
  createHistoricalApi(core),
  createPapApi(core),
  createFisherMacdApi(core),
  createIndicatorResearchApi(core),
);

/** Back-compat alias — no code constructs ApiClient directly (singleton `api` is the entrypoint). */
export type ApiClient = Api;
export { API_BASE };
export { ApiCore };
