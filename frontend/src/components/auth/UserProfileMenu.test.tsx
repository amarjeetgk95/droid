// @vitest-environment happy-dom
import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { authState, routerReplace } = vi.hoisted(() => ({
  authState: {
    user: { id: 'u1', email: 'desk@droid.term', role: 'admin' } as {
      id: string;
      email: string | null;
      role?: string;
    } | null,
    signOut: vi.fn(),
    isConfigured: true,
  },
  routerReplace: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: routerReplace, push: vi.fn() }),
}));

vi.mock('./AuthProvider', () => ({ useAuth: () => authState }));

vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuItem: ({
    children,
    onClick,
    disabled,
  }: {
    children: React.ReactNode;
    onClick?: () => void;
    disabled?: boolean;
  }) => (
    <button type="button" onClick={onClick} disabled={disabled}>
      {children}
    </button>
  ),
  DropdownMenuLabel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuSeparator: () => <hr />,
}));

vi.mock('@/components/ui/ConfirmDialog', () => ({
  ConfirmDialog: ({
    open,
    onConfirm,
    confirmLabel,
    busy,
  }: {
    open: boolean;
    onConfirm: () => void;
    confirmLabel?: string;
    busy?: boolean;
  }) =>
    open ? (
      <button type="button" onClick={onConfirm} disabled={busy}>
        {confirmLabel ?? 'Confirm'}
      </button>
    ) : null,
}));

import { UserProfileMenu } from './UserProfileMenu';

describe('UserProfileMenu', () => {
  beforeEach(() => {
    authState.user = { id: 'u1', email: 'desk@droid.term', role: 'admin' };
    authState.isConfigured = true;
    authState.signOut.mockReset().mockResolvedValue(undefined);
    routerReplace.mockReset();
  });

  afterEach(() => cleanup());

  it('shows the real identity and requires confirmation before signing out', async () => {
    render(<UserProfileMenu />);

    expect(screen.getAllByText('desk@droid.term').length).toBeGreaterThan(0);
    expect(screen.getByText('ADMIN')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: /Log Out/ }));
    expect(authState.signOut).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }));
    await waitFor(() => expect(authState.signOut).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(routerReplace).toHaveBeenCalledWith('/login'));
  });

  it('surfaces a sign-out failure instead of failing silently', async () => {
    authState.signOut.mockRejectedValue(new Error('Failed to fetch'));
    render(<UserProfileMenu />);

    fireEvent.click(screen.getByRole('button', { name: /Log Out/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }));

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toMatch(/Cannot reach the authentication service/);
    expect(routerReplace).not.toHaveBeenCalled();
  });

  it('disables the confirmation while sign-out is pending', async () => {
    let resolveSignOut: () => void = () => {};
    authState.signOut.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolveSignOut = resolve;
        }),
    );
    render(<UserProfileMenu />);

    fireEvent.click(screen.getByRole('button', { name: /Log Out/ }));
    const confirm = screen.getByRole('button', { name: 'Sign out' }) as HTMLButtonElement;
    fireEvent.click(confirm);

    await waitFor(() => expect(confirm.disabled).toBe(true));
    resolveSignOut();
    await waitFor(() => expect(routerReplace).toHaveBeenCalledWith('/login'));
  });

  it('renders and signs out safely when Supabase env is missing', async () => {
    authState.user = null;
    authState.isConfigured = false;

    render(<UserProfileMenu />);
    expect(screen.getAllByText('Authentication not configured').length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('button', { name: /Log Out/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }));

    await waitFor(() => expect(authState.signOut).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(routerReplace).toHaveBeenCalledWith('/login'));
  });
});
