import type { ApiCore } from './client';

export interface DashboardMarketData {
  symbol: string;
  current_price: number | null;
  regime: string;
  atr: number | null;
  vwap: number | null;
}

export interface DashboardQuantitative {
  prob_up: number | null;
  prob_down: number | null;
  p10: number | null;
  p50: number | null;
  p90: number | null;
  method: string;
}

export interface DashboardRisk {
  buy_target: number | null;
  buy_invalidation: number | null;
  buy_rr: number | null;
  sell_target: number | null;
  sell_invalidation: number | null;
  sell_rr: number | null;
}

export interface DashboardSymbolData {
  market: DashboardMarketData;
  mtf: Record<string, string>;
  quantitative: DashboardQuantitative;
  fno: Record<string, unknown>;
  risk: DashboardRisk;
  execution: Record<string, unknown>;
  generated_at: string;
  disclaimer: string;
  degraded: boolean;
  quote_status: string;
  quote_provider: string;
  errors: Record<string, string>;
}

export function createDashboardApi(core: ApiCore) {
  return {
    getDashboardSymbol: (symbol: string) =>
      core.request<{ data: DashboardSymbolData; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/dashboard/${encodeURIComponent(symbol)}`),
  };
}

export type DashboardApi = ReturnType<typeof createDashboardApi>;
