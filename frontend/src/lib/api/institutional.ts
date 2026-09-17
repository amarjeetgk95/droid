import type { ApiCore } from './client';

export function createInstitutionalApi(core: ApiCore) {
  return {
    async getInstitutionalAuditRecent(limit = 20) {
      return core.request<{ records: Record<string, unknown>[] }>(`/api/v1/institutional/audit/recent?limit=${limit}`);
    },

    async getInstitutionalAuditRecord(signalId: string) {
      return core.request<Record<string, unknown>>(`/api/v1/institutional/audit/${encodeURIComponent(signalId)}`);
    },

    async getInstitutionalBreakout(payload: Record<string, unknown>) {
      return core.request<Record<string, unknown>>('/api/v1/institutional/breakout/evaluate', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },

    async getInstitutionalDataHealthDashboard() {
      return core.request<{
        data_health: Record<string, { status: string; feed: string }>;
        overall: Record<string, string>;
        generated_at_ms: number;
      }>('/api/v1/institutional/dashboard/data-health');
    },

    async getInstitutionalHealth() {
      return core.request<{
        data_health: Record<string, Record<string, unknown>>;
        generated_at_ms: number;
      }>('/api/v1/institutional/health/data');
    },

    async getInstitutionalInstruments() {
      return core.request<{ instruments: Record<string, unknown>[]; count: number }>('/api/v1/institutional/instruments');
    },

    async getInstitutionalMI(payload: Record<string, unknown>) {
      return core.request<Record<string, unknown>>('/api/v1/institutional/market-intelligence/evaluate', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },

    async getInstitutionalMIDashboard(instrument: string) {
      return core.request<Record<string, unknown>>(`/api/v1/institutional/dashboard/market-intelligence?instrument_id=${encodeURIComponent(instrument)}`);
    },

    async getInstitutionalSignal(signalId: string) {
      return core.request<Record<string, unknown>>(`/api/v1/institutional/signals/${encodeURIComponent(signalId)}`);
    },

    async getInstitutionalSignalsActive(opts?: { signal?: AbortSignal; timeoutMs?: number }) {
      return core.request<{ signals: Record<string, unknown>[]; count: number; generated_at_ms: number }>('/api/v1/institutional/signals/active', {
        signal: opts?.signal,
        timeoutMs: opts?.timeoutMs ?? 30_000,
        cache: 'no-store',
      } as RequestInit & { timeoutMs?: number });
    },

    async getMIFull(instrument: string, opts?: { signal?: AbortSignal; timeoutMs?: number }) {
      return core.request<Record<string, unknown>>(`/api/v1/institutional/market-intelligence/${encodeURIComponent(instrument)}/full`, {
        signal: opts?.signal,
        timeoutMs: opts?.timeoutMs ?? 30_000,
        cache: 'no-store',
      } as RequestInit & { timeoutMs?: number });
    },

    async getCallsPutsFull(underlying: string, expiry?: string) {
      const qs = expiry ? `?expiry=${encodeURIComponent(expiry)}` : '';
      return core.request<Record<string, unknown>>(`/api/v1/institutional/calls-puts/${encodeURIComponent(underlying)}/full${qs}`);
    },

    async getSnapshotSynchronized(instruments: string[] | string) {
      const list = Array.isArray(instruments) ? instruments.join(',') : instruments;
      return core.request<Record<string, unknown>>(`/api/v1/institutional/snapshot/synchronized?instruments=${encodeURIComponent(list)}`);
    },

    async getSnapshotHealth() {
      return core.request<Record<string, unknown>>('/api/v1/institutional/snapshot/health');
    },

    async getFeedHealth(instrumentId?: string) {
      const path = instrumentId
        ? `/api/v1/institutional/feed/${encodeURIComponent(instrumentId)}/health`
        : '/api/v1/institutional/feed/health';
      return core.request<Record<string, unknown>>(path);
    },

    async tripFeedCircuit(instrumentId: string, anomaly = 'MISSING', reason = 'manual trip') {
      const qs = new URLSearchParams({ anomaly, reason }).toString();
      return core.request<Record<string, unknown>>(`/api/v1/institutional/feed/${encodeURIComponent(instrumentId)}/trip?${qs}`, {
        method: 'POST',
      });
    },

    async resyncFeedCircuit(instrumentId: string) {
      return core.request<Record<string, unknown>>(`/api/v1/institutional/feed/${encodeURIComponent(instrumentId)}/resync-request`, {
        method: 'POST',
      });
    },

    async confirmAI(payload: Record<string, unknown>) {
      return core.request<{
        short_horizon: Record<string, unknown>;
        continuation: Record<string, unknown>;
        overall_assessment: string;
        ai_status: string;
        error: string | null;
      }>('/api/v1/institutional/ai/confirm', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },

    async evaluatePortfolioRisk(payload: Record<string, unknown>) {
      return core.request<{
        result: string;
        reason: string | null;
        failed_check: string | null;
        checks: Array<{ name: string; passed: boolean; reason: string | null }>;
        portfolio: { gross: string; net: string; margin_used: string };
      }>('/api/v1/institutional/risk/portfolio-evaluate', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },

    async getSignalTtl(signalId: string) {
      return core.request<Record<string, unknown>>(`/api/v1/institutional/dashboard/signal-ttl/${encodeURIComponent(signalId)}`);
    },

    async institutionalPipelineIngest(event: Record<string, unknown>, mockAi?: Record<string, unknown>) {
      const qs = mockAi ? `?mock_ai_response=${encodeURIComponent(JSON.stringify(mockAi))}` : '';
      return core.request<Record<string, unknown>>(`/api/v1/institutional/pipeline/ingest${qs}`, {
        method: 'POST',
        body: JSON.stringify(event),
      });
    },
  };
}

export type InstitutionalApi = ReturnType<typeof createInstitutionalApi>;
