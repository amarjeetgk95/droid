import { afterEach, describe, expect, it, vi } from 'vitest';

const { getStoredSettingsMock } = vi.hoisted(() => ({
  getStoredSettingsMock: vi.fn(),
}));

vi.mock('./settingsStorage', () => ({
  getStoredSettings: getStoredSettingsMock,
}));

import {
  buildAnalyzePayload,
  getStoredAISettings,
  missingKeyHint,
  resolveAISettings,
  toBackendSymbol,
} from './aiPayload';
import { DEFAULT_SETTINGS } from './settingsDefaults';
import type { AISettings } from './settingsTypes';

function settingsWith(ai: AISettings) {
  return { ...DEFAULT_SETTINGS, ai };
}

afterEach(() => {
  getStoredSettingsMock.mockReset();
});

describe('getStoredAISettings identity', () => {
  it('returns the same reference while settings are structurally unchanged', () => {
    const base = { ...DEFAULT_SETTINGS.ai };

    getStoredSettingsMock.mockReturnValue(settingsWith({ ...base }));
    const first = getStoredAISettings();

    // Fresh parse with identical content (the focus/storage-event case).
    getStoredSettingsMock.mockReturnValue(
      settingsWith({ ...base, taskModels: { ...base.taskModels } }),
    );
    const second = getStoredAISettings();

    expect(first).not.toBeNull();
    expect(second).toBe(first);
  });

  it('returns a new reference after a real change, then stabilizes again', () => {
    const base = { ...DEFAULT_SETTINGS.ai };
    getStoredSettingsMock.mockReturnValue(settingsWith({ ...base }));
    const before = getStoredAISettings();

    const changed: AISettings = {
      ...DEFAULT_SETTINGS.ai,
      openRouterApiKey: 'sk-or-v1-changed',
      taskModels: { ...DEFAULT_SETTINGS.ai.taskModels, NEWS_ANALYSIS: 'openai/gpt-4o' },
    };

    getStoredSettingsMock.mockReturnValue(settingsWith(changed));
    const updated = getStoredAISettings();
    expect(updated).not.toBe(before);
    expect(updated?.openRouterApiKey).toBe('sk-or-v1-changed');
    expect(updated?.taskModels.NEWS_ANALYSIS).toBe('openai/gpt-4o');

    getStoredSettingsMock.mockReturnValue(settingsWith({ ...changed }));
    expect(getStoredAISettings()).toBe(updated);
  });

  it('returns null instead of throwing when storage read fails', () => {
    getStoredSettingsMock.mockImplementation(() => {
      throw new Error('storage unavailable');
    });
    expect(getStoredAISettings()).toBeNull();

    getStoredSettingsMock.mockReturnValue(settingsWith({ ...DEFAULT_SETTINGS.ai }));
    expect(getStoredAISettings()).not.toBeNull();
  });
});

describe('resolveAISettings', () => {
  it('falls back to OpenRouter auto when settings are missing', () => {
    expect(resolveAISettings(null)).toEqual({ provider: 'openrouter', model: 'auto', allow_paid: false });
  });

  it('resolves the default OpenRouter mode', () => {
    const resolved = resolveAISettings({ ...DEFAULT_SETTINGS.ai, openRouterApiKey: 'key' });
    expect(resolved.provider).toBe('openrouter');
    expect(resolved.model).toBe('auto');
    expect(resolved.openRouterApiKey).toBe('key');
  });

  it('resolves a direct NVIDIA provider without leaking the OpenRouter key', () => {
    const resolved = resolveAISettings({
      ...DEFAULT_SETTINGS.ai,
      connectionMode: 'Direct Provider',
      directProvider: 'NVIDIA',
      nvidiaApiKey: 'nv-key',
      nvidiaModel: 'meta/llama-3.3-70b-instruct',
    });
    expect(resolved.provider).toBe('nvidia');
    expect(resolved.model).toBe('meta/llama-3.3-70b-instruct');
    expect(resolved.nvidiaApiKey).toBe('nv-key');
    expect(resolved.openRouterApiKey).toBeUndefined();
  });

  it('builds an analyze payload carrying the resolved provider fields', () => {
    const payload = buildAnalyzePayload('BANKNIFTY', { ...DEFAULT_SETTINGS.ai, openRouterApiKey: 'key' });
    expect(payload.symbol).toBe('BANKNIFTY');
    expect(payload.provider).toBe('openrouter');
    expect(payload.openRouterApiKey).toBe('key');
  });
});

describe('toBackendSymbol / missingKeyHint', () => {
  it('normalizes display symbols', () => {
    expect(toBackendSymbol('NIFTY 50')).toBe('NIFTY');
    expect(toBackendSymbol('banknifty')).toBe('BANKNIFTY');
    expect(toBackendSymbol('')).toBe('NIFTY');
  });

  it('hints when the OpenRouter key is missing', () => {
    expect(missingKeyHint({ ...DEFAULT_SETTINGS.ai, openRouterApiKey: '' })).toContain('OpenRouter key missing');
    expect(missingKeyHint({ ...DEFAULT_SETTINGS.ai, openRouterApiKey: 'sk-or-v1-x' })).toBeNull();
    expect(missingKeyHint(null)).toContain('AI settings not found');
  });
});
