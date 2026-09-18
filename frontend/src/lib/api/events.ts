import type { ApiCore } from './client';

export function createEventsApi(core: ApiCore) {
  return {
    async getEventRiskOverlay(underlying: string = 'BANKNIFTY') {
    return core.request<import('../event-types').EventRiskParameters>(`/api/v1/events/risk/overlay?underlying=${encodeURIComponent(underlying)}`);
  },

    async getTodayEvents() {
    return core.request<import('../event-types').CanonicalEvent[]>(`/api/v1/events/today`);
  },

    async getUpcomingEvents(limit: number = 50) {
    return core.request<import('../event-types').CanonicalEvent[]>(`/api/v1/events/upcoming?limit=${limit}`);
  },
  };
}

export type EventsApi = ReturnType<typeof createEventsApi>;
