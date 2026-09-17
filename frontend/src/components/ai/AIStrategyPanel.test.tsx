// @vitest-environment happy-dom
import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { apiMock } = vi.hoisted(() => ({ apiMock: { recommendOptionsStrategy: vi.fn() } }));
vi.mock('@/lib/api', () => ({ api: apiMock }));

import { DEFAULT_SETTINGS } from '@/lib/settingsDefaults';
import { AIStrategyPanel } from './AIStrategyPanel';

const VALID_REC = {
  strategy_name: 'Bull Call Spread',
  market_outlook: 'BULLISH',
  legs: [
    { strike: 25000, option_type: 'CE', action: 'BUY', estimated_premium: 120, delta: 0.52, theta: -8.1 },
    { strike: 25200, option_type: 'CE', action: 'SELL', estimated_premium: 60, delta: 0.31, theta: -5.4 },
  ],
  max_profit_pts: '80',
  max_loss_pts: '-40',
  risk_reward_ratio: '2.0',
  breakevens: [25060],
  net_debit_credit_pts: -60,
  net_delta: 0.21,
  net_theta: -2.7,
  rationale: 'Defined-risk bullish continuation.',
  entry_rules: ['Enter above VWAP'],
  exit_rules: ['Exit at 80% max profit'],
  risk_management: 'Risk 1% of capital.',
  timestamp: '2026-01-01T00:00:00Z',
  provider_used: 'openrouter:test-model',
};

beforeEach(() => {
  window.localStorage.clear();
  window.localStorage.setItem(
    'droid_app_settings_v2',
    JSON.stringify({ schemaVersion: 2, ai: { ...DEFAULT_SETTINGS.ai, openRouterApiKey: 'test-key' } }),
  );
  apiMock.recommendOptionsStrategy.mockReset();
});

afterEach(() => cleanup());

describe('AIStrategyPanel', () => {
  it('surfaces an HTTP-200 provider error with a retry instead of an empty state', async () => {
    apiMock.recommendOptionsStrategy.mockResolvedValue({
      data: null,
      error: 'No API key configured for provider',
    });
    render(<AIStrategyPanel symbol="NIFTY" />);
    fireEvent.click(screen.getByRole('button', { name: 'Recommend' }));

    expect(await screen.findByText(/Strategy unavailable — No API key configured for provider/)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeTruthy();
  });

  it('shows a schema error for a malformed recommendation instead of crashing', async () => {
    apiMock.recommendOptionsStrategy.mockResolvedValue({
      data: { strategy_name: 'Iron Condor' },
      error: null,
    });
    render(<AIStrategyPanel symbol="NIFTY" />);
    fireEvent.click(screen.getByRole('button', { name: 'Recommend' }));

    expect(await screen.findByText(/Strategy unavailable — The strategy response was malformed/)).toBeTruthy();
  });

  it('renders a valid recommendation with legs and the AI provenance label', async () => {
    apiMock.recommendOptionsStrategy.mockResolvedValue({ data: VALID_REC, error: null });
    render(<AIStrategyPanel symbol="NIFTY" />);
    fireEvent.click(screen.getByRole('button', { name: 'Recommend' }));

    expect(await screen.findByText('Bull Call Spread')).toBeTruthy();
    expect(screen.getByText('25000')).toBeTruthy();
    expect(screen.getByText(/not financial advice/)).toBeTruthy();
    expect(screen.getByText(/openrouter:test-model/)).toBeTruthy();
  });
});
