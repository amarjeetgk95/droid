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

    trainMLModel: (payload: {
      features: number[][];
      labels: number[];
      horizon_minutes?: number;
      target_spec_version?: string;
    }) =>
      core.request<{ data: Record<string, unknown> }>('/api/v1/ml/train', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),

    settleMLOutcome: (payload: {
      prediction_id: string;
      outcome_spot: number;
      atr_at_t: number;
      spot_at_t: number;
    }) =>
      core.request<{ data: Record<string, unknown> }>('/api/v1/ml/outcomes/settle', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
  };
}

export type MlApi = ReturnType<typeof createMlApi>;
