'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { KeyRound, ShieldAlert, ShieldCheck } from 'lucide-react';
import { api, API_BASE } from '@/lib/api';
import { openBrokerAuth } from '@/lib/brokerAuth';
import { errorMessage } from '@/lib/errors';
import type { BrokerTokenStatus } from '@/lib/api/tokens';
import { useToast } from '@/components/ui/toast';
import { useCommandSection } from '@/context/AppStreamContext';

/**
 * Fyers broker auth pill for the shell header.
 *
 * Fyers access tokens die every trading day (no refresh token), so a daily
 * 1-click re-auth is mandatory. This control surfaces that state in the
 * header — no more Settings hunt — and opens the OAuth popup in place.
 *
 * State rides `GET /api/v1/tokens/status` (60s smart poll, paused when the
 * tab is hidden) plus the trusted `broker:authenticated` window event fired
 * by both the OAuth popup (`lib/brokerAuth.ts`) and the market-feed WS
 * (`hooks/useMarketStream.ts`).
 */
export function BrokerAuthControl() {
  const { push } = useToast();
  const [status, setStatus] = useState<BrokerTokenStatus | null>(null);
  const [authorizing, setAuthorizing] = useState(false);
  const cleanupRef = useRef<(() => void) | null>(null);

  const load = useCallback(async () => {
    try {
      const result = await api.getBrokerTokenStatus();
      setStatus(result.data ?? null);
    } catch {
      // Offline / backend down: keep last known state, pill shows unknown.
      setStatus((prev) => prev);
    }
  }, []);

  useEffect(() => {
    void load();
    const onAuthenticated = () => {
      setAuthorizing(false);
      void load();
      push('success', 'Fyers connected — live data resumed.');
    };
    window.addEventListener('broker:authenticated', onAuthenticated);
    return () => {
      window.removeEventListener('broker:authenticated', onAuthenticated);
      cleanupRef.current?.();
      cleanupRef.current = null;
    };
  }, [load, push]);

  // Stream-driven refresh: reacts when feed_health section increments version
  const feedSection = useCommandSection('feed_health');
  useEffect(() => {
    void load();
  }, [feedSection?.version, load]);

  const handleClick = useCallback(() => {
    if (authorizing) return;
    cleanupRef.current?.();
    setAuthorizing(true);
    const loginUrl = `${API_BASE.replace(/\/+$/, '')}/api/v1/tokens/fyers/login`;
    cleanupRef.current = openBrokerAuth({
      provider: 'fyers',
      loginUrl,
      onSuccess: () => {
        setAuthorizing(false);
        void load();
      },
      onError: (msg) => {
        setAuthorizing(false);
        push('error', msg);
      },
      onClose: () => {
        // Popup closed without success (cancelled) — re-check in case the
        // callback marker landed anyway, then release the button.
        setAuthorizing(false);
        void load();
      },
    });
  }, [authorizing, load, push]);

  const valid = status?.is_token_valid === true;
  const state = (status?.state ?? '').toUpperCase();
  const expired = !valid && (state === 'AUTH_EXPIRED' || state === 'DISCONNECTED' || status !== null);

  const badgeClass = !status ? 'b-warn' : valid ? 'b-bull' : 'b-bear';
  const label = authorizing
    ? 'FYERS AUTH…'
    : !status
      ? 'FYERS ?'
      : valid
        ? 'FYERS LIVE'
        : state === 'AUTH_EXPIRED'
          ? 'FYERS EXPIRED'
          : 'FYERS LOGIN';

  const title = !status
    ? 'Broker token state unknown — click to authorize Fyers (daily token expires every trading day)'
    : valid
      ? `Fyers connected · state ${status.state}${status.data_lag_seconds != null ? ` · lag ${status.data_lag_seconds}s` : ''} — click to re-authorize`
      : `Fyers needs daily re-auth (state ${status.state}${status.last_error ? ` — ${status.last_error}` : ''}) — click to authorize`;

  return (
    <button
      type="button"
      className={`badge ${badgeClass}`}
      title={title}
      disabled={authorizing}
      onClick={handleClick}
      aria-live="polite"
    >
      {valid && !authorizing ? <ShieldCheck size={12} /> : expired && !authorizing ? <ShieldAlert size={12} /> : <KeyRound size={12} />}
      {label}
    </button>
  );
}
