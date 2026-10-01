import { ApiCore, API_BASE, type RequestOptions } from './client';

const defaultCore = new ApiCore(API_BASE);

async function request<T>(path: string, options?: RequestOptions): Promise<T> {
  return defaultCore.request<T>(path, options);
}

export interface PapGate {
  name: string;
  passed: boolean;
  detail: string;
}

export interface PapInstrumentData {
  instrument: string;
  slug: string;
  path: string;
  present: boolean;
  admissible: boolean;
  source: string | null;
  row_count: number | null;
  checksum_sha256: string | null;
  reasons: string[];
  screen: Record<string, unknown> | null;
}

export interface PapReportSummary {
  file: string;
  verdict: string | null;
  created: string | null;
  criteria_version: string | null;
  experiment_id: string | null;
  unreadable?: boolean;
}

export type PapVerdict = 'PASS' | 'FAIL' | 'INCONCLUSIVE' | 'NOT_RUN';

export interface PapStatus {
  phase: string;
  verdict: PapVerdict;
  criteria_version: string;
  pre_registered: Record<string, string>;
  gates: PapGate[];
  instruments: PapInstrumentData[];
  token_present: boolean;
  horizons: string[];
  reports: PapReportSummary[];
}

export type PapDataStatus = 'LIVE' | 'DELAYED' | 'STALE' | 'OFFLINE';
export type PapPrediction = 'UP' | 'NEUTRAL' | 'DOWN';
export type PapAlignment = 'ALIGNED' | 'NEUTRAL' | 'CONFLICT' | 'NO_DROID_SIGNAL' | 'PAP_UNAVAILABLE';

export interface PapHorizon {
  up: number;
  neutral: number;
  down: number;
  prediction: PapPrediction;
  probability: number;
  /** Null unless the backend artifact triple is calibrated for this horizon. */
  confidence: number | null;
  prediction_state: 'ACTIVE' | 'STALE';
  model_source: string;
  calibrated: boolean;
  artifact_horizon_minutes: number | null;
  model_version: string;
}

export interface PapLive {
  instrument: string;
  timeframe: string;
  timestamp: string;
  price: number | null;
  data_status: PapDataStatus;
  data_age_s: number | null;
  available: boolean;
  unavailable_code?: string | null;
  unavailable_reason?: string | null;
  mode: string;
  execution: string;
  horizons: Record<string, PapHorizon> | null;
  features: Record<string, number | null> | null;
  market_state: Record<string, number | string | null> | null;
  evidence: Array<{ label: string; state: string; detail: string }>;
  evidence_note?: string;
  droid_alignment: {
    droid_signal: string | null;
    droid_state?: string | null;
    droid_strategy?: string | null;
    pap_primary: PapPrediction | null;
    pap_primary_horizon?: string;
    alignment: PapAlignment;
    advisory_only: boolean;
  };
  horizon_consensus: { consensus: string; predictions: Record<string, PapPrediction> | null };
  model: {
    name: string;
    versions: string[];
    feature_schema: string;
    calibration: string;
    data_quality: string;
    prediction_age_s: number | null;
    status: string;
    shadow_mode: string;
    execution: string;
  };
  calibration: { status: string; note: string };
}

export interface PapResearchSummary {
  status: 'OK' | 'INSUFFICIENT_SAMPLE';
  n: number;
  reason?: string;
  metrics: Record<string, unknown> | null;
  baseline: Record<string, unknown> | null;
  lift: Record<string, unknown> | null;
  walk_forward: {
    status: string;
    folds: Array<{ fold: number; n: number; uplift: number; positive: boolean }>;
    positive_folds?: string;
    mean_uplift?: number;
    confidence_interval?: [number, number];
    reason?: string;
    economic_evaluated?: boolean;
  };
  filters?: Record<string, unknown>;
  ledger?: { total: number; settled: number };
}

export interface PapPredictionRow {
  time: string | null;
  instrument: string;
  horizon_minutes: number | null;
  horizon: string | null;
  p_up: number;
  p_neutral: number;
  p_down: number;
  prediction: PapPrediction | null;
  actual: PapPrediction | null;
  correct: boolean | null;
  confidence: number;
  price_change_pct: number | null;
  mfe_pct: number | null;
  mae_pct: number | null;
}

export interface PapCalibration {
  buckets: Array<{
    bucket: string;
    n: number;
    predicted: number | null;
    observed: number | null;
    error: number | null;
    status: string;
  }>;
  n: number;
}

export interface PapGroupedRow {
  name: string;
  n: number;
  balanced_accuracy: number | null;
  macro_f1: number | null;
  brier: number | null;
  up_precision?: number | null;
  down_precision?: number | null;
  status: string;
}

export type PapResearchFilters = {
  instrument?: string;
  horizon?: string;
  period?: { from?: string; to?: string };
  model?: string;
  session?: string;
  regime?: string;
  outcome?: string;
  minConfidence?: number;
};

export function createPapApi(core: ApiCore) {
  return {
    async getStatus(): Promise<PapStatus> {
      const res = await core.request<{ data: PapStatus }>('/api/v1/pap/status');
      return res.data;
    },

    async getLive(instrument: string): Promise<PapLive> {
      const res = await core.request<{ data: PapLive }>(
        `/api/v1/pap/live/${encodeURIComponent(instrument)}`,
      );
      return res.data;
    },

    async getHorizons(instrument: string): Promise<Pick<PapLive, 'instrument' | 'timestamp' | 'price' | 'data_status' | 'data_age_s' | 'available' | 'horizons' | 'horizon_consensus'>> {
      const res = await core.request<{ data: PapLive }>(
        `/api/v1/pap/live/${encodeURIComponent(instrument)}/horizons`,
      );
      return res.data;
    },

    async getResearchSummary(params?: { instrument?: string; horizon_minutes?: number }): Promise<PapResearchSummary> {
      const q = new URLSearchParams();
      if (params?.instrument) q.set('instrument', params.instrument);
      if (params?.horizon_minutes !== undefined) q.set('horizon_minutes', String(params.horizon_minutes));
      const qs = q.toString() ? `?${q.toString()}` : '';
      const res = await core.request<{ data: PapResearchSummary }>(`/api/v1/pap/research/summary${qs}`);
      return res.data;
    },

    async getResearchPredictions(params?: {
      instrument?: string;
      horizon_minutes?: number;
      outcome?: string;
      prediction?: string;
      min_confidence?: number;
      limit?: number;
    }): Promise<{ rows: PapPredictionRow[]; count: number }> {
      const q = new URLSearchParams();
      if (params?.instrument) q.set('instrument', params.instrument);
      if (params?.horizon_minutes !== undefined) q.set('horizon_minutes', String(params.horizon_minutes));
      if (params?.outcome) q.set('outcome', params.outcome);
      if (params?.prediction) q.set('prediction', params.prediction);
      if (params?.min_confidence !== undefined) q.set('min_confidence', String(params.min_confidence));
      if (params?.limit !== undefined) q.set('limit', String(params.limit));
      const qs = q.toString() ? `?${q.toString()}` : '';
      const res = await core.request<{ data: { rows: PapPredictionRow[]; count: number } }>(
        `/api/v1/pap/research/predictions${qs}`,
      );
      return res.data;
    },

    async getResearchCalibration(params?: { instrument?: string; horizon_minutes?: number }): Promise<PapCalibration> {
      const q = new URLSearchParams();
      if (params?.instrument) q.set('instrument', params.instrument);
      if (params?.horizon_minutes !== undefined) q.set('horizon_minutes', String(params.horizon_minutes));
      const qs = q.toString() ? `?${q.toString()}` : '';
      const res = await core.request<{ data: PapCalibration }>(`/api/v1/pap/research/calibration${qs}`);
      return res.data;
    },

    async getResearchRegimes(params?: { instrument?: string; horizon_minutes?: number }): Promise<{ regimes: PapGroupedRow[] }> {
      const q = new URLSearchParams();
      if (params?.instrument) q.set('instrument', params.instrument);
      if (params?.horizon_minutes !== undefined) q.set('horizon_minutes', String(params.horizon_minutes));
      const qs = q.toString() ? `?${q.toString()}` : '';
      const res = await core.request<{ data: { regimes: PapGroupedRow[] } }>(`/api/v1/pap/research/regimes${qs}`);
      return res.data;
    },

    async getResearchSessions(params?: { instrument?: string; horizon_minutes?: number }): Promise<{ sessions: PapGroupedRow[] }> {
      const q = new URLSearchParams();
      if (params?.instrument) q.set('instrument', params.instrument);
      if (params?.horizon_minutes !== undefined) q.set('horizon_minutes', String(params.horizon_minutes));
      const qs = q.toString() ? `?${q.toString()}` : '';
      const res = await core.request<{ data: { sessions: PapGroupedRow[] } }>(`/api/v1/pap/research/sessions${qs}`);
      return res.data;
    },

    async getResearchAblation(): Promise<{ status: string; reason: string; experiments: unknown[] }> {
      const res = await core.request<{ data: { status: string; reason: string; experiments: unknown[] } }>(
        '/api/v1/pap/research/ablation',
      );
      return res.data;
    },

    async getResearchTradability(): Promise<Record<string, unknown>> {
      const res = await core.request<{ data: Record<string, unknown> }>('/api/v1/pap/research/tradability');
      return res.data;
    },

    async getResearchChart(params?: { instrument?: string; horizon_minutes?: number; limit?: number }): Promise<{
      status: string;
      reason: string | null;
      instrument: string;
      candles: Array<{ time: number; open: number; high: number; low: number; close: number }>;
      markers: Array<{
        time: number;
        prediction: PapPrediction | null;
        horizon: string | null;
        p_up: number;
        p_neutral: number;
        p_down: number;
        actual: PapPrediction | null;
        correct: boolean | null;
        price_change_pct: number | null;
        confidence: number;
      }>;
    }> {
      const q = new URLSearchParams();
      if (params?.instrument) q.set('instrument', params.instrument);
      if (params?.horizon_minutes !== undefined) q.set('horizon_minutes', String(params.horizon_minutes));
      if (params?.limit !== undefined) q.set('limit', String(params.limit));
      const qs = q.toString() ? `?${q.toString()}` : '';
      const res = await core.request<{ data: Awaited<ReturnType<PapApi['getResearchChart']>> }>(
        `/api/v1/pap/research/chart${qs}`,
      );
      return res.data;
    },
  };
}

export type PapApi = ReturnType<typeof createPapApi>;

export const papApi: PapApi = createPapApi(defaultCore);
