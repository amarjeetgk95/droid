// @vitest-environment happy-dom
import React, { useEffect } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup, act, fireEvent } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

import { DEFAULT_SETTINGS, type AppSettings } from '@/lib/settings';
import { SettingsProvider, useSettings } from './SettingsProvider';

type Ctx = ReturnType<typeof useSettings>;

const ctxRef: { current: Ctx | null } = { current: null };

function Capture() {
  const ctx = useSettings();
  useEffect(() => {
    ctxRef.current = ctx;
  }, [ctx]);
  return (
    <div>
      <button type="button" onClick={() => ctx.updatePreferences({ numberFormat: 'INTERNATIONAL' })}>
        edit-prefs
      </button>
      <button type="button" onClick={() => ctx.updateQuantitative({ brokeragePerOrder: 99 })}>
        edit-quant
      </button>
      <button type="button" onClick={() => void ctx.save()}>
        save
      </button>
      <button type="button" onClick={() => void ctx.saveSection('preferences')}>
        save-prefs
      </button>
      <span data-testid="dirty">{String(ctx.isDirty)}</span>
      <span data-testid="dirty-prefs">{String(ctx.isDirtySections.preferences)}</span>
      <span data-testid="dirty-quant">{String(ctx.isDirtySections.quantitative)}</span>
      <span data-testid="msgtype">{ctx.saveMessage?.type ?? ''}</span>
      <span data-testid="msgtxt">{ctx.saveMessage?.text ?? ''}</span>
      <span data-testid="format">{ctx.settings.preferences.numberFormat}</span>
      <span data-testid="symbol">{ctx.settings.preferences.defaultIndexSymbol}</span>
      <span data-testid="brokerage">{String(ctx.settings.quantitative.brokeragePerOrder)}</span>
    </div>
  );
}

function renderProvider(
  onSaveToBackend: (settings: AppSettings) => Promise<void>,
  onLoadFromBackend?: () => Promise<AppSettings | null>,
) {
  return render(
    <SettingsProvider onSaveToBackend={onSaveToBackend} onLoadFromBackend={onLoadFromBackend}>
      <Capture />
    </SettingsProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  ctxRef.current = null;
});

afterEach(() => cleanup());

describe('SettingsProvider save semantics', () => {
  it('does not toast success and stays dirty when the backend save fails', async () => {
    const onSave = vi.fn().mockRejectedValue(new Error('backend down'));
    renderProvider(onSave);

    fireEvent.click(screen.getByText('edit-prefs'));
    await waitFor(() => expect(screen.getByTestId('dirty').textContent).toBe('true'));

    fireEvent.click(screen.getByText('save'));
    await waitFor(() => expect(screen.getByTestId('msgtype').textContent).toBe('error'));
    expect(screen.getByTestId('msgtxt').textContent).toContain('were not saved');
    expect(screen.getByTestId('dirty').textContent).toBe('true');
    // The local cache must not have been advanced before the backend write.
    expect(localStorage.getItem('droid_app_settings_v2')).toBeNull();
  });

  it('persists only the validated section and keeps other tabs dirty', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    renderProvider(onSave);

    fireEvent.click(screen.getByText('edit-prefs'));
    fireEvent.click(screen.getByText('edit-quant'));
    await waitFor(() => expect(screen.getByTestId('dirty').textContent).toBe('true'));

    fireEvent.click(screen.getByText('save-prefs'));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));

    const persisted = onSave.mock.calls[0][0] as AppSettings;
    expect(persisted.preferences.numberFormat).toBe('INTERNATIONAL');
    // Unsaved quant edit must not be published by a preferences-only save.
    expect(persisted.quantitative.brokeragePerOrder).toBe(
      DEFAULT_SETTINGS.quantitative.brokeragePerOrder,
    );

    await waitFor(() => expect(screen.getByTestId('dirty-prefs').textContent).toBe('false'));
    expect(screen.getByTestId('dirty-quant').textContent).toBe('true');
    expect(screen.getByTestId('dirty').textContent).toBe('true');
  });

  it('leaves state untouched and reports failure when reset cannot reach the backend', async () => {
    const onSave = vi.fn().mockRejectedValue(new Error('offline'));
    renderProvider(onSave);

    fireEvent.click(screen.getByText('edit-prefs'));
    await waitFor(() => expect(screen.getByTestId('dirty').textContent).toBe('true'));

    let result: { success: boolean } | undefined;
    await act(async () => {
      result = await ctxRef.current!.reset();
    });

    expect(result?.success).toBe(false);
    expect(screen.getByTestId('msgtype').textContent).toBe('error');
    expect(screen.getByTestId('format').textContent).toBe('INTERNATIONAL');
    // The backend write was attempted first, then rolled back — local state
    // still holds the edited (dirty) value.
    expect(onSave).toHaveBeenCalledWith(DEFAULT_SETTINGS);
  });

  it('rejects imports with invalid values instead of applying them', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    renderProvider(onSave);

    let result: { success: boolean; error?: string } | undefined;
    await act(async () => {
      result = ctxRef.current!.importJson(
        JSON.stringify({
          preferences: { theme: 'light', numberFormat: 'INVALID', defaultIndexSymbol: 'NIFTY 50' },
        }),
      );
    });

    expect(result?.success).toBe(false);
    expect(result?.error).toContain('preferences.numberFormat');
    expect(screen.getByTestId('msgtype').textContent).toBe('error');
    expect(screen.getByTestId('format').textContent).toBe('INDIAN');
  });
});

describe('SettingsProvider hydration', () => {
  const remoteSettings: AppSettings = {
    ...DEFAULT_SETTINGS,
    preferences: { ...DEFAULT_SETTINGS.preferences, defaultIndexSymbol: 'SENSEX' },
    quantitative: { ...DEFAULT_SETTINGS.quantitative, brokeragePerOrder: 42 },
  };

  it('applies remote settings under StrictMode and marks them clean', async () => {
    const loader = () => Promise.resolve(remoteSettings);
    render(
      <React.StrictMode>
        <SettingsProvider onLoadFromBackend={loader} onSaveToBackend={async () => {}}>
          <Capture />
        </SettingsProvider>
      </React.StrictMode>,
    );

    await waitFor(() => expect(screen.getByTestId('symbol').textContent).toBe('SENSEX'));
    expect(screen.getByTestId('dirty').textContent).toBe('false');
  });

  it('keeps edits made while the remote load is in flight', async () => {
    let resolveLoad: (value: AppSettings) => void = () => {};
    const pending = new Promise<AppSettings>((resolve) => { resolveLoad = resolve; });
    const loader = () => pending;
    const onSave = vi.fn().mockResolvedValue(undefined);

    renderProvider(onSave, loader);

    fireEvent.click(screen.getByText('edit-prefs'));
    await waitFor(() => expect(screen.getByTestId('format').textContent).toBe('INTERNATIONAL'));

    await act(async () => {
      resolveLoad(remoteSettings);
      await pending;
    });

    // Local edit survives; untouched sections take the remote value.
    expect(screen.getByTestId('format').textContent).toBe('INTERNATIONAL');
    expect(screen.getByTestId('brokerage').textContent).toBe('42');
    expect(screen.getByTestId('dirty').textContent).toBe('true');
  });
});
