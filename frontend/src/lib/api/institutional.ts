import type { ApiCore } from './client';

export function createInstitutionalApi(core: ApiCore) {
  return {
    async listInstitutionalInstruments() {
      return core.request<{ instruments: Record<string, unknown>[]; count: number }>(
        '/api/v1/institutional/instruments',
      );
    },

    async getInstitutionalDashboardMI(instrumentId: string) {
      return core.request<Record<string, unknown>>(
        `/api/v1/institutional/dashboard/market-intelligence?instrument_id=${encodeURIComponent(instrumentId)}`,
      );
    },

    async getInstitutionalAuditRecent(limit = 20) {
      return core.request<{ records: Record<string, unknown>[] }>(`/api/v1/institutional/audit/recent?limit=${limit}`);
    },

    async getInstitutionalAuditOne(signalId: string) {
      return core.request<Record<string, unknown>>(
        `/api/v1/institutional/audit/${encodeURIComponent(signalId)}`,
      );
    },

    async getInstitutionalSignalsActive(params?: { instrument?: string; status?: string }) {
      const qs = new URLSearchParams();
      if (params?.instrument) qs.set('instrument', params.instrument);
      if (params?.status) qs.set('status', params.status);
      const q = qs.toString() ? `?${qs.toString()}` : '';
      return core.request<{ signals: Record<string, unknown>[]; count: number; generated_at_ms: number }>(
        `/api/v1/institutional/signals/active${q}`,
      );
    },

    async getInstitutionalSignalsHistory(limit = 20) {
      return core.request<{ records: Record<string, unknown>[] }>(
        `/api/v1/institutional/signals/history?limit=${limit}`,
      );
    },

    async getInstitutionalSignal(signalId: string) {
      return core.request<Record<string, unknown>>(
        `/api/v1/institutional/signals/${encodeURIComponent(signalId)}`,
      );
    },

    async transitionInstitutionalSignal(signalId: string, toState: string) {
      return core.request<Record<string, unknown>>(
        `/api/v1/institutional/signals/${encodeURIComponent(signalId)}/transition?to_state=${encodeURIComponent(toState)}`,
        { method: 'POST' },
      );
    },

    async casInstitutionalSignalExecution(signalId: string) {
      return core.request<Record<string, unknown>>(
        `/api/v1/institutional/signals/${encodeURIComponent(signalId)}/cas-execution`,
        { method: 'POST' },
      );
    },

    async getInstitutionalSignalTtl(signalId: string) {
      return core.request<{
        signal_id: string;
        is_expired: boolean;
        ttl_remaining_ms: number | null;
        valid: boolean;
        error: string | null;
        fsm_state: string;
      }>(`/api/v1/institutional/signals/${encodeURIComponent(signalId)}/ttl-check`);
    },

    async evaluateMarketIntelligence(payload: Record<string, unknown>) {
      return core.request<Record<string, unknown>>('/api/v1/institutional/market-intelligence/evaluate', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },

    async evaluateBreakout(payload: Record<string, unknown>) {
      return core.request<Record<string, unknown>>('/api/v1/institutional/breakout/evaluate', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },

    async getInstitutionalFeedHealth() {
      return core.request<{ feeds: Record<string, Record<string, unknown>>; detail: Record<string, unknown> }>(
        '/api/v1/institutional/feed/health',
      );
    },

    async getInstitutionalFeedHealthOne(instrumentId: string) {
      return core.request<Record<string, unknown>>(
        `/api/v1/institutional/feed/${encodeURIComponent(instrumentId)}/health`,
      );
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
    async validateContract(instrumentId: string, price: string, quantity: string) {
      const qs = new URLSearchParams({ instrument_id: instrumentId, price, quantity }).toString();
      return core.request<Record<string, unknown>>(`/api/v1/institutional/contract/validate?${qs}`, {
        method: 'POST',
      });
    },

    async computeExposure(instrumentId: string, price: string, quantity: string) {
      const qs = new URLSearchParams({ instrument_id: instrumentId, price, quantity }).toString();
      return core.request<Record<string, unknown>>(`/api/v1/institutional/decimal/exposure?${qs}`, {
        method: 'POST',
      });
    },
  };
}

export type InstitutionalApi = ReturnType<typeof createInstitutionalApi>;
