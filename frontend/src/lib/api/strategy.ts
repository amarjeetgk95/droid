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

/** One leg of a built strategy (`backend/app/api/strategy.py::StrategyLeg`). */
export interface StrategyLeg {
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

/** One payoff-curve sample as served by the backend: `{spot, pnl}`. */
export interface PayoffCurvePoint {
  spot: number;
  pnl: number;
}

/** `POST /api/v1/strategy/build-template` response body (envelope `data`). */
export interface BuiltTemplateStrategy {
  template_id: string;
  underlying: string;
  spot_price: number;
  legs: StrategyLeg[];
  premium_note?: string;
  max_profit: number;
  max_loss: number;
  risk_reward: number | null;
  payoff_curve: PayoffCurvePoint[];
}

/** `POST /api/v1/strategy/payoff` response body (envelope `data`). */
export interface PayoffResult {
  underlying: string;
  spot_price: number;
  payoff_curve: PayoffCurvePoint[];
  legs_count: number;
}

/** `GET /api/v1/strategy/scanner` response body (envelope `data`). */
export interface StrategyScanResult {
  scans: Record<string, unknown>[];
  count: number;
  limitation?: string;
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
     * `POST /strategy/build-template` reads `template_id`/`symbol` as QUERY
     * PARAMS — it has no JSON request body (backend/app/api/strategy.py:78).
     * Fails closed (503) when the live FYERS spot is unavailable, so callers
     * never receive a strategy built on a fabricated spot.
     */
    buildFromTemplate: (params: { template_id: string; symbol?: string }) => {
      const qs = new URLSearchParams({ template_id: params.template_id });
      if (params.symbol) qs.set('symbol', params.symbol);
      return core.request<{ data: BuiltTemplateStrategy }>(
        `/api/v1/strategy/build-template?${qs.toString()}`,
        { method: 'POST' },
      );
    },

    /**
     * `POST /strategy/payoff` expects `{underlying, spot_price, legs:[{...side}]}`
     * and answers `{data:{underlying,spot_price,payoff_curve:[{spot,pnl}],legs_count}}`
     * (backend/app/api/strategy.py:126).
     */
    calculatePayoff: (payload: {
      underlying: string;
      spot_price: number;
      expiry?: string;
      legs: StrategyLeg[];
    }) =>
      core.request<{ data: PayoffResult }>('/api/v1/strategy/payoff', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),

    /** `GET /strategy/scanner` filters by `min_pop` (backend has no `symbol` param). */
    scanStrategies: (minPop = 20) => {
      const q = `?min_pop=${encodeURIComponent(String(minPop))}`;
      return core.request<{ data: StrategyScanResult }>(`/api/v1/strategy/scanner${q}`);
    },
  };
}

export type StrategyApi = ReturnType<typeof createStrategyApi>;
