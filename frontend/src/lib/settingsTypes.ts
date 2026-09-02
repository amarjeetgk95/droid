export type ApiType = 'indian' | 'crypto';
export type IndianProviderId = 'fyers' | 'flattrade';
export type CryptoProviderId = 'binance';
export type BrokerProviderId = IndianProviderId | CryptoProviderId;

export interface FyersCredentials {
  appId: string;
  secret: string;
  redirectUri: string;
  accessToken?: string;
}

export interface FlattradeCredentials {
  userId: string;
  apiKey: string;
  apiSecret: string;
  redirectUri: string;
  token?: string;
}

export interface BinanceCredentials {
  apiKey: string;
  apiSecret: string;
}

export interface BrokerSettings {
  apiType: ApiType;
  provider: BrokerProviderId;
  fyers: FyersCredentials;
  flattrade: FlattradeCredentials;
  binance: BinanceCredentials;
}

export interface QuantitativeSettings {
  riskFreeRate: number;
  timeConvention: 'ACT365' | 'ACT360' | 'TradingDays252';
  defaultPricingModel: 'FUTURES_BLACK76' | 'SPOT_BLACK_SCHOLES';
  ivMethod: 'BRENT' | 'NEWTON_RAPHSON';
  brokeragePerOrder: number;
  slippagePct: number;
}

export type AIConnectionMode = 'OpenRouter' | 'Direct Provider' | 'Local Ollama';
export type DirectProviderId = 'OpenAI' | 'Novita AI' | 'NVIDIA' | 'Google Gemini' | 'Custom OpenAI-Compatible';
export type AIRoutingMode = 'Manual' | 'Task Optimized' | 'Best Available' | 'Cost Optimized';
export type AITaskId = 'INTRADAY_ANALYSIS' | 'NEWS_ANALYSIS' | 'DEEP_RESEARCH' | 'MTF_SYNTHESIS' | 'CHART_EXPLANATION' | 'FINAL_REVIEW';

export interface AISettings {
  provider: 'gemini' | 'openrouter' | 'ollama' | 'mock_ai' | 'openai' | 'novita' | 'nvidia' | 'custom';
  connectionMode: AIConnectionMode;
  directProvider: DirectProviderId;
  routingMode: AIRoutingMode;
  geminiApiKey: string;
  geminiModel: string;
  openRouterApiKey: string;
  openRouterModel: string;
  ollamaBaseUrl: string;
  ollamaModel: string;
  openaiApiKey: string;
  openaiModel: string;
  novitaApiKey: string;
  novitaModel: string;
  nvidiaApiKey: string;
  nvidiaModel: string;
  customOpenaiApiKey: string;
  customOpenaiBaseUrl: string;
  customOpenaiModel: string;
  taskModels: Record<AITaskId, string>;
  openaiBaseUrl: string;
  novitaBaseUrl: string;
  nvidiaBaseUrl: string;
  geminiBaseUrl: string;
  persona: 'INSTITUTIONAL' | 'MOMENTUM' | 'OPTION_SELLER';
  temperature: number;
  cacheTtlSeconds: number;
  openRouterFreeOnly: boolean;
  openRouterPricingFilter: 'FREE' | 'PAID' | 'ALL';
  openRouterSelectedModel: string;
  openRouterAllowPaid: boolean;
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
  schemaVersion?: number;
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
