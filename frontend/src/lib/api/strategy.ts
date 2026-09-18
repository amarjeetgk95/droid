import type { ApiCore } from './client';

/**
 * A strategy template row as served by `GET /api/v1/strategy/templates`.
 * Backend rows are keyed by `id` and carry `legs_count` (not a `legs` array) —
 * see `backend/app/api/strategy.py::TEMPLATES`.
 */
export interface StrategyTemplate {
  id: string;
  name: string;
  description: string;
  category: string;
  legs_count: number;
}

/** Raw list row — tolerates the legacy `template_id` alias for normalization. */
type RawStrategyTemplate = Omit<StrategyTemplate, 'id'> & {
  id?: string;
  template_id?: string;
};

export function createStrategyApi(core: ApiCore) {
  return {
    /**
     * Template list. Backend rows are keyed by `id`; normalize at this boundary
     * (mapping any legacy `template_id` through) so every consumer sees a
     * stable `id`.
     */
    getStrategyTemplates: async () => {
      const res = await core.request<{ data: RawStrategyTemplate[] }>('/api/v1/strategy/templates');
      const rows = Array.isArray(res?.data) ? res.data : [];
      const data: StrategyTemplate[] = rows.map((t) => ({
        id: t.id ?? t.template_id ?? '',
        name: t.name,
        description: t.description,
        category: t.category,
        legs_count: t.legs_count,
      }));
      return { ...res, data };
    },
  };
}

export type StrategyApi = ReturnType<typeof createStrategyApi>;
