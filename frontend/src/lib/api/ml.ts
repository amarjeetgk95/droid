import type { ApiCore } from './client';

export function createMlApi(core: ApiCore) {
  return {
    getMLShadowGateEval: (params?: { strategy?: string; direction?: string; direction_prob?: number }) => {
      const q = new URLSearchParams();
      if (params?.strategy) q.set('strategy', params.strategy);
      if (params?.direction) q.set('direction', params.direction);
      if (params?.direction_prob !== undefined) q.set('direction_prob', String(params.direction_prob));
      const qs = q.toString() ? `?${q.toString()}` : '';
      return core.request<{ data: Record<string, unknown> }>(`/api/v1/ml/shadow-gate-eval${qs}`);
    },

    async getMLModelInfo() {
    return core.request<{ data: Record<string, any>; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/ml/model-info');
  },

    async getMLTargets() {
    return core.request<{ data: { target_spec_version: string; supported_horizons: number[]; default_horizon_minutes: number; specs: any[] }; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/ml/targets');
  },

    async getMLCalibration(symbol: string, horizonMinutes?: number) {
    const qs = horizonMinutes ? `?horizon_minutes=${horizonMinutes}` : '';
    return core.request<{ data: Record<string, any>; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/ml/calibration/${encodeURIComponent(symbol)}${qs}`);
  },

    async getMLChallengerInfo() {
    return core.request<{ data: { challenger_models: Record<string, any> }; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/ml/challenger-info');
  },

    async getMLChampionInfo() {
    return core.request<{ data: { champion_models: Record<string, any> }; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/ml/champion-info');
  },

    async runMLSettlement(symbol?: string, limit: number = 100) {
    const qs = new URLSearchParams({ limit: String(limit) });
    if (symbol) qs.set('symbol', symbol);
    return core.request<{ data: Record<string, any>; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/ml/settle/run?${qs.toString()}`, { method: 'POST' });
  },

    async getMLPrediction(symbol: string, horizonMinutes?: number) {
    const qs = horizonMinutes ? `?horizon_minutes=${horizonMinutes}` : '';
    return core.request<{ data: Record<string, any>; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/ml/predict/${encodeURIComponent(symbol)}${qs}`);
    },

    async getMLCurrentRegime(symbol: string = 'NIFTY') {
    return core.request<{ data: Record<string, any>; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/ml/current-regime?symbol=${encodeURIComponent(symbol)}`);
    },

    async settleMLOutcome(params: { prediction_id: string; outcome_spot: number; atr_at_t: number; spot_at_t: number }) {
    return core.request<{ data: Record<string, any>; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/ml/outcomes/settle', {
      method: 'POST',
      body: JSON.stringify(params),
    });
    },

    async trainMLEnsemble(params: { features: number[][]; labels: number[]; horizon_minutes?: number; target_spec_version?: string }) {
    return core.request<{ data: Record<string, any>; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/ml/train', {
      method: 'POST',
      body: JSON.stringify(params),
      timeoutMs: 180_000,
    });
    },
  };
}

export type MlApi = ReturnType<typeof createMlApi>;
