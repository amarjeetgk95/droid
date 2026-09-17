// @vitest-environment happy-dom
import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { apiMock } = vi.hoisted(() => ({ apiMock: { getDeepInsight: vi.fn() } }));
vi.mock('@/lib/api', () => ({ api: apiMock }));

import { DEFAULT_SETTINGS } from '@/lib/settingsDefaults';
import { AIDeepInsightCard } from './AIDeepInsightCard';

const VALID_DATA = {
  market: { direction: 'BULLISH', regime: 'TREND_UP', regime_strength: 0.7, volatility: 'LOW' },
  multi_timeframe: [{ timeframe: '15m', direction: 'BULLISH', strength: 0.6, structure: 'HH/HL' }],
  ai_view: { summary: 'Long bias above VWAP.', bias: 'BULLISH', confidence: 0.62 },
  setup: { entry_zone: '25000-25020', stop_loss: 24950, target: '25200' },
  validation: { status: 'PASSED' },
  provider: { name: 'openrouter', model: 'test-model', latency_ms: 100 },
  signal_state: { state: 'ACTIVE', ttl_remaining: 120 },
  options_evidence: { bias: 'BULLISH', pcr: 1.1, iv: 'LOW' },
};

beforeEach(() => {
  window.localStorage.clear();
  window.localStorage.setItem(
    'droid_app_settings_v2',
    JSON.stringify({ schemaVersion: 2, ai: { ...DEFAULT_SETTINGS.ai, openRouterApiKey: 'test-key' } }),
  );
  apiMock.getDeepInsight.mockReset();
});

afterEach(() => cleanup());

describe('AIDeepInsightCard', () => {
  it('surfaces a null payload as an error with retry, not an empty state', async () => {
    apiMock.getDeepInsight.mockResolvedValue({ data: null, error: null });
    render(<AIDeepInsightCard symbol="NIFTY" />);

    expect(await screen.findByText(/Deep Insight unavailable — The deep-insight service returned no payload/)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeTruthy();
  });

  it('surfaces an HTTP-200 provider error', async () => {
    apiMock.getDeepInsight.mockResolvedValue({ data: null, error: 'provider quota exhausted' });
    render(<AIDeepInsightCard symbol="NIFTY" />);

    expect(await screen.findByText(/Deep Insight unavailable — provider quota exhausted/)).toBeTruthy();
  });

  it('renders a valid payload with the AI provenance label', async () => {
    apiMock.getDeepInsight.mockResolvedValue({ data: VALID_DATA, error: null });
    render(<AIDeepInsightCard symbol="NIFTY" />);

    expect(await screen.findByText('Long bias above VWAP.')).toBeTruthy();
    expect(screen.getByText(/15m/)).toBeTruthy();
    expect(screen.getByText(/not financial advice/)).toBeTruthy();
  });

  it('tolerates a non-array multi-timeframe payload', async () => {
    apiMock.getDeepInsight.mockResolvedValue({
      data: { ...VALID_DATA, multi_timeframe: { bad: true } },
      error: null,
    });
    render(<AIDeepInsightCard symbol="NIFTY" />);

    expect(await screen.findByText('Long bias above VWAP.')).toBeTruthy();
  });
});
