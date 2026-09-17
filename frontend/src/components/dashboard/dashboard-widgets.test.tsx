// @vitest-environment happy-dom
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, act, cleanup } from '@testing-library/react';
import type { VirtualPosition } from '@/lib/types';

const { apiMock, sessionMock, polls } = vi.hoisted(() => {
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
  return { apiMock, sessionMock, polls };
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

import { ForecastOutcomes } from './ForecastOutcomes';
import { PaperPnLWidget } from '@/components/command-center/PaperPnLWidget';

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  sessionMock.phase = 'OPEN';
  sessionMock.isOpen = true;
  polls.length = 0;
});

async function flushPoll() {
  const cb = polls.at(-1);
  expect(cb).toBeTruthy();
  await act(async () => {
    await cb?.();
  });
}

describe('ForecastOutcomes horizon filtering', () => {
  it('filters on forecast_horizon, not the chart timeframe', async () => {
    apiMock.listResearchPredictions.mockResolvedValue([
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
    ]);
    render(<ForecastOutcomes instrument="NIFTY 50" horizon="1h" />);
    await flushPoll();

    expect(screen.getByText('NIFTY 50 · horizon 1h')).toBeTruthy();
    expect(screen.getByText('BULLISH')).toBeTruthy();
    expect(screen.queryByText('BEARISH')).toBeNull();
  });

  it('surfaces fetch errors explicitly', async () => {
    apiMock.listResearchPredictions.mockRejectedValue(new Error('research service down'));
    render(<ForecastOutcomes instrument="NIFTY 50" horizon="1h" />);
    await flushPoll();

    expect(screen.getByText(/Predictions unavailable/)).toBeTruthy();
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
