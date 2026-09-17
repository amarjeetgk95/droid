import type { ApiCore } from './client';

export interface BrokerTokenStatus {
  provider: string;
  state: string;
  is_token_valid: boolean;
  connection_started_at: string | null;
  uptime_seconds: number | null;
  last_message_at: string | null;
  last_heartbeat_at: string | null;
  data_lag_seconds: number | null;
  reconnect_count: number;
  subscription_count: number;
  last_error: string | null;
}

export interface BrokerTokenDiagnostics {
  provider: string;
  refreshed: boolean;
  diagnostics: Record<string, unknown>;
}

export interface BrokerTokenRefresh {
  refreshed: boolean;
  provider: string;
  has_token: boolean;
  auth_method?: string;
  state?: string | null;
}

export function createTokensApi(core: ApiCore) {
  return {
    getBrokerTokenStatus: () =>
      core.request<{ data: BrokerTokenStatus; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/tokens/status'),

    refreshBrokerToken: () =>
      core.request<{ data: BrokerTokenRefresh; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/tokens/refresh', {
        method: 'POST',
      }),

    runTokenDiagnostics: () =>
      core.request<{ data: BrokerTokenDiagnostics; error: string | null; meta: import('../types').ApiMeta }>('/api/v1/tokens/diagnostics', {
        method: 'POST',
      }),
  };
}

export type TokensApi = ReturnType<typeof createTokensApi>;
