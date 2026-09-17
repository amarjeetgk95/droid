// @vitest-environment happy-dom
import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { authState, routerReplace, routerPush, searchParamsRef } = vi.hoisted(() => ({
  authState: {
    user: null as { id: string; email: string | null } | null,
    loading: false,
    isAuthenticated: false,
    isDemoMode: false,
    isPasswordRecovery: false,
    signIn: vi.fn(),
    sendPasswordReset: vi.fn(),
    updatePassword: vi.fn(),
    clearPasswordRecovery: vi.fn(),
  },
  routerReplace: vi.fn(),
  routerPush: vi.fn(),
  searchParamsRef: { current: new URLSearchParams() },
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: routerReplace, push: routerPush }),
  useSearchParams: () => searchParamsRef.current,
}));

vi.mock('@/components/auth/AuthProvider', () => ({ useAuth: () => authState }));

import LoginPage from '@/app/login/page';
import { setTestUrl } from './setTestUrl';

function fillCredentials(email = 'trader@droid.term', password = 'correct horse') {
  fireEvent.change(screen.getByLabelText('User ID / Email'), { target: { value: email } });
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: password } });
}

describe('LoginPage', () => {
  beforeEach(() => {
    authState.user = null;
    authState.loading = false;
    authState.isAuthenticated = false;
    authState.isDemoMode = false;
    authState.isPasswordRecovery = false;
    authState.signIn.mockReset().mockResolvedValue(undefined);
    authState.sendPasswordReset.mockReset().mockResolvedValue(undefined);
    authState.updatePassword.mockReset().mockResolvedValue(undefined);
    authState.clearPasswordRecovery.mockReset();
    routerReplace.mockReset();
    routerPush.mockReset();
    searchParamsRef.current = new URLSearchParams();
    sessionStorage.clear();
    setTestUrl('http://localhost:3000/login');
  });

  afterEach(() => cleanup());

  it('associates labels with inputs and exposes a focusable password toggle', () => {
    render(<LoginPage />);

    expect(screen.getByLabelText('User ID / Email')).toBeTruthy();
    expect(screen.getByLabelText('Password')).toBeTruthy();

    const toggle = screen.getByRole('button', { name: 'Show password' });
    expect(toggle.getAttribute('tabindex')).toBeNull();

    fireEvent.click(toggle);
    expect(screen.getByRole('button', { name: 'Hide password' })).toBeTruthy();
  });

  it('announces validation failures in an alert region', async () => {
    render(<LoginPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Log in' }));

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('Please enter your Email');
  });

  it.each([
    ['https://evil.example/phish', '/'],
    ['//evil.example', '/'],
    ['/\\evil.example', '/'],
    ['javascript:alert(1)', '/'],
    ['/login?returnUrl=/login', '/'],
    ['/markets?symbol=NIFTY#depth', '/markets?symbol=NIFTY#depth'],
  ])('sanitizes returnUrl %s -> %s and redirects once via replace', async (requested, expected) => {
    searchParamsRef.current = new URLSearchParams({ returnUrl: requested });
    authState.isAuthenticated = true;
    authState.user = { id: 'u1', email: 'trader@droid.term' };

    render(<LoginPage />);

    await waitFor(() => expect(routerReplace).toHaveBeenCalledWith(expected));
    expect(routerPush).not.toHaveBeenCalled();
  });

  it('does not navigate on submit — the authenticated effect is the single path', async () => {
    render(<LoginPage />);
    fillCredentials();
    fireEvent.click(screen.getByRole('button', { name: 'Log in' }));

    await waitFor(() => expect(authState.signIn).toHaveBeenCalledWith('trader@droid.term', 'correct horse'));
    expect(routerPush).not.toHaveBeenCalled();
    expect(routerReplace).not.toHaveBeenCalled();
  });

  it('maps raw provider failures to human copy instead of surfacing them verbatim', async () => {
    authState.signIn.mockRejectedValue(new Error('Failed to fetch'));
    render(<LoginPage />);
    fillCredentials();
    fireEvent.click(screen.getByRole('button', { name: 'Log in' }));

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toMatch(/Cannot reach the authentication service/);
    expect(alert.textContent).not.toMatch(/Failed to fetch/);
  });

  it('shows the session-expired notice from the redirect reason', () => {
    searchParamsRef.current = new URLSearchParams({ reason: 'session_expired' });
    render(<LoginPage />);
    expect(screen.getByText(/session expired or was revoked/i)).toBeTruthy();
  });

  it('offers a password-reset path and confirms the send without confirming account existence', async () => {
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText('User ID / Email'), { target: { value: 'trader@droid.term' } });
    fireEvent.click(screen.getByRole('button', { name: 'Forgot password?' }));

    expect(screen.getByLabelText('Account Email')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Send reset link' }));

    await waitFor(() => expect(authState.sendPasswordReset).toHaveBeenCalledWith('trader@droid.term'));
    expect(await screen.findByText(/password-reset link is on its way/i)).toBeTruthy();
  });

  it('renders the recovery form for a recovery session and validates both fields', async () => {
    authState.isPasswordRecovery = true;
    authState.isAuthenticated = true;
    authState.user = { id: 'u1', email: 'trader@droid.term' };

    render(<LoginPage />);
    expect(screen.getByLabelText('New password')).toBeTruthy();

    fireEvent.change(screen.getByLabelText('New password'), { target: { value: 'abcdef' } });
    fireEvent.change(screen.getByLabelText('Confirm new password'), { target: { value: 'abcdeg' } });
    fireEvent.click(screen.getByRole('button', { name: 'Set new password' }));

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('do not match');
    expect(authState.updatePassword).not.toHaveBeenCalled();
    // A recovery session must never auto-redirect away from the reset form.
    expect(routerReplace).not.toHaveBeenCalled();
  });

  it('detects a recovery link in the URL hash even before the auth event arrives', () => {
    setTestUrl('http://localhost:3000/login#access_token=abc&type=recovery');

    render(<LoginPage />);

    expect(screen.getByLabelText('New password')).toBeTruthy();
    expect(routerReplace).not.toHaveBeenCalled();
  });

  it('explains missing configuration in demo mode and disables sign-in', () => {
    authState.isDemoMode = true;

    render(<LoginPage />);

    expect(screen.getByText(/Authentication is not configured \(demo mode\)/)).toBeTruthy();
    expect((screen.getByRole('button', { name: 'Log in' }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByLabelText('User ID / Email') as HTMLInputElement).disabled).toBe(true);
  });
});
