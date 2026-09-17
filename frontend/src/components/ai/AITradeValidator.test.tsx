// @vitest-environment happy-dom
import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { apiMock } = vi.hoisted(() => ({ apiMock: { validateTradeSetup: vi.fn() } }));
vi.mock('@/lib/api', () => ({ api: apiMock }));

import { DEFAULT_SETTINGS } from '@/lib/settingsDefaults';
import { AITradeValidator } from './AITradeValidator';

beforeEach(() => {
  window.localStorage.clear();
  window.localStorage.setItem(
    'droid_app_settings_v2',
    JSON.stringify({ schemaVersion: 2, ai: { ...DEFAULT_SETTINGS.ai, openRouterApiKey: 'test-key' } }),
  );
  apiMock.validateTradeSetup.mockReset();
});

afterEach(() => cleanup());

function fillLevels() {
  fireEvent.change(screen.getByLabelText(/stop loss/i), { target: { value: '95' } });
  fireEvent.change(screen.getByLabelText(/^target$/i), { target: { value: '115' } });
}

function submit() {
  fireEvent.click(screen.getByRole('button', { name: 'Validate setup' }));
}

describe('AITradeValidator', () => {
  it('surfaces an HTTP-200 provider error with a retry', async () => {
    apiMock.validateTradeSetup.mockResolvedValue({ data: null, error: 'provider refused the request' });
    render(<AITradeValidator symbol="NIFTY" spotPrice={100} />);
    fillLevels();
    submit();

    expect(await screen.findByText(/Audit unavailable — provider refused the request/)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeTruthy();
  });

  it('renders a non-finite risk/reward as an em dash, never NaN', async () => {
    apiMock.validateTradeSetup.mockResolvedValue({
      data: {
        decision: 'CONFIRM',
        score: 82,
        risk_reward_calculated: Number.NaN,
        executive_verdict: 'Setup is aligned with the regime.',
        technical_alignment: 'ok',
        derivatives_alignment: 'ok',
        volatility_regime_check: 'ok',
        invalidation_conditions: [],
        warning_traps: [],
        provider_used: 'openrouter:test-model',
      },
      error: null,
    });
    render(<AITradeValidator symbol="NIFTY" spotPrice={100} />);
    fillLevels();
    submit();

    expect(await screen.findByText('Setup is aligned with the regime.')).toBeTruthy();
    const meta = screen.getByText(/score 82/);
    expect(meta.textContent).toContain('RR —');
    expect(meta.textContent).not.toContain('NaN');
    expect(screen.getByText(/not financial advice/)).toBeTruthy();
  });

  it('rejects malformed list fields with a visible schema error instead of crashing', async () => {
    apiMock.validateTradeSetup.mockResolvedValue({
      data: {
        decision: 'WATCH',
        executive_verdict: 'Watch carefully.',
        warning_traps: 'not-a-list',
      },
      error: null,
    });
    render(<AITradeValidator symbol="NIFTY" spotPrice={100} />);
    fillLevels();
    submit();

    expect(await screen.findByText(/The validation response was malformed/)).toBeTruthy();
    expect(screen.getByText(/Audit unavailable/)).toBeTruthy();
  });
});
