// @vitest-environment happy-dom
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { PapChartPanel } from './PapChartPanel';
import { api } from '@/lib/api';
import { markerDetail, toChartMarkers } from '@/lib/papChart';
import { chartTokens } from '@/lib/chartTheme';

vi.mock('@/lib/api', () => ({
  api: { getResearchChart: vi.fn() },
}));

vi.mock('lightweight-charts', () => ({
  createChart: vi.fn(() => ({
    addSeries: vi.fn(() => ({ setData: vi.fn() })),
    timeScale: vi.fn(() => ({ fitContent: vi.fn() })),
    subscribeCrosshairMove: vi.fn(),
  })),
  CandlestickSeries: {},
  createSeriesMarkers: vi.fn(),
}));

const CHART = {
  status: 'OK',
  reason: null,
  instrument: 'NIFTY',
  candles: [
    { time: 1700000000, open: 25000, high: 25010, low: 24990, close: 25005 },
    { time: 1700000060, open: 25005, high: 25015, low: 25000, close: 25012 },
  ],
  markers: [
    {
      time: 1700000000,
      prediction: 'UP' as const,
      horizon: '5m',
      p_up: 72,
      p_neutral: 18,
      p_down: 10,
      actual: 'UP' as const,
      correct: true,
      price_change_pct: 0.19,
      confidence: 0,
    },
  ],
};

describe('PapChartPanel', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('maps predictions to directional markers with outcome colours', () => {
    const tokens = chartTokens();
    const out = toChartMarkers(
      [
        { time: 1, prediction: 'UP', horizon: '5m', p_up: 72, p_neutral: 18, p_down: 10, actual: 'UP', correct: true, price_change_pct: 0.19, confidence: 0 },
        { time: 2, prediction: 'DOWN', horizon: '5m', p_up: 10, p_neutral: 18, p_down: 72, actual: 'UP', correct: false, price_change_pct: 0.19, confidence: 0 },
        { time: 3, prediction: 'NEUTRAL', horizon: '5m', p_up: 20, p_neutral: 60, p_down: 20, actual: null, correct: null, price_change_pct: null, confidence: 0 },
      ],
      tokens,
    );
    expect(out[0]).toMatchObject({ shape: 'arrowUp', position: 'belowBar', color: tokens.up, text: 'UP 72%' });
    expect(out[1]).toMatchObject({ shape: 'arrowDown', position: 'aboveBar', color: tokens.down });
    expect(out[2]).toMatchObject({ shape: 'circle', color: tokens.warn });
  });

  it('builds the click detail from a marker without inventing numbers', () => {
    const d = markerDetail(CHART.markers[0]);
    expect(d?.title).toBe('Prediction: UP');
    expect(d?.rows).toContainEqual(['P(UP)', '72%']);
    expect(d?.rows).toContainEqual(['Actual return', '+0.19%']);
    expect(d?.rows).toContainEqual(['Result', 'CORRECT']);
    expect(markerDetail(null)).toBeNull();
  });

  it('renders candles and markers from the backend, never synthetic', async () => {
    vi.mocked(api.getResearchChart).mockResolvedValue(CHART);
    const lw = await import('lightweight-charts');
    render(<PapChartPanel instrument="NIFTY" horizon="5M" />);
    await waitFor(() => expect(api.getResearchChart).toHaveBeenCalledWith({ instrument: 'NIFTY', horizon_minutes: 5, limit: 200 }));
    await waitFor(() => expect(vi.mocked(lw.createChart)).toHaveBeenCalled());
    await waitFor(() => expect(vi.mocked(lw.createSeriesMarkers)).toHaveBeenCalled());
    expect(screen.getByTestId('pap-chart')).toBeTruthy();
    expect(screen.queryByTestId('pap-chart-unavailable')).toBeNull();
  });

  it('shows PAP DATA UNAVAILABLE when candles are missing', async () => {
    vi.mocked(api.getResearchChart).mockResolvedValue({ ...CHART, candles: [], markers: [], status: 'INSUFFICIENT_SAMPLE', reason: 'No 1m candles.' });
    render(<PapChartPanel instrument="NIFTY" horizon="5M" />);
    await waitFor(() => expect(screen.getByTestId('pap-chart-unavailable')).toBeTruthy());
    expect(screen.getByTestId('pap-chart-unavailable').textContent).toContain('PAP DATA UNAVAILABLE');
  });
});
