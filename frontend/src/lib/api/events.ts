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

    async getEventDetail(eventId: string) {
      return core.request<import('../event-types').CanonicalEvent>(
        `/api/v1/events/${encodeURIComponent(eventId)}`,
      );
    },

    async getEventScores(eventId: string) {
      return core.request<import('../event-types').EventScoreSnapshot>(
        `/api/v1/events/${encodeURIComponent(eventId)}/scores`,
      );
    },

    async getEventComparables(eventId: string) {
      return core.request<import('../event-types').EventComparable[]>(
        `/api/v1/events/${encodeURIComponent(eventId)}/comparables`,
      );
    },

    async getEventPrediction(eventId: string) {
      return core.request<import('../event-types').PredictionSnapshot>(
        `/api/v1/events/${encodeURIComponent(eventId)}/prediction`,
      );
    },

    async getEventLiveOpportunity(eventId: string) {
      return core.request<import('../event-types').LiveOpportunityResponse>(
        `/api/v1/events/${encodeURIComponent(eventId)}/live-opportunity`,
      );
    },

    async getEventOutcome(eventId: string) {
      return core.request<import('../event-types').EventOutcome>(
        `/api/v1/events/${encodeURIComponent(eventId)}/outcome`,
      );
    },

    async getEventAlertsQueue() {
      return core.request<import('../event-types').EventAlert[]>(`/api/v1/events/alerts/queue`);
    },

    async ackEventAlert(alertId: string, user = 'OPS_DESK') {
      return core.request<import('../event-types').EventAlert>(
        `/api/v1/events/alerts/${encodeURIComponent(alertId)}/ack?user=${encodeURIComponent(user)}`,
        { method: 'POST' },
      );
    },

    async getEventShadowSignals() {
      return core.request<import('../event-types').ShadowSignalRecord[]>(`/api/v1/events/shadow-signals`);
    },

    async syncRbiEvents() {
      return core.request<import('../event-types').CanonicalEvent[]>(`/api/v1/events/rbi/sync`, {
        method: 'POST',
      });
    },

    async syncCorporateEvents() {
      return core.request<import('../event-types').CanonicalEvent[]>(`/api/v1/events/corporate/sync`, {
        method: 'POST',
      });
    },

    async createManualEvent(payload: Record<string, unknown>) {
      return core.request<import('../event-types').CanonicalEvent>(`/api/v1/events/manual`, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },

    async getEventTrackRecord() {
      return core.request<import('../event-types').EventTrackRecord>(
        `/api/v1/events/analytics/track-record`,
      );
    },

    async getEventSourcesHealth() {
      return core.request<import('../event-types').SourceHealthTelemetry>(`/api/v1/events/sources/health`);
    },
  };
}

export type EventsApi = ReturnType<typeof createEventsApi>;
