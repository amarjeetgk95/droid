import type { ApiCore } from './client';

export function createPaperApi(core: ApiCore) {
  return {
    async getFIIDIIOverview() {
    return core.request<{ data: import('../types').FIIDIIOverviewResponse; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/fii-dii/overview');
  },

    async getMLPrediction(symbol: string = 'NIFTY') {
    return core.request<{ data: import('../types').MLPredictionResponse; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/ml/predict/${encodeURIComponent(symbol)}`);
  },

    async getPaperOrders() {
    return core.request<{ data: import('../types').VirtualOrder[]; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/paper/orders');
  },

    async getPaperPortfolio() {
    return core.request<{ data: import('../types').PortfolioSummary; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/paper/portfolio');
  },

    async getPaperPositions() {
    return core.request<{ data: import('../types').VirtualPosition[]; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/paper/positions');
  },

    async placePaperBasket(payload: import('../types').BasketOrderPayload) {
    return core.request<{ data: import('../types').VirtualOrder[]; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/paper/basket', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

    async placePaperOrder(payload: import('../types').OrderPayload) {
    return core.request<{ data: import('../types').VirtualOrder; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/paper/order', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

    async previewPaperMargin(payload: { symbol: string; underlying: string; side: 'BUY' | 'SELL'; quantity: number; price: number }) {
    return core.request<{ data: { required_margin: number; premium: number; available_margin: number; affordable: boolean }; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/paper/preview', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

    async resetPaperAccount() {
    return core.request<{ data: import('../types').PortfolioSummary; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/paper/reset', {
      method: 'POST',
    });
  },

    async squareOffAllPositions() {
    return core.request<{ data: import('../types').VirtualPosition[]; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/paper/square-off-all', {
      method: 'POST',
    });
  },

    async squareOffPosition(positionId: string) {
    return core.request<{ data: import('../types').VirtualPosition; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/paper/position/square-off/${encodeURIComponent(positionId)}`, {
      method: 'POST',
    });
  },
  };
}

export type PaperApi = ReturnType<typeof createPaperApi>;
