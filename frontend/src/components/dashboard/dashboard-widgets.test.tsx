// @vitest-environment happy-dom
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, act, cleanup, fireEvent } from '@testing-library/react';
import type { VirtualPosition } from '@/lib/types';

const { apiMock, sessionMock, polls, sectionMock, refreshMock } = vi.hoisted(() => {
  const apiMock: Record<string, ReturnType<typeof vi.fn>> = {
    listResearchPredictions: vi.fn(async () => []),
    getResearchPredictionOutcome: vi.fn(async () => {
      throw new Error('outcome not measured');
    }),
    measureResearchPrediction: vi.fn(async () => ({})),
    getPaperPortfolio: vi.fn(async () => ({ data: null })),
    getPaperPositions: vi.fn(async () => ({ data: [] })),
  };
  const sessionMock = { phase: 'OPEN', isOpen: true };
  const polls: Array<() => unknown> = [];
  const sectionMock: { current: unknown } = { current: null };
  const refreshMock = vi.fn(async () => undefined);
  return { apiMock, sessionMock, polls, sectionMock, refreshMock };
});

vi.mock('@/lib/api', () => ({ api: apiMock }));
vi.mock('@/hooks/useMarketSession', () => ({
  useMarketSession: () => sessionMock,
}));
vi.mock('@/hooks/usePolling', () => ({
  usePolling: (cb: () => unknown) => {
    polls.push(cb);
  },
}));
vi.mock('@/context/AppStreamContext', () => ({
  useCommandSection: (name: string) => (name === 'forecast' ? sectionMock.current : null),
  useAppStreamRefresh: () => refreshMock,
}));

function sectionEnvelope(value: unknown, degraded = false) {
  return {
    value,
    updated_at: '2026-09-18T07:22:01.000Z',
    freshness_s: 1,
    degraded,
    version: 1,
  };
}

import { ForecastOutcomes } from './ForecastOutcomes';
import { PaperPnLWidget } from '@/components/command-center/PaperPnLWidget';

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  sessionMock.phase = 'OPEN';
  sessionMock.isOpen = true;
  polls.length = 0;
  sectionMock.current = null;
  apiMock.listResearchPredictions.mockResolvedValue([]);
});

async function flushPoll() {
  const cb = polls.at(-1);
  expect(cb).toBeTruthy();
  await act(async () => {
    await cb?.();
  });
}

async function flushEffects() {
  await act(async () => {
    await Promise.resolve();
  });
}

describe('ForecastOutcomes by_instrument consumption', () => {
  it('filters the selected instrument on forecast_horizon, not the chart timeframe', async () => {
    sectionMock.current = sectionEnvelope({
      by_instrument: {
        'NIFTY 50': [
          {
            prediction_id: 'p-1h',
            forecast_horizon: '1h',
            timeframe: '5m',
            direction: 'BULLISH',
            score: 42,
            timestamp: '2026-09-17T10:00:00Z',
          },
          {
            prediction_id: 'p-15m',
            forecast_horizon: '15m',
            timeframe: '1h',
            direction: 'BEARISH',
            score: -20,
            timestamp: '2026-09-17T10:05:00Z',
          },
        ],
        BANKNIFTY: null,
        SENSEX: null,
      },
    });
    render(<ForecastOutcomes instrument="NIFTY 50" horizon="1h" />);
    await flushEffects();

    expect(screen.getByText('NIFTY 50 · horizon 1h')).toBeTruthy();
    expect(screen.getByText('BULLISH')).toBeTruthy();
    expect(screen.queryByText('BEARISH')).toBeNull();
    expect(apiMock.listResearchPredictions).not.toHaveBeenCalled();
    expect(polls.length).toBe(0);
  });

  it('surfaces a degraded instrument entry instead of polling', async () => {
    sectionMock.current = sectionEnvelope(
      { by_instrument: { 'NIFTY 50': null, BANKNIFTY: null, SENSEX: null } },
      true,
    );
    render(<ForecastOutcomes instrument="NIFTY 50" horizon="1h" />);
    await flushEffects();

    expect(screen.getByText(/Predictions unavailable/)).toBeTruthy();
    expect(apiMock.listResearchPredictions).not.toHaveBeenCalled();
    expect(polls.length).toBe(0);
  });

  it('renders BANKNIFTY rows from by_instrument without reusing NIFTY rows', async () => {
    sectionMock.current = sectionEnvelope({
      by_instrument: {
        'NIFTY 50': [
          {
            prediction_id: 'nifty-1h',
            forecast_horizon: '1h',
            direction: 'BULLISH',
            score: 42,
            timestamp: '2026-09-17T10:00:00Z',
          },
        ],
        BANKNIFTY: [
          {
            prediction_id: 'bnf-1h',
            forecast_horizon: '1h',
            timeframe: '5m',
            direction: 'BEARISH',
            score: -20,
            timestamp: '2026-09-17T10:05:00Z',
          },
        ],
        SENSEX: null,
      },
    });
    render(<ForecastOutcomes instrument="BANKNIFTY" horizon="1h" />);
    await flushEffects();

    expect(screen.getByText('BEARISH')).toBeTruthy();
    expect(screen.queryByText('BULLISH')).toBeNull();
    expect(apiMock.listResearchPredictions).not.toHaveBeenCalled();
    expect(polls.length).toBe(0);
  });

  it('keeps refresh and measure user-triggered: one stream refresh per click, one measured row', async () => {
    sectionMock.current = sectionEnvelope({
      by_instrument: {
        'NIFTY 50': [
          {
            prediction_id: 'p-1',
            forecast_horizon: '1h',
            direction: 'BULLISH',
            score: 10,
            timestamp: '2026-09-17T10:00:00Z',
          },
        ],
        BANKNIFTY: null,
        SENSEX: null,
      },
    });
    render(<ForecastOutcomes instrument="NIFTY 50" horizon="1h" />);
    await flushEffects();

    expect(refreshMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
    await flushEffects();
    expect(refreshMock).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: 'Measure' }));
    await flushEffects();
    expect(apiMock.measureResearchPrediction).toHaveBeenCalledWith('p-1');
    expect(apiMock.measureResearchPrediction).toHaveBeenCalledTimes(1);
  });
});

describe('PaperPnLWidget portfolio accounting', () => {
  it('uses virtual_capital / total_* fields and per-position unrealized_pnl', async () => {
    apiMock.getPaperPortfolio.mockResolvedValue({
      data: {
        virtual_capital: 500000,
        available_margin: 400000,
        used_margin: 100000,
        margin_utilization_pct: 20,
        total_realized_pnl: 1000,
        total_unrealized_pnl: -500,
        total_portfolio_pnl: 500,
        open_positions_count: 1,
      },
    });
    const position: Partial<VirtualPosition> = {
      position_id: 'pos-1',
      symbol: 'NIFTY 24500 CE',
      side: 'BUY',
      quantity: 50,
      unrealized_pnl: -500,
      is_open: true,
    };
    apiMock.getPaperPositions.mockResolvedValue({ data: [position] });
    render(<PaperPnLWidget />);
    await flushPoll();

    expect(screen.getByText(/₹1,00,000 of ₹5,00,000 allocated/)).toBeTruthy();
    expect(screen.getByText('20.0%')).toBeTruthy();
    expect(screen.getAllByText('₹-500').length).toBe(2);
    expect(screen.queryByText(/10,00,000/)).toBeNull();
  });

  it('shows unavailable instead of zeroed numbers when the portfolio fails', async () => {
    apiMock.getPaperPortfolio.mockRejectedValue(new Error('paper service down'));
    apiMock.getPaperPositions.mockRejectedValue(new Error('paper service down'));
    render(<PaperPnLWidget />);
    await flushPoll();

    expect(screen.getByText(/Paper portfolio unavailable/)).toBeTruthy();
    expect(screen.getByText(/Positions unavailable/)).toBeTruthy();
  });
});
