import type { ApiCore } from './client';

export function createPaperApi(core: ApiCore) {
  const squareOffPosition = (positionId: string) =>
    core.request<{ data: import('../types').VirtualPosition; error: string | null; meta: import('../types').ApiMeta }>(`/api/v1/paper/position/square-off/${encodeURIComponent(positionId)}`, {
      method: 'POST',
    });

  const squareOffAllPositions = () =>
    core.request<{ data: import('../types').VirtualPosition[]; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/paper/square-off-all', {
      method: 'POST',
    });

  return {
    async getFIIDIIOverview() {
    return core.request<{ data: import('../types').FIIDIIOverviewResponse; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/fii-dii/overview');
  },

    async getFiiDiiActivity() {
    return core.request<{ data: import('../types').FIIDIIOverviewResponse; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/fii-dii/overview');
  },

    async getFiiDiiData() {
    return core.request<{ data: import('../types').FIIDIIOverviewResponse; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/fii-dii/overview');
  },

    async getFlowSnapshot() {
    return core.request<{ data: { live: boolean; pit_note: string; flow: { event_date: string | null; fii_cash_5d_z: number | null; dii_cash_5d_z: number | null; fii_lsr: number | null } | null; composite: { score: number | null; sentiment: string; status: string } | null; drift: { degraded: boolean; reason: string } | null; futures: { status: string } }; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/fii-dii/flow');
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

    squareOffAllPositions,

    closeAllPaperPositions: squareOffAllPositions,

    squareOffPosition,

    closePaperPosition: squareOffPosition,
  };
}

export type PaperApi = ReturnType<typeof createPaperApi>;
