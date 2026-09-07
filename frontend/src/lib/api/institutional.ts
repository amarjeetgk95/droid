import type { ApiCore } from './client';

export function createInstitutionalApi(core: ApiCore) {
  return {
    async getInstitutionalAuditRecent(limit = 20) {
    return core.request<any>(`/api/v1/institutional/audit/recent?limit=${limit}`);
  },

    async getInstitutionalBreakout(payload: any) {
    return core.request<any>('/api/v1/institutional/breakout/evaluate', { method: 'POST', body: JSON.stringify(payload) });
  },

    async getInstitutionalDataHealthDashboard() {
    return core.request<any>('/api/v1/institutional/dashboard/data-health');
  },

    async getInstitutionalHealth() {
    return core.request<any>('/api/v1/institutional/health/data');
  },

    async getInstitutionalInstruments() {
    return core.request<any>('/api/v1/institutional/instruments');
  },

    async getInstitutionalMI(payload: any) {
    return core.request<any>('/api/v1/institutional/market-intelligence/evaluate', { method: 'POST', body: JSON.stringify(payload) });
  },

    async getInstitutionalMIDashboard(instrument: string) {
    return core.request<any>(`/api/v1/institutional/dashboard/market-intelligence?instrument_id=${encodeURIComponent(instrument)}`);
  },

    async getInstitutionalSignal(signalId: string) {
    return core.request<any>(`/api/v1/institutional/signals/${encodeURIComponent(signalId)}`);
  },

    async getInstitutionalSignalsActive(opts?: { signal?: AbortSignal; timeoutMs?: number }) {
    return core.request<any>('/api/v1/institutional/signals/active', {
      signal: opts?.signal,
      timeoutMs: opts?.timeoutMs ?? 30_000,
      cache: 'no-store',
    } as RequestInit & { timeoutMs?: number });
  },

    async getMIFull(instrument: string, opts?: { signal?: AbortSignal; timeoutMs?: number }) {
    return core.request<any>(`/api/v1/institutional/market-intelligence/${encodeURIComponent(instrument)}/full`, {
      signal: opts?.signal,
      timeoutMs: opts?.timeoutMs ?? 30_000,
      cache: 'no-store',
    } as RequestInit & { timeoutMs?: number });
  },

    async institutionalIngestDirect(event: any) {
    return core.request<any>('/api/v1/institutional/pipeline/ingest', { method: 'POST', body: JSON.stringify(event) });
  },

    async institutionalPipelineIngest(event: any, mockAi?: any) {
    // Backend takes the raw tick as the JSON body; mock_ai_response is a query param.
    const qs = mockAi ? `?mock_ai_response=${encodeURIComponent(JSON.stringify(mockAi))}` : '';
    return core.request<any>(`/api/v1/institutional/pipeline/ingest${qs}`, { method: 'POST', body: JSON.stringify(event) });
  },
  };
}

export type InstitutionalApi = ReturnType<typeof createInstitutionalApi>;
