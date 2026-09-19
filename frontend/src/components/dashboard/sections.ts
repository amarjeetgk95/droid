import type {
  FIIDIIOverviewResponse,
  HourForecast,
  IndexCard,
  MarketBreadthData,
  MarketRegimeOverview,
  MarketStatusResponse,
  MLPredictionResponse,
  OptionsAnalytics,
} from '@/lib/types';

export type MarketSectionValue = {
  cards?: IndexCard[] | null;
  breadth?: MarketBreadthData | null;
  market_status?: MarketStatusResponse | null;
};

export type RegimeSectionValue = {
  regime_overview?: MarketRegimeOverview | null;
  options_analytics?: OptionsAnalytics | null;
  by_symbol?: Record<string, MarketRegimeOverview | null> | null;
};

export type MlSectionValue = {
  ml_prediction?: MLPredictionResponse | null;
  by_symbol?: Record<string, MLPredictionResponse | null> | null;
};

export type RiskEventsSectionValue = {
  fii_dii?: FIIDIIOverviewResponse | null;
  event_risk?: Record<string, unknown> | null;
};

export type FeedHealthSectionValue = {
  subsystems?: Record<string, unknown> | null;
  feed_circuits?: Record<string, unknown> | null;
};

export type ForecastSectionValue = {
  forecast?: HourForecast | null;
  predictions?: unknown[] | null;
  by_instrument?: Record<string, unknown[] | null> | null;
};

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

export function narrowMarket(value: unknown): MarketSectionValue | null {
  return asRecord(value) as MarketSectionValue | null;
}

export function narrowRegime(value: unknown): RegimeSectionValue | null {
  return asRecord(value) as RegimeSectionValue | null;
}

export function narrowMl(value: unknown): MlSectionValue | null {
  return asRecord(value) as MlSectionValue | null;
}

export function narrowRiskEvents(value: unknown): RiskEventsSectionValue | null {
  return asRecord(value) as RiskEventsSectionValue | null;
}

export function narrowFeedHealth(value: unknown): FeedHealthSectionValue | null {
  return asRecord(value) as FeedHealthSectionValue | null;
}

export function narrowForecast(value: unknown): ForecastSectionValue | null {
  return asRecord(value) as ForecastSectionValue | null;
}

export function pickByInstrument<T>(
  map: Record<string, T | null> | null | undefined,
  instrument: string,
): T | null {
  if (!map) return null;
  const key = Object.keys(map).find(
    (candidate) => candidate.toUpperCase() === instrument.toUpperCase(),
  );
  if (!key) return null;
  return map[key] ?? null;
}
