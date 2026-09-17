import type { ApiCore } from './client';

export interface IndicatorDefinition {
  indicator_id: string;
  name: string;
  category?: string;
  description?: string;
  lifecycle?: string;
  current_version?: string;
  parameters_schema?: Record<string, unknown>;
}

export interface IndicatorOutput {
  indicator_id: string;
  version: string;
  timestamp: string;
  instrument: string;
  timeframe: string;
  direction: string;
  score: number;
  confidence: number;
  raw_value?: unknown;
  normalized_value?: number | null;
  component_values?: Record<string, unknown>;
  forecast_horizon?: string;
  horizon_candles?: number;
  target_price?: number | null;
  invalidation_price?: number | null;
  data_quality?: string;
}

export interface ResearchPrediction {
  prediction_id: string;
  indicator_id: string;
  indicator_version?: string;
  instrument: string;
  timeframe: string;
  timestamp: string;
  current_price?: number;
  direction: string;
  score?: number;
  confidence?: number;
  component_values?: Record<string, unknown>;
  forecast_horizon?: string;
  horizon_candles?: number;
  target_price?: number | null;
  invalidation_price?: number | null;
  snapshot_id?: string | null;
}

export interface ResearchSnapshot {
  snapshot_id: string;
  instrument: string;
  timeframe: string;
  timestamp: string;
  price: number;
  regime?: string | null;
  session?: string | null;
  features?: Record<string, unknown>;
  options_context?: Record<string, unknown> | null;
  data_quality?: string;
  created_at?: string | null;
}

export interface ResearchAnnotation {
  annotation_id: string;
  instrument: string;
  timeframe?: string;
  timestamp: string;
  title?: string;
  notes?: string;
  author?: string;
  tags?: string[];
  created_at?: string | null;
}

export function createResearchApi(core: ApiCore) {
  return {
    getResearchChartFeatures: (instrument: string, timeframe = '5m') =>
      core.request<Record<string, unknown>>(
        `/api/v1/research/chart/features?instrument=${encodeURIComponent(instrument)}&timeframe=${encodeURIComponent(timeframe)}`,
      ),

    getResearchForecast: (
      horizon: string,
      instrument: string,
      record = true,
      includeExplain = true,
    ) =>
      core.request<Record<string, unknown>>(
        `/api/v1/research/forecast/${encodeURIComponent(horizon)}?instrument=${encodeURIComponent(instrument)}&record=${record ? 'true' : 'false'}&include_explain=${includeExplain ? 'true' : 'false'}`,
      ),

    getResearchTacticalBias: (
      horizon: string,
      instrument: string,
      record = true,
      includeExplain = true,
    ) =>
      core.request<Record<string, unknown>>(
        `/api/v1/research/tactical-bias/${encodeURIComponent(horizon)}?instrument=${encodeURIComponent(instrument)}&record=${record ? 'true' : 'false'}&include_explain=${includeExplain ? 'true' : 'false'}`,
      ),

    createResearchPrediction: (prediction: Record<string, unknown>) =>
      core.request<{ prediction_id: string; status: string }>('/api/v1/research/predictions', {
        method: 'POST',
        body: JSON.stringify(prediction),
      }),
  };
}

export type ResearchApi = ReturnType<typeof createResearchApi>;
