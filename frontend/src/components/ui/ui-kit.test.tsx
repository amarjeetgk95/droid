// @vitest-environment happy-dom
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Modal } from '@/components/ui/modal';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';

afterEach(() => cleanup());

describe('Card (unified compound + prop API)', () => {
  it('renders the compound API', () => {
    render(
      <Card data-testid="compound">
        <CardHeader>
          <CardTitle>Compound title</CardTitle>
        </CardHeader>
        <CardContent>Compound body</CardContent>
      </Card>,
    );

    expect(screen.getByText('Compound title')).toBeTruthy();
    expect(screen.getByText('Compound body')).toBeTruthy();
    expect(screen.getByTestId('compound').getAttribute('data-slot')).toBe('card');
  });

  it('renders the legacy prop API with header, footer and glow tone', () => {
    const { container } = render(
      <Card
        title="Panel"
        subtitle="Legacy subtitle"
        headerAction={<button type="button">Action</button>}
        footer="footer copy"
        glow="emerald"
      >
        body copy
      </Card>,
    );

    expect(screen.getByText('Panel')).toBeTruthy();
    expect(screen.getByText('Legacy subtitle')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Action' })).toBeTruthy();
    expect(screen.getByText('footer copy')).toBeTruthy();
    expect(container.firstElementChild!.className).toContain('border-up-line');
  });
});

describe('Badge (unified variants)', () => {
  it('renders legacy variants, sizes and the dot indicator', () => {
    const { container } = render(
      <Badge variant="bull" size="xs" dot>
        LONG
      </Badge>,
    );

    const badge = container.querySelector('[data-slot="badge"]')!;
    expect(badge.className).toContain('bg-up-wash');
    expect(badge.className).toContain('text-[10px]');
    expect(badge.querySelector('.animate-pulse')).toBeTruthy();
  });

  it('keeps the radix aliases and asChild contract', () => {
    render(
      <Badge asChild variant="destructive">
        <a href="/desk">danger link</a>
      </Badge>,
    );

    const link = screen.getByRole('link', { name: 'danger link' });
    expect(link.className).toContain('bg-down-wash');
  });
});

describe('Modal (radix-backed legacy adapter)', () => {
  it('focuses the [data-autofocus] target and closes on Escape', async () => {
    const onClose = vi.fn();
    render(
      <Modal isOpen onClose={onClose} title="AI thesis" footer={<button type="button">Done</button>}>
        <input data-autofocus />
      </Modal>,
    );

    const input = screen.getByRole('textbox');
    await waitFor(() => expect(document.activeElement).toBe(input));

    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it('does not dismiss while closeDisabled', async () => {
    const onClose = vi.fn();
    render(
      <Modal isOpen onClose={onClose} title="Exit position" closeDisabled>
        body
      </Modal>,
    );

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();
    expect((screen.getByRole('button', { name: 'Close dialog' }) as HTMLButtonElement).disabled).toBe(
      true,
    );
  });
});

describe('ConfirmDialog legacy API (typed confirmation + inline error)', () => {
  it('gates on the typed phrase and closes itself after an async confirm', async () => {
    const onClose = vi.fn();
    const onConfirm = vi.fn(async () => undefined);
    render(
      <ConfirmDialog
        isOpen
        onClose={onClose}
        onConfirm={onConfirm}
        title="CRITICAL EXECUTION HALT"
        message={<p>Stops every engine.</p>}
        destructive
        requireTypedConfirmation="KILL"
      />,
    );

    const confirm = screen.getByRole('button', { name: 'Confirm' }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);

    fireEvent.change(document.getElementById('confirm-typed-input')!, { target: { value: 'kill' } });
    expect(confirm.disabled).toBe(false);

    fireEvent.click(confirm);
    await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it('surfaces an async failure inline and keeps the dialog open', async () => {
    const onClose = vi.fn();
    const onConfirm = vi.fn().mockRejectedValue(new Error('backend refused the halt'));
    render(
      <ConfirmDialog
        isOpen
        onClose={onClose}
        onConfirm={onConfirm}
        title="CRITICAL EXECUTION HALT"
        message="Stops every engine."
        destructive
        requireTypedConfirmation="KILL"
      />,
    );

    fireEvent.change(document.getElementById('confirm-typed-input')!, { target: { value: 'KILL' } });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('backend refused the halt');
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe('ConfirmDialog controlled API (busy guard + intent rows)', () => {
  it('blocks dismissal and disables both actions while busy', () => {
    const onOpenChange = vi.fn();
    const onConfirm = vi.fn();
    render(
      <ConfirmDialog
        open
        onOpenChange={onOpenChange}
        title="Square off paper position?"
        description="Simulated only."
        intentRows={[{ label: 'Qty', value: '50' }]}
        confirmLabel="Square off"
        busy
        onConfirm={onConfirm}
      />,
    );

    expect(screen.getByText('Qty')).toBeTruthy();
    expect(screen.getByText('50')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onOpenChange).not.toHaveBeenCalled();
    expect(
      (screen.getByRole('button', { name: 'Working…' }) as HTMLButtonElement).disabled,
    ).toBe(true);

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onOpenChange).not.toHaveBeenCalled();
  });

  it('lets a non-busy cancel request close without auto-closing on confirm', async () => {
    const onOpenChange = vi.fn();
    const onConfirm = vi.fn(async () => undefined);
    render(
      <ConfirmDialog
        open
        onOpenChange={onOpenChange}
        title="Sign out?"
        description="Ends the session."
        confirmLabel="Sign out"
        onConfirm={onConfirm}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }));
    await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
    expect(onOpenChange).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
