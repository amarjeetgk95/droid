// @vitest-environment happy-dom
import React, { useEffect } from 'react';
import { act, cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { supabaseMock, apiMock, authListeners, routerReplace } = vi.hoisted(() => {
  type AuthListener = (event: string, session: unknown) => void;
  const listeners: AuthListener[] = [];
  const supabase = {
    auth: {
      getSession: vi.fn(),
      onAuthStateChange: vi.fn((listener: AuthListener) => {
        listeners.push(listener);
        return { data: { subscription: { unsubscribe: vi.fn() } } };
      }),
      signInWithPassword: vi.fn(),
      signUp: vi.fn(),
      signOut: vi.fn(),
      resetPasswordForEmail: vi.fn(),
      updateUser: vi.fn(),
    },
  };
  const api = {
    setToken: vi.fn(),
    getToken: vi.fn(),
  };
  return { supabaseMock: supabase, apiMock: api, authListeners: listeners, routerReplace: vi.fn() };
});

vi.mock('@/lib/supabase', () => ({ supabase: supabaseMock }));
vi.mock('@/lib/api', () => ({ api: apiMock }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: routerReplace, push: vi.fn() }),
}));

import { AuthProvider, useAuth, type AuthContextType } from './AuthProvider';
import { readAuthNotice } from './authMessages';
import { deskCache } from '@/lib/useDeskCache';
import { setTestUrl } from './setTestUrl';

const APP_ORIGIN = 'http://localhost:3000';

let ctx: AuthContextType | null = null;

function ctxValue(): AuthContextType {
  if (!ctx) throw new Error('Auth context is not mounted');
  return ctx;
}

function Probe() {
  const auth = useAuth();
  // Publish for assertions once effects flush (assigning during render is
  // flagged by the react-hooks/globals rule).
  useEffect(() => {
    ctx = auth;
  });
  return <div data-testid="user-email">{auth.user?.email ?? 'anonymous'}</div>;
}

function renderAuthProvider() {
  ctx = null;
  return render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  );
}

async function waitForContext() {
  await waitFor(() => expect(ctx).not.toBeNull());
}

describe('AuthProvider session lifecycle', () => {
  beforeEach(() => {
    setTestUrl(`${APP_ORIGIN}/war-room`);
    localStorage.clear();
    sessionStorage.clear();
    authListeners.length = 0;
    deskCache.clear();

    supabaseMock.auth.getSession.mockReset().mockResolvedValue({ data: { session: null }, error: null });
    supabaseMock.auth.onAuthStateChange.mockClear();
    supabaseMock.auth.signInWithPassword.mockReset();
    supabaseMock.auth.signUp.mockReset();
    supabaseMock.auth.signOut.mockReset().mockResolvedValue({ error: null });
    supabaseMock.auth.resetPasswordForEmail.mockReset().mockResolvedValue({ data: {}, error: null });
    supabaseMock.auth.updateUser.mockReset().mockResolvedValue({ data: { user: null }, error: null });

    apiMock.setToken.mockReset();
    apiMock.getToken.mockReset();
    apiMock.getToken.mockReturnValue(null);
    routerReplace.mockReset();
  });

  afterEach(() => {
    cleanup();
    setTestUrl(`${APP_ORIGIN}/`);
  });

  it('signs in, stores the bearer token and maps failures to human copy', async () => {
    supabaseMock.auth.signInWithPassword.mockResolvedValue({
      data: {
        session: {
          access_token: 'tok-1',
          user: { id: 'u1', email: 'trader@droid.term', role: 'admin', last_sign_in_at: '2026-01-01T00:00:00Z' },
        },
      },
      error: null,
    });

    renderAuthProvider();
    await waitForContext();

    await act(async () => {
      await ctxValue().signIn('trader@droid.term', 'pw');
    });

    expect(apiMock.setToken).toHaveBeenCalledWith('tok-1');
    expect(ctxValue().user?.email).toBe('trader@droid.term');
    expect(ctxValue().isAuthenticated).toBe(true);

    supabaseMock.auth.signInWithPassword.mockRejectedValue(new Error('Failed to fetch'));
    await act(async () => {
      await expect(ctxValue().signIn('trader@droid.term', 'pw')).rejects.toThrow(
        /Cannot reach the authentication service/,
      );
    });
  });

  it('ends the local session and bounces to /login?reason=session_expired on a backend 401', async () => {
    renderAuthProvider();
    await waitForContext();
    apiMock.getToken.mockReturnValue('stale-token');

    act(() => {
      window.dispatchEvent(
        new CustomEvent('auth:unauthorized', { detail: { url: 'http://127.0.0.1:8000/api/v1/markets' } }),
      );
    });

    await waitFor(() => expect(supabaseMock.auth.signOut).toHaveBeenCalledWith({ scope: 'local' }));
    await waitFor(() => expect(routerReplace).toHaveBeenCalledTimes(1));

    const target = String(routerReplace.mock.calls[0][0]);
    expect(target).toContain('reason=session_expired');
    expect(target).toContain(encodeURIComponent('/war-room'));
    expect(apiMock.setToken).toHaveBeenCalledWith(null);
    expect(readAuthNotice()).toBe('session_expired');
  });

  it('does not react to 401s while already on /login (no redirect loop)', async () => {
    setTestUrl(`${APP_ORIGIN}/login`);
    renderAuthProvider();
    await waitForContext();
    apiMock.getToken.mockReturnValue('stale-token');

    act(() => {
      window.dispatchEvent(new CustomEvent('auth:unauthorized', { detail: { url: '/api/v1/x' } }));
    });
    await Promise.resolve();

    expect(supabaseMock.auth.signOut).not.toHaveBeenCalled();
    expect(routerReplace).not.toHaveBeenCalled();
    expect(window.location.pathname).toBe('/login');
  });

  it('does not react to 401s when no session token is loaded', async () => {
    renderAuthProvider();
    await waitForContext();
    apiMock.getToken.mockReturnValue(null);

    act(() => {
      window.dispatchEvent(new CustomEvent('auth:unauthorized', { detail: { url: '/api/v1/x' } }));
    });
    await Promise.resolve();

    expect(supabaseMock.auth.signOut).not.toHaveBeenCalled();
    expect(routerReplace).not.toHaveBeenCalled();
    expect(window.location.pathname).toBe('/war-room');
  });

  it('treats a broker-kind 401 as a gateway event, not a platform logout', async () => {
    renderAuthProvider();
    await waitForContext();
    apiMock.getToken.mockReturnValue('stale-token');
    const brokerExpired = vi.fn();
    window.addEventListener('broker:session-expired', brokerExpired);

    act(() => {
      window.dispatchEvent(
        new CustomEvent('auth:unauthorized', { detail: { url: '/api/v1/tokens/status', kind: 'broker' } }),
      );
    });
    await Promise.resolve();

    expect(brokerExpired).toHaveBeenCalledTimes(1);
    expect(supabaseMock.auth.signOut).not.toHaveBeenCalled();
    expect(routerReplace).not.toHaveBeenCalled();
    expect(window.location.pathname).toBe('/war-room');
    window.removeEventListener('broker:session-expired', brokerExpired);
  });

  it('sign-out revokes the provider session and clears token, desk cache and broker markers', async () => {
    renderAuthProvider();
    await waitForContext();

    deskCache.set('options:private', { v: 1 }, 60_000);
    localStorage.setItem('droid_last_auth_time', '123');
    localStorage.setItem('droid_last_auth_provider', 'fyers');

    await act(async () => {
      await ctxValue().signOut();
    });

    expect(supabaseMock.auth.signOut).toHaveBeenCalledTimes(1);
    expect(apiMock.setToken).toHaveBeenCalledWith(null);
    expect(deskCache.get('options:private')).toBeNull();
    expect(localStorage.getItem('droid_last_auth_time')).toBeNull();
    expect(localStorage.getItem('droid_last_auth_provider')).toBeNull();
    expect(ctxValue().user).toBeNull();
  });

  it('fails closed and reports visibly when the provider cannot revoke the session', async () => {
    supabaseMock.auth.signOut.mockResolvedValueOnce({ error: { message: 'network down' } });
    renderAuthProvider();
    await waitForContext();

    await act(async () => {
      await expect(ctxValue().signOut()).rejects.toThrow(/could not be reached/);
    });

    expect(supabaseMock.auth.signOut).toHaveBeenNthCalledWith(1);
    expect(supabaseMock.auth.signOut).toHaveBeenNthCalledWith(2, { scope: 'local' });
    expect(apiMock.setToken).toHaveBeenCalledWith(null);
    expect(ctxValue().user).toBeNull();
    expect(readAuthNotice()).toBe('logout_incomplete');
  });

  it('exposes PASSWORD_RECOVERY and clears it on demand', async () => {
    renderAuthProvider();
    await waitForContext();
    const listener = authListeners[0];
    expect(listener).toBeDefined();

    act(() => {
      listener('PASSWORD_RECOVERY', {
        access_token: 'recovery-token',
        user: { id: 'u1', email: 'trader@droid.term' },
      });
    });
    expect(ctxValue().isPasswordRecovery).toBe(true);

    supabaseMock.auth.updateUser.mockResolvedValue({
      data: { user: { id: 'u1', email: 'trader@droid.term', role: 'user' } },
      error: null,
    });
    await act(async () => {
      await ctxValue().updatePassword('new-secret');
    });
    expect(ctxValue().isPasswordRecovery).toBe(false);

    act(() => {
      ctxValue().clearPasswordRecovery();
    });
    expect(ctxValue().user).toBeNull();
    expect(apiMock.setToken).toHaveBeenCalledWith(null);
  });
});
