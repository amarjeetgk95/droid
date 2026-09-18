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

const REGIME_SECTION = sectionEnvelope({
  regime_overview: null,
  options_analytics: null,
  by_symbol: {
    NIFTY: {
      regime_overview: {
        symbol: 'NIFTY 50',
        regime_state: 'TRENDING_BULLISH',
        key_levels: { nearest_support: 25000, nearest_resistance: 25500 },
      },
      options_analytics: {
        symbol: 'NIFTY',
        spot_price: 25000,
        pcr_oi: 1.1,
        max_pain_strike: 25100,
      },
    },
    BANKNIFTY: {
      regime_overview: {
        symbol: 'BANKNIFTY',
        regime_state: 'RANGEBOUND_VOLATILE',
        key_levels: { nearest_support: 51000, nearest_resistance: 52000 },
      },
      options_analytics: { symbol: 'BANKNIFTY', spot_price: 51500, pcr_oi: 0.9 },
    },
    SENSEX: null,
  },
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

describe('WhyStrip by_symbol consumption', () => {
  it('renders regime/levels/PCR from by_symbol and only polls REST for the option walls', async () => {
    sectionMock.current = REGIME_SECTION;
    apiMock.getResearchOptionsContext.mockResolvedValue({
      available: true,
      pcr_oi: 0.5,
      call_wall: 25600,
      put_wall: 24900,
      timestamp: '2026-09-18T07:20:00Z',
    });

    render(<WhyStrip instrument="NIFTY 50" />);

    // Stream rows are already usable; the wall rows cannot be fabricated.
    expect(screen.getByText('TRENDING BULLISH')).toBeTruthy();
    expect(screen.getByText('₹25,000')).toBeTruthy();
    expect(screen.getByText('₹25,500')).toBeTruthy();
    expect(screen.getByText('1.10')).toBeTruthy();
    expect(screen.getAllByText('—').length).toBe(2); // Call wall / Put wall

    await flushPoll();

    // Stream PCR wins over the REST PCR; the walls come from the REST leg.
    expect(screen.getByText('1.10')).toBeTruthy();
    expect(screen.queryByText('0.50')).toBeNull();
    expect(screen.getByText('₹25,600')).toBeTruthy();
    expect(screen.getByText('₹24,900')).toBeTruthy();
    expect(apiMock.getRegimeOverview).not.toHaveBeenCalled();
    expect(apiMock.getResearchOptionsContext).toHaveBeenCalledWith('NIFTY 50');
  });

  it('renders BANKNIFTY by_symbol values and never NIFTY values', async () => {
    sectionMock.current = REGIME_SECTION;
    render(<WhyStrip instrument="BANKNIFTY" />);
    await flushPoll();

    expect(screen.getByText('RANGEBOUND VOLATILE')).toBeTruthy();
    expect(screen.getByText('₹51,000')).toBeTruthy();
    expect(screen.getByText('₹52,000')).toBeTruthy();
    expect(screen.getByText('0.90')).toBeTruthy();
    expect(screen.queryByText('TRENDING BULLISH')).toBeNull();
    expect(screen.queryByText('₹25,000')).toBeNull();
    expect(apiMock.getRegimeOverview).not.toHaveBeenCalled();
  });

  it('shows the options walls as unavailable when the REST fallback fails', async () => {
    sectionMock.current = REGIME_SECTION;
    apiMock.getResearchOptionsContext.mockRejectedValue(new Error('options service down'));

    render(<WhyStrip instrument="SENSEX" />);
    await flushPoll();

    // SENSEX has no by_symbol entry and the REST wall leg failed.
    expect(screen.getByText(/Market context unavailable/)).toBeTruthy();
    expect(apiMock.getRegimeOverview).not.toHaveBeenCalled();
  });

  it('marks the strip degraded when only the wall rows fall back', async () => {
    sectionMock.current = REGIME_SECTION;
    apiMock.getResearchOptionsContext.mockResolvedValue({
      available: true,
      pcr_oi: 1.1,
      call_wall: null,
      put_wall: null,
    });

    render(<WhyStrip instrument="NIFTY 50" />);
    await flushPoll();

    expect(screen.getByText('TRENDING BULLISH')).toBeTruthy();
    expect(screen.getByText(/partial leg\(s\) missing/)).toBeTruthy();
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
