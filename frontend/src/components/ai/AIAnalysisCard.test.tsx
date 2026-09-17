// @vitest-environment happy-dom
import React from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    generateAIAnalysisWithModel: vi.fn(),
    getAIHistory: vi.fn(),
    getMarketBriefing: vi.fn(),
  },
}));
vi.mock('@/lib/api', () => ({ api: apiMock }));

import { DEFAULT_SETTINGS } from '@/lib/settingsDefaults';
import { AIAnalysisCard } from './AIAnalysisCard';

const VALID_INSIGHT = {
  symbol: 'NIFTY',
  timestamp: '2026-01-01T00:00:00Z',
  market_bias: 'BULLISH' as const,
  confidence: 68,
  executive_summary: 'Momentum holding with call writers capping 25200.',
  simple_takeaway: 'Trend intact above VWAP.',
  options_interpretation: 'Call writers at 25200.',
  futures_flow_analysis: '',
  regime_and_levels: '',
  recommended_strategy_framework: '',
  risk_management_notes: '',
  disclaimer: '',
  provider_used: 'openrouter:test-model',
};

const VALID_BRIEFING = {
  symbol: 'NIFTY',
  session_type: 'PRE_MARKET' as const,
  timestamp: '2026-01-01T00:00:00Z',
  executive_summary: 'Markets firm; watch the 25000 pin.',
  key_levels_to_watch: { spot: 25000, pivot: 24950, r1: 25100, s1: 24800, poc: 24980, vah: 25050, val: 24900 },
  options_pin_and_pivots: 'Pin drifting to 25000.',
  fii_dii_implication: 'FIIs net buyers.',
  actionable_playbook: ['Buy dips near 24900'],
  provider_used: 'openrouter:test-model',
};

beforeEach(() => {
  window.localStorage.clear();
  window.localStorage.setItem(
    'droid_app_settings_v2',
    JSON.stringify({ schemaVersion: 2, ai: { ...DEFAULT_SETTINGS.ai, openRouterApiKey: 'test-key' } }),
  );
  apiMock.generateAIAnalysisWithModel.mockReset();
  apiMock.getAIHistory.mockReset();
  apiMock.getMarketBriefing.mockReset();
});

afterEach(() => cleanup());

describe('AIAnalysisCard', () => {
  it('keeps fulfilled sections when one sub-fetch rejects', async () => {
    apiMock.generateAIAnalysisWithModel.mockRejectedValue(new Error('analysis engine down'));
    apiMock.getAIHistory.mockResolvedValue({ data: [], error: null });
    apiMock.getMarketBriefing.mockResolvedValue({ data: VALID_BRIEFING, error: null });

    render(<AIAnalysisCard symbol="NIFTY 50" />);
    expect(await screen.findByText(/AI analysis unavailable — analysis engine down/)).toBeTruthy();

    fireEvent.click(screen.getByRole('tab', { name: 'Briefing' }));
    expect(await screen.findByText('Markets firm; watch the 25000 pin.')).toBeTruthy();
    expect(screen.getByText('Pin drifting to 25000.')).toBeTruthy();
  });

  it('treats an HTTP-200 payload error as a visible error', async () => {
    apiMock.generateAIAnalysisWithModel.mockResolvedValue({ data: null, error: 'provider refused' });
    apiMock.getAIHistory.mockResolvedValue({ data: [], error: null });
    apiMock.getMarketBriefing.mockResolvedValue({ data: null, error: null });

    render(<AIAnalysisCard symbol="NIFTY" />);
    expect(await screen.findByText(/AI analysis unavailable — provider refused/)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeTruthy();
  });

  it('renders analysis, history and is resilient to a malformed history item', async () => {
    apiMock.generateAIAnalysisWithModel.mockResolvedValue({
      data: VALID_INSIGHT,
      error: null,
      model_used: 'test-model',
      latency_ms: 120,
    });
    apiMock.getAIHistory.mockResolvedValue({
      data: [
        { id: '1', market_bias: 'BULLISH', confidence: 61, executive_summary: 'Prior day summary' },
        { id: '2', market_bias: 'BULLISH', confidence: 42, executive_summary: { bad: true } },
      ],
      error: null,
    });
    apiMock.getMarketBriefing.mockRejectedValue(new Error('briefing down'));

    render(<AIAnalysisCard symbol="NIFTY" />);
    expect(await screen.findByText('Trend intact above VWAP.')).toBeTruthy();
    expect(screen.getByText(/not financial advice/)).toBeTruthy();
    expect(screen.getByRole('tab', { name: /History \(1\)/ })).toBeTruthy();

    fireEvent.click(screen.getByRole('tab', { name: /History/ }));
    expect(await screen.findByText('Prior day summary')).toBeTruthy();
  });

  it('does not refetch on focus/storage events while settings are unchanged', async () => {
    apiMock.generateAIAnalysisWithModel.mockResolvedValue({ data: VALID_INSIGHT, error: null });
    apiMock.getAIHistory.mockResolvedValue({ data: [], error: null });
    apiMock.getMarketBriefing.mockResolvedValue({ data: VALID_BRIEFING, error: null });

    render(<AIAnalysisCard symbol="NIFTY" />);
    expect(await screen.findByText('Trend intact above VWAP.')).toBeTruthy();
    expect(apiMock.generateAIAnalysisWithModel).toHaveBeenCalledTimes(1);

    await act(async () => {
      window.dispatchEvent(new Event('focus'));
      window.dispatchEvent(new StorageEvent('storage', { key: 'droid_app_settings_v2' }));
      await new Promise((resolve) => setTimeout(resolve, 20));
    });

    expect(apiMock.generateAIAnalysisWithModel).toHaveBeenCalledTimes(1);
    expect(apiMock.getMarketBriefing).toHaveBeenCalledTimes(1);
  });
});
