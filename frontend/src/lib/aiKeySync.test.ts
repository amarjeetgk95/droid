// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { getSettingsMock } = vi.hoisted(() => ({ getSettingsMock: vi.fn() }));
vi.mock('./api', () => ({ api: { getSettings: getSettingsMock } }));

const { getStoredSettingsMock, saveStoredSettingsMock } = vi.hoisted(() => ({
  getStoredSettingsMock: vi.fn(),
  saveStoredSettingsMock: vi.fn(),
}));
vi.mock('./settingsStorage', () => ({
  getStoredSettings: getStoredSettingsMock,
  saveStoredSettings: saveStoredSettingsMock,
}));

import { AI_SYNC_EVENT, syncAISecretsFromBackend } from './aiKeySync';
import { DEFAULT_SETTINGS } from './settingsDefaults';
import type { AppSettings } from './settingsTypes';

function cloneDefaults(): AppSettings {
  return { ...DEFAULT_SETTINGS, ai: { ...DEFAULT_SETTINGS.ai } };
}

describe('syncAISecretsFromBackend', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('fills remote secrets into a cloned AI section and emits the sync event', async () => {
    const local = cloneDefaults();
    local.ai.openRouterApiKey = '';
    getStoredSettingsMock.mockReturnValue(local);
    getSettingsMock.mockResolvedValue({
      app_settings: { ai: { openRouterApiKey: 'sk-or-v1-remote', geminiApiKey: '' } },
    });

    const listener = vi.fn();
    window.addEventListener(AI_SYNC_EVENT, listener);
    const changed = await syncAISecretsFromBackend(true);
    window.removeEventListener(AI_SYNC_EVENT, listener);

    expect(changed).toBe(true);
    // The object read from storage must not be mutated in place.
    expect(local.ai.openRouterApiKey).toBe('');
    expect(saveStoredSettingsMock).toHaveBeenCalledTimes(1);
    const saved = saveStoredSettingsMock.mock.calls[0][0] as AppSettings;
    expect(saved.ai).not.toBe(local.ai);
    expect(saved.ai.openRouterApiKey).toBe('sk-or-v1-remote');
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it('never blanks a local key with an empty remote value', async () => {
    const local = cloneDefaults();
    local.ai.geminiApiKey = 'local-key';
    getStoredSettingsMock.mockReturnValue(local);
    getSettingsMock.mockResolvedValue({
      app_settings: { ai: { geminiApiKey: '', openRouterApiKey: '   ' } },
    });

    const changed = await syncAISecretsFromBackend(true);

    expect(changed).toBe(false);
    expect(saveStoredSettingsMock).not.toHaveBeenCalled();
  });

  it('is a silent no-op when the backend is unreachable or has no AI settings', async () => {
    getStoredSettingsMock.mockReturnValue(cloneDefaults());
    getSettingsMock.mockRejectedValueOnce(new Error('offline'));
    await expect(syncAISecretsFromBackend(true)).resolves.toBe(false);

    getSettingsMock.mockResolvedValueOnce({ app_settings: {} });
    await expect(syncAISecretsFromBackend(true)).resolves.toBe(false);
    expect(saveStoredSettingsMock).not.toHaveBeenCalled();
  });
});
