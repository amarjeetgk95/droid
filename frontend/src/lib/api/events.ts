import type { ApiCore } from './client';

export function createEventsApi(core: ApiCore) {
  return {
    async acknowledgeAlert(alertId: string, user: string = 'OPS_DESK') {
    return core.request<import('../event-types').EventAlert>(`/api/v1/events/alerts/${encodeURIComponent(alertId)}/ack?user=${encodeURIComponent(user)}`, {
      method: 'POST',
    });
  },

    async getAlertsQueue() {
    return core.request<import('../event-types').EventAlert[]>(`/api/v1/events/alerts/queue`);
  },

    async getEventDetail(eventId: string) {
    return core.request<import('../event-types').CanonicalEvent>(`/api/v1/events/${encodeURIComponent(eventId)}`);
  },

    async getEventOutcome(eventId: string) {
    return core.request<import('../event-types').EventOutcome>(`/api/v1/events/${encodeURIComponent(eventId)}/outcome`);
  },

    async getEventRiskOverlay(underlying: string = 'BANKNIFTY') {
    return core.request<import('../event-types').EventRiskParameters>(`/api/v1/events/risk/overlay?underlying=${encodeURIComponent(underlying)}`);
  },

    async getEventTrackRecord() {
    return core.request<import('../event-types').EventTrackRecord>(`/api/v1/events/analytics/track-record`);
  },

    async getLiveOpportunity(eventId: string) {
    return core.request<import('../event-types').LiveOpportunityResponse>(`/api/v1/events/${encodeURIComponent(eventId)}/live-opportunity`);
  },

    async getShadowSignals() {
    return core.request<import('../event-types').ShadowSignalRecord[]>(`/api/v1/events/shadow-signals`);
  },

    async getSourceHealth() {
    return core.request<import('../event-types').SourceHealthTelemetry>(`/api/v1/events/sources/health`);
  },

    async getTodayEvents() {
    return core.request<import('../event-types').CanonicalEvent[]>(`/api/v1/events/today`);
  },

    async getUpcomingEvents(limit: number = 50) {
    return core.request<import('../event-types').CanonicalEvent[]>(`/api/v1/events/upcoming?limit=${limit}`);
  },

    async syncCorporateEvents() {
    return core.request<import('../event-types').CanonicalEvent[]>(`/api/v1/events/corporate/sync`, { method: 'POST' });
  },

    async syncRbiEvents() {
    return core.request<import('../event-types').CanonicalEvent[]>(`/api/v1/events/rbi/sync`, { method: 'POST' });
  },

    async triggerCalibration() {
    return core.request<{ calibrated_events: number; summary: import('../event-types').CalibrationSummary }>(`/api/v1/events/calibrate`, {
      method: 'POST',
    });
  },
  };
}

export type EventsApi = ReturnType<typeof createEventsApi>;
