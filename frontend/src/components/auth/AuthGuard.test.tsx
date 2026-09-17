// @vitest-environment happy-dom
import React from 'react';
import { cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { authState, routerReplace } = vi.hoisted(() => ({
  authState: {
    user: null as { id: string; email: string | null } | null,
    loading: false,
    isAuthenticated: false,
  },
  routerReplace: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    replace: routerReplace,
    push: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
  usePathname: () => '/markets',
}));

vi.mock('./AuthProvider', () => ({ useAuth: () => authState }));

import { AuthGuard } from './AuthGuard';
import { setTestUrl } from './setTestUrl';

describe('AuthGuard', () => {
  beforeEach(() => {
    authState.user = null;
    authState.loading = false;
    authState.isAuthenticated = false;
    routerReplace.mockReset();
    setTestUrl('http://localhost:3000/markets?symbol=NIFTY#depth');
  });

  afterEach(() => {
    cleanup();
  });

  it('preserves path, query and hash in the returnUrl', async () => {
    render(
      <AuthGuard>
        <div>secret desk</div>
      </AuthGuard>,
    );

    await waitFor(() =>
      expect(routerReplace).toHaveBeenCalledWith(
        `/login?returnUrl=${encodeURIComponent('/markets?symbol=NIFTY#depth')}`,
      ),
    );
  });

  it('renders children when authenticated without redirecting', () => {
    authState.user = { id: 'u1', email: 'trader@droid.term' };
    authState.isAuthenticated = true;

    const { getByText } = render(
      <AuthGuard>
        <div>secret desk</div>
      </AuthGuard>,
    );

    expect(getByText('secret desk')).toBeTruthy();
    expect(routerReplace).not.toHaveBeenCalled();
  });

  it('shows the verification state while loading and never redirects early', () => {
    authState.loading = true;

    const { getByText } = render(
      <AuthGuard>
        <div>secret desk</div>
      </AuthGuard>,
    );

    expect(getByText(/Verifying credentials/)).toBeTruthy();
    expect(routerReplace).not.toHaveBeenCalled();
  });
});
