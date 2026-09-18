import type { ApiCore } from './client';

export function createInstitutionalApi(core: ApiCore) {
  return {
    async getInstitutionalAuditRecent(limit = 20) {
      return core.request<{ records: Record<string, unknown>[] }>(`/api/v1/institutional/audit/recent?limit=${limit}`);
    },

    async getInstitutionalDataHealthDashboard() {
      return core.request<{
        data_health: Record<string, { status: string; feed: string }>;
        overall: Record<string, string>;
        generated_at_ms: number;
      }>('/api/v1/institutional/dashboard/data-health');
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
  };
}

export type InstitutionalApi = ReturnType<typeof createInstitutionalApi>;
