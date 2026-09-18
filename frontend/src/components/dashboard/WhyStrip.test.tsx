// @vitest-environment happy-dom
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, act, cleanup } from '@testing-library/react';

const { sectionMock, marketMock, sessionMock, apiMock, polls } = vi.hoisted(() => {
  const apiMock = {
    getRegimeOverview: vi.fn(async (): Promise<unknown> => ({ data: null })),
    getResearchOptionsContext: vi.fn(async (): Promise<unknown> => null),
  };
  return {
    sectionMock: { current: null as unknown },
    marketMock: { current: null as unknown },
    sessionMock: { phase: 'OPEN', isOpen: true },
    apiMock,
    polls: [] as Array<() => unknown>,
  };
});

vi.mock('@/context/AppStreamContext', () => ({
  useCommandSection: (name: string) => (name === 'regime' ? sectionMock.current : null),
}));
vi.mock('@/context/MarketDataContext', () => ({
  useOptionalMarketDataContext: () => marketMock.current,
}));
vi.mock('@/hooks/useMarketSession', () => ({
  useMarketSession: () => sessionMock,
}));
vi.mock('@/lib/api', () => ({ api: apiMock }));
vi.mock('@/hooks/usePolling', () => ({
  usePolling: (cb: () => unknown) => {
    polls.push(cb);
  },
}));

import { WhyStrip } from './WhyStrip';

function sectionEnvelope(value: unknown, degraded = false) {
  return {
    value,
    updated_at: '2026-09-18T07:22:01.000Z',
    freshness_s: 1,
    degraded,
    version: 1,
  };
}

const NIFTY_SECTION = sectionEnvelope({
  regime_overview: {
    symbol: 'NIFTY 50',
    regime_state: 'TRENDING_BULLISH',
    key_levels: { nearest_support: 25000, nearest_resistance: 25500 },
  },
  options_analytics: { available: true, pcr_oi: 1.1, call_wall: 25600, put_wall: 24900 },
  futures: { NIFTY: null, BANKNIFTY: null },
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  sectionMock.current = null;
  marketMock.current = null;
  polls.length = 0;
  apiMock.getRegimeOverview.mockResolvedValue({ data: null });
  apiMock.getResearchOptionsContext.mockResolvedValue(null);
});

async function flushPoll() {
  const cb = polls.at(-1);
  expect(cb).toBeTruthy();
  await act(async () => {
    await cb?.();
  });
}

describe('WhyStrip stream/REST context', () => {
  it('renders the stream regime/options legs for NIFTY-family instruments', () => {
    sectionMock.current = NIFTY_SECTION;
    render(<WhyStrip instrument="NIFTY 50" />);

    expect(screen.getByText('TRENDING BULLISH')).toBeTruthy();
    expect(screen.getByText('₹25,000')).toBeTruthy();
    expect(screen.getByText('₹25,500')).toBeTruthy();
    expect(screen.getByText('1.10')).toBeTruthy();
    expect(screen.getByText('₹25,600')).toBeTruthy();
    expect(screen.getByText('₹24,900')).toBeTruthy();
    expect(apiMock.getRegimeOverview).not.toHaveBeenCalled();
  });

  it('falls back to the REST fetch for instruments outside the NIFTY section', async () => {
    sectionMock.current = NIFTY_SECTION;
    apiMock.getRegimeOverview.mockResolvedValue({
      data: {
        symbol: 'BANKNIFTY',
        regime_state: 'RANGEBOUND_VOLATILE',
        key_levels: { nearest_support: 51000, nearest_resistance: 52000 },
        timestamp: '2026-09-18T07:20:00Z',
      },
    });
    apiMock.getResearchOptionsContext.mockResolvedValue({
      available: true,
      pcr_oi: 0.9,
      call_wall: 52100,
      put_wall: 50900,
    });

    render(<WhyStrip instrument="BANKNIFTY" />);
    await flushPoll();

    expect(apiMock.getRegimeOverview).toHaveBeenCalledWith('BANKNIFTY');
    expect(apiMock.getResearchOptionsContext).toHaveBeenCalledWith('BANKNIFTY');
    expect(screen.getByText('RANGEBOUND VOLATILE')).toBeTruthy();
    expect(screen.getByText('₹51,000')).toBeTruthy();
    expect(screen.getByText('0.90')).toBeTruthy();
    expect(screen.queryByText('TRENDING BULLISH')).toBeNull();
    expect(screen.queryByText('₹25,000')).toBeNull();
  });

  it('shows honest unavailability when both the stream and REST have nothing', async () => {
    apiMock.getRegimeOverview.mockRejectedValue(new Error('regime service down'));
    apiMock.getResearchOptionsContext.mockRejectedValue(new Error('options service down'));

    render(<WhyStrip instrument="SENSEX" />);
    await flushPoll();

    expect(screen.getByText(/Market context unavailable/)).toBeTruthy();
  });

  it('keeps the NIFTY-family MarketDataContext fallback while the stream warms up', () => {
    marketMock.current = {
      regimeOverview: {
        symbol: 'NIFTY 50',
        regime_state: 'RANGEBOUND_LOW_VOL',
        key_levels: { nearest_support: 24000, nearest_resistance: 26000 },
      },
    };
    render(<WhyStrip instrument="NIFTY 50" />);

    expect(screen.getByText('RANGEBOUND LOW VOL')).toBeTruthy();
    expect(screen.getByText('₹24,000')).toBeTruthy();
    expect(screen.getByText('₹26,000')).toBeTruthy();
  });
});
