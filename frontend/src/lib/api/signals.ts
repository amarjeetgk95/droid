import type { ApiCore } from './client';

export function createSignalsApi(core: ApiCore) {
  return {
    async autoDetectSignal(payload: { underlying: string; strategy?: string; timeframe?: string }) {
    return core.request<{ detected: boolean; candidate: any; message: string }>(`/api/v1/signals/auto-detect`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

    async bulkDeleteSignals(payload: {
    signal_ids?: string[];
    before_ms?: number;
    underlying?: string;
    strategy?: string;
    status?: string;
    delete_all?: boolean;
    confirm_all?: boolean;
  }) {
    return core.request<{ status: string; message: string; deleted_count: number; deleted_ids: string[]; requested_count: number }>(
      `/api/v1/signals/bulk-delete`,
      { method: 'POST', body: JSON.stringify(payload) },
    );
  },

    async deleteSignal(signalId: string) {
    return core.request<{ status: string; message: string; fsm_deleted: boolean; audit_deleted: boolean }>(
      `/api/v1/signals/${encodeURIComponent(signalId)}`,
      { method: 'DELETE' },
    );
  },

    async executeSignalPaper(signalId: string, lots?: number, riskPercent?: number) {
    return core.request<{ success: boolean; signal_id: string; quantity: number; lots: number; fill_price: number; order_id: string; message: string }>(
      `/api/v1/signals/${encodeURIComponent(signalId)}/execute-paper`,
      {
        method: 'POST',
        body: JSON.stringify({ lots, risk_percent: riskPercent }),
      },
    );
  },

    async generateSignal(payload: Record<string, any>) {
    return core.request<{ success: boolean; signal: any; paper_order: any; telegram: { enqueued: number } }>(
      `/api/v1/signals/generate`,
      { method: 'POST', body: JSON.stringify(payload) },
    );
  },

    async getSignal(signalId: string) {
    return core.request<any>(`/api/v1/signals/${encodeURIComponent(signalId)}`);
  },

    async getSignalDeepDive(signalId: string) {
    return core.request<any>(`/api/v1/signals/${encodeURIComponent(signalId)}/deep-dive`);
  },

    async getSingleSignalAudit(signalId: string) {
    return core.request<any>(`/api/v1/signals/${encodeURIComponent(signalId)}/audit`);
  },

    async getSignalEngines() {
    return core.request<{ approved_universe: string[]; broker: string; strategies: any[] }>(`/api/v1/signals/engines`);
  },

    async getSignalsActive(params?: { instrument?: string; status?: string; strategy?: string; desk?: string; is_scalp?: boolean }) {
    const qs = new URLSearchParams();
    if (params?.instrument) qs.set('instrument', params.instrument);
    if (params?.status) qs.set('status', params.status);
    if (params?.strategy) qs.set('strategy', params.strategy);
    if (params?.desk) qs.set('desk', params.desk);
    if (params?.is_scalp !== undefined) qs.set('is_scalp', String(params.is_scalp));
    const q = qs.toString() ? `?${qs.toString()}` : '';
    return core.request<{ signals: any[]; count: number; timestamp_ms: number }>(`/api/v1/signals/active${q}`);
  },

    async getSignalsAudit(params?: { underlying?: string; strategy?: string; status?: string; limit?: number }) {
    const qs = new URLSearchParams();
    if (params?.underlying) qs.set('underlying', params.underlying);
    if (params?.strategy) qs.set('strategy', params.strategy);
    if (params?.status) qs.set('status', params.status);
    if (params?.limit) qs.set('limit', String(params.limit));
    const q = qs.toString() ? `?${qs.toString()}` : '';
    return core.request<{ trades: any[]; count: number; summary: any; timestamp_ms: number }>(`/api/v1/signals/audit${q}`);
  },

    async getSignalsHistory(limit = 20) {
    return core.request<{ records: any[] }>(`/api/v1/signals/history?limit=${limit}`);
  },

    async getSignalsPerformance() {
    return core.request<{
      total_signals: number;
      active_signals: number;
      completed_signals: number;
      winning_signals: number;
      losing_signals: number;
      win_rate_pct: number;
      profit_factor: number;
      average_rr: number;
      expectancy_r: number;
      target_1_hits: number;
      target_2_hits: number;
      stop_loss_hits: number;
      strategy_breakdown: Record<string, any>;
      underlying_breakdown: Record<string, any>;
    }>(`/api/v1/signals/performance`);
  },

    async getSignalsScanner(desk?: string) {
    const qs = desk ? `?desk=${desk}` : '';
    return core.request<{ scanned_underlyings: string[]; total_candidates: number; new_signals: any[]; active_signals: any[]; timestamp_ms: number }>(
      `/api/v1/signals/scanner${qs}`
    );
  },

    async getSignalsStatus() {
    return core.request<{
      active_count: number;
      confirmed_count: number;
      armed_count: number;
      diagnostics: Record<string, unknown>;
      timestamp_ms: number;
    }>(`/api/v1/signals/status`);
  },

    async previewSignal(payload: Record<string, any>) {
    return core.request<{ preview: string; event: any; event_type: string; instrument: string }>(`/api/v1/signals/preview`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

    async setPaperWalletCapital(capital: number) {
    return core.request<{ status: string; data: any; capital: number; available_margin: number }>(
      `/api/v1/signals/paper-wallet`,
      {
        method: 'POST',
        body: JSON.stringify({ capital }),
      },
    );
  },
  };
}

export type SignalsApi = ReturnType<typeof createSignalsApi>;
