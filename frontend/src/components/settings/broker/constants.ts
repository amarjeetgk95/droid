import { REDIRECT_BASE, DEFAULT_BACKEND_BASE } from '@/lib/settingsConstants';
import type { BrokerProviderId, ApiType } from '@/lib/settingsTypes';

export { REDIRECT_BASE, DEFAULT_BACKEND_BASE };

export const BACKEND_BASE = DEFAULT_BACKEND_BASE;
export const FYERS_LOGIN_URL = `${DEFAULT_BACKEND_BASE}/api/v1/tokens/fyers/login`;
export const FYERS_REDIRECT_URI = `${DEFAULT_BACKEND_BASE}/api/v1/tokens/fyers/callback`;


export type ProviderMeta = {
  connected: boolean;
  label: string;
  sub: string;
  tone: 'emerald' | 'amber' | 'red';
  hasCreds: boolean;
};

export function getProviderMeta(
  provider: BrokerProviderId,
  apiType: ApiType,
  tokenStatus: Record<string, unknown> | null
): ProviderMeta {
  const tokenConnected = (tokenStatus as Record<string, unknown> | null)?.is_token_valid === true;
  const state = (tokenStatus as unknown as { state?: string })?.state;
  if (provider === 'fyers') {
    if (tokenConnected) return { connected: true, label: 'CONNECTED', sub: 'WebSocket • Live Stream Active', tone: 'emerald', hasCreds: true };
    return {
      connected: false,
      label: state === 'AUTH_EXPIRED' ? 'DAILY AUTH EXPIRED' : 'LOCAL BACKEND — DAILY AUTH REQUIRED',
      sub: 'Click below to authorize your daily session',
      tone: state === 'AUTH_EXPIRED' ? 'red' : 'amber',
      hasCreds: true,
    };
  }
  return { connected: false, label: 'UNKNOWN', sub: '', tone: 'red', hasCreds: false };
}
