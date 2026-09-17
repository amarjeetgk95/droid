import type { ApiCore } from './client';

export interface AlgoHealthResponse {
  data: {
    status: string;
    components: Record<string, { status: string; [key: string]: unknown }>;
    thresholds?: Record<string, string>;
    timestamp: string;
  };
}

export interface AlgoAccountResponse {
  data: {
    account_id: string;
    user_id?: string;
    mode: 'OFF' | 'PAPER' | 'LIVE';
    is_active?: boolean;
    capital?: { investment_limit: string; max_capital_per_trade: string; max_daily_loss: string } | null;
    kill_switch?: { is_killed: boolean; kill_level: string } | null;
    consent_ok?: boolean;
    disclosure_version?: string;
  };
}

export interface AlgoConsentResponse {
  data: {
    disclosure: {
      version: string;
      content: string;
      requires_acknowledgement: boolean;
      pre_checked: boolean;
    };
    consents: Array<{ version: string; acknowledged_at: string | null; is_revoked: boolean }>;
    current_ok?: boolean;
  };
}

export interface AlgoCapitalConfig {
  investment_limit?: number;
  max_capital_per_trade?: number;
  max_daily_loss?: number;
  max_loss_per_trade?: number;
  max_open_positions?: number;
  max_trades_per_day?: number;
  max_position_quantity?: number;
  max_slippage_pct?: number;
  max_spread_pct?: number;
  portfolio_gross_exposure_limit?: number;
  portfolio_net_exposure_limit?: number;
  portfolio_margin_limit_pct?: number;
  portfolio_var_limit?: number;
  portfolio_stress_limit?: number;
  portfolio_delta_limit?: number;
  portfolio_gamma_limit?: number;
  portfolio_vega_limit?: number;
  underlying_concentration_pct?: number;
  strategy_concentration_pct?: number;
  expiry_concentration_pct?: number;
  confirm?: boolean;
}

export interface AlgoOrder {
  order_id?: string;
  client_order_id: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  quantity: number;
  price?: number;
  order_type?: string;
  product?: string;
  status?: string;
  filled_quantity?: number;
  average_price?: number;
  created_at?: string;
  updated_at?: string;
}

export interface AlgoPosition {
  position_id: string;
  symbol: string;
  quantity: number;
  average_price: number;
  current_price?: number;
  unrealized_pnl?: number;
  realized_pnl?: number;
  side?: string;
  product?: string;
  updated_at?: string;
}

export interface AlgoStrategy {
  strategy_id: string;
  name: string;
  description?: string;
  parameters?: Record<string, unknown>;
  weights?: Record<string, unknown>;
  ai_mode?: string;
  is_active?: boolean;
}

export interface AlgoKillSwitchStatus {
  is_killed: boolean;
  kill_level: string;
  killed_at?: string;
  reason?: string;
}

export function createAlgoApi(core: ApiCore) {
  return {
    // Health & Observability
    getAlgoHealth: () => core.request<AlgoHealthResponse>('/api/v1/algo/health'),
    getAlgoObservabilityMetrics: () => core.request<{ data: Record<string, unknown> }>('/api/v1/algo/observability/metrics'),
    getAlgoSloDashboard: () => core.request<{ data: Record<string, unknown> }>('/api/v1/algo/slo-dashboard'),
    getBrokerCapabilities: () => core.request<{ data: Record<string, unknown> }>('/api/v1/algo/broker-capabilities'),

    // Account & Modes
    getAlgoAccount: () => core.request<AlgoAccountResponse>('/api/v1/algo/account'),
    setAlgoMode: (mode: 'OFF' | 'PAPER' | 'LIVE') =>
      core.request<{ data: { mode: string; status: string } }>('/api/v1/algo/account/mode', {
        method: 'POST',
        body: JSON.stringify({ mode }),
      }),

    // Consent & Risk Disclosure
    getAlgoConsent: () => core.request<AlgoConsentResponse>('/api/v1/algo/consent'),
    acknowledgeAlgoConsent: (disclosure_version: string, acknowledged: boolean) =>
      core.request<{ data: { acknowledged: boolean; version: string; timestamp?: string } }>('/api/v1/algo/consent', {
        method: 'POST',
        body: JSON.stringify({ disclosure_version, acknowledged }),
      }),
    revokeAlgoConsent: () => core.request<{ data: { revoked: boolean; note?: string } }>('/api/v1/algo/consent', { method: 'DELETE' }),

    // Capital & Limits
    getAlgoCapital: () => core.request<{
      data: {
        limit: string;
        deployed: string;
        reserved?: string;
        reserved_pending?: string;
        available: string;
        utilization_pct: string;
        config: AlgoCapitalConfig;
      };
    }>('/api/v1/algo/capital'),
    updateAlgoCapital: (config: AlgoCapitalConfig) =>
      core.request<{
        data: {
          updated?: boolean;
          reason?: string;
          account_id?: string;
          config?: Partial<Record<keyof AlgoCapitalConfig, string>>;
          limit_exceeded?: string | null;
        };
      }>('/api/v1/algo/capital', {
        method: 'PATCH',
        body: JSON.stringify(config),
      }),
    getAlgoExposure: () => core.request<{ data: Record<string, unknown> }>('/api/v1/algo/exposure'),

    // Strategies
    getAlgoStrategies: () => core.request<{ data: AlgoStrategy[] }>('/api/v1/algo/strategies'),
    createOrUpdateAlgoStrategy: (strategy: AlgoStrategy) =>
      core.request<{ data: AlgoStrategy }>('/api/v1/algo/strategies', {
        method: 'POST',
        body: JSON.stringify(strategy),
      }),
    promoteAlgoStrategy: (strategy_id: string, stage: string) =>
      core.request<{ data: Record<string, unknown> }>(`/api/v1/algo/strategies/${strategy_id}/promote`, {
        method: 'POST',
        body: JSON.stringify({ stage }),
      }),

    // Orders & Baskets
    getAlgoOrders: () => core.request<{ data: AlgoOrder[] }>('/api/v1/algo/orders'),
    createAlgoOrder: (order: Partial<AlgoOrder>) =>
      core.request<{ data: AlgoOrder }>('/api/v1/algo/orders', {
        method: 'POST',
        body: JSON.stringify(order),
      }),
    cancelAlgoOrder: (client_order_id: string) =>
      core.request<{ data: { cancelled: boolean } }>(`/api/v1/algo/orders/${client_order_id}/cancel`, {
        method: 'POST',
      }),
    reconcileAlgoOrder: (client_order_id: string) =>
      core.request<{ data: Record<string, unknown> }>(`/api/v1/algo/orders/${client_order_id}/reconcile`, {
        method: 'POST',
      }),
    createAlgoBasket: (basket: { orders: Partial<AlgoOrder>[]; execution_mode?: string; leg_risk_policy?: string }) =>
      core.request<{ data: Record<string, unknown> }>('/api/v1/algo/basket', {
        method: 'POST',
        body: JSON.stringify(basket),
      }),

    // Positions & Exits
    getAlgoPositions: () => core.request<{ data: AlgoPosition[] }>('/api/v1/algo/positions'),
    exitAlgoPosition: (position_id: string) =>
      core.request<{ data: { closed: boolean } }>(`/api/v1/algo/positions/${position_id}/exit`, {
        method: 'POST',
      }),
    exitAllAlgoPositions: () =>
      core.request<{ data: { closed_count: number } }>('/api/v1/algo/positions/exit-all', {
        method: 'POST',
      }),

    // Kill Switch
    getAlgoKillSwitch: () => core.request<{ data: AlgoKillSwitchStatus }>('/api/v1/algo/kill-switch'),
    triggerAlgoKillSwitch: (kill_level = 'FULL_EXECUTION_STOP', reason?: string) =>
      core.request<{ data: AlgoKillSwitchStatus }>('/api/v1/algo/kill-switch', {
        method: 'POST',
        body: JSON.stringify({ kill_level, reason }),
      }),

    // AI Governance & Drift
    getAlgoAiModels: () => core.request<{ data: Record<string, unknown>[] }>('/api/v1/algo/ai-models'),
    registerAlgoAiModel: (model: Record<string, unknown>) =>
      core.request<{ data: Record<string, unknown> }>('/api/v1/algo/ai/models', {
        method: 'POST',
        body: JSON.stringify(model),
      }),
    canaryAlgoAiModel: (key: string, canary_percentage: number) =>
      core.request<{ data: Record<string, unknown> }>(`/api/v1/algo/ai/models/${key}/canary`, {
        method: 'POST',
        body: JSON.stringify({ canary_percentage }),
      }),
    rollbackAlgoAiModel: (key: string) =>
      core.request<{ data: Record<string, unknown> }>(`/api/v1/algo/ai/models/${key}/rollback`, {
        method: 'POST',
      }),
    getAlgoAiDrift: () => core.request<{ data: Record<string, unknown> }>('/api/v1/algo/ai/drift'),

    // Options Selection & Sizing
    previewAlgoSizing: (payload: { symbol: string; risk_amount?: number; stop_distance?: number }) =>
      core.request<{ data: Record<string, unknown> }>('/api/v1/algo/sizing/preview', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    selectAlgoOptions: (payload: { direction: string; candidates: Record<string, unknown>[] }) =>
      core.request<{ data: Record<string, unknown> }>('/api/v1/algo/options/select', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),

    // Reconciliation & Audit
    runAlgoReconciliation: () =>
      core.request<{ data: Record<string, unknown> }>('/api/v1/algo/reconciliation/run', {
        method: 'POST',
      }),
    restartAlgoRecovery: () =>
      core.request<{ data: Record<string, unknown> }>('/api/v1/algo/recovery/restart', {
        method: 'POST',
      }),
    getAlgoAudit: (limit = 50) => core.request<{ data: Record<string, unknown>[] }>(`/api/v1/algo/audit?limit=${limit}`),
  };
}

export type AlgoApi = ReturnType<typeof createAlgoApi>;
