import { REDIRECT_BASE, DEFAULT_BACKEND_BASE } from '@/lib/settingsConstants';
import type { BrokerProviderId, ApiType } from '@/lib/settingsTypes';

export { REDIRECT_BASE, DEFAULT_BACKEND_BASE };

export const BACKEND_BASE = DEFAULT_BACKEND_BASE;
export const FYERS_LOGIN_URL = `${REDIRECT_BASE}/fyers/login`;
export const FLATTRADE_LOGIN_URL = `${REDIRECT_BASE}/flattrade/login`;

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
  if (provider === 'binance') {
    return { connected: true, label: 'CONNECTED', sub: 'Public WebSocket (Zero auth needed)', tone: 'emerald', hasCreds: true };
  }
  const tokenConnected = (tokenStatus as Record<string, unknown> | null)?.is_token_valid === true;
  const state = (tokenStatus as unknown as { state?: string })?.state;
  if (provider === 'fyers') {
    if (tokenConnected) return { connected: true, label: 'CONNECTED', sub: 'WebSocket • Live Stream Active', tone: 'emerald', hasCreds: true };
    return {
      connected: false,
      label: state === 'AUTH_EXPIRED' ? 'DAILY AUTH EXPIRED' : 'RENDER MANAGED — DAILY AUTH REQUIRED',
      sub: 'Click below to authorize your daily session',
      tone: state === 'AUTH_EXPIRED' ? 'red' : 'amber',
      hasCreds: true,
    };
  }
  if (provider === 'flattrade') {
    const hasToken = tokenConnected || Boolean((tokenStatus as unknown as { token?: string })?.token);
    // Also check flattradeCreds token via caller — simplified here
    if (hasToken) return { connected: true, label: 'CONNECTED', sub: 'PiConnect • Live Stream Active', tone: 'emerald', hasCreds: true };
    return {
      connected: false,
      label: state === 'AUTH_EXPIRED' ? 'DAILY AUTH EXPIRED' : 'RENDER MANAGED — DAILY AUTH REQUIRED',
      sub: 'Click below to authorize your daily session',
      tone: state === 'AUTH_EXPIRED' ? 'red' : 'amber',
      hasCreds: true,
    };
  }
  return { connected: false, label: 'UNKNOWN', sub: '', tone: 'red', hasCreds: false };
}
