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

/** One leg of a strategy payoff request / built template. */
export interface StrategyLegInput {
  id?: string | null;
  option_type: string;
  side: string;
  strike: number;
  quantity: number;
  price: number;
  iv?: number | null;
  expiry?: string | null;
  lot_size?: number | null;
}

export interface StrategyPayoffPoint {
  spot: number;
  pnl: number;
}

/** Built template as served by `POST /api/v1/strategy/build-template`. */
export interface BuiltTemplateStrategy {
  template_id: string;
  underlying: string;
  spot_price: number;
  legs: StrategyLegInput[];
  premium_note: string;
  max_profit: number;
  max_loss: number;
  risk_reward: number | null;
  payoff_curve: StrategyPayoffPoint[];
}

/** Honest scanner payload — `scans` is empty until live analytics wire it. */
export interface StrategyScannerData {
  scans: unknown[];
  count: number;
  limitation: string;
}

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

    /**
     * Build a template strategy off the LIVE spot. Fails closed server-side
     * (503) when no live quote exists — the hook surfaces that honestly.
     */
    buildStrategyTemplate: async (templateId: string, symbol: string) => {
      const qs = new URLSearchParams({ template_id: templateId, symbol }).toString();
      return core.request<{ data: BuiltTemplateStrategy; error: string | null; meta: unknown }>(
        `/api/v1/strategy/build-template?${qs}`,
        { method: 'POST' },
      );
    },

    /** Pure payoff math over caller-supplied legs — safe for on-demand use. */
    calculateStrategyPayoff: async (payload: {
      underlying: string;
      spot_price: number;
      expiry?: string | null;
      legs: StrategyLegInput[];
    }) => {
      return core.request<{
        data: {
          underlying: string;
          spot_price: number;
          payoff_curve: StrategyPayoffPoint[];
          legs_count: number;
        };
        error: string | null;
        meta: unknown;
      }>('/api/v1/strategy/payoff', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },

    /**
     * Multi-factor scanner. Honest empty result until live option-chain
     * analytics wire it — never fabricate recommendations client-side.
     */
    getStrategyScanner: async (minPop = 20) => {
      return core.request<{ data: StrategyScannerData; error: string | null; meta: unknown }>(
        `/api/v1/strategy/scanner?min_pop=${minPop}`,
      );
    },
  };
}

export type StrategyApi = ReturnType<typeof createStrategyApi>;
