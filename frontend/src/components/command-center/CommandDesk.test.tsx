// @vitest-environment happy-dom
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';

const { marketMock, flag } = vi.hoisted(() => ({
  marketMock: { regimeOverview: null as unknown },
  flag: { minimal: false },
}));

vi.mock('./SystemHealthStrip', () => ({
  SystemHealthStrip: () => <div data-testid="system-health-strip" />,
}));
vi.mock('./MarketPulseBar', () => ({
  MarketPulseBar: () => <div data-testid="market-pulse-bar" />,
}));
vi.mock('./MLPredictionBadges', () => ({
  MLPredictionBadges: () => <div data-testid="ml-prediction-badges" />,
}));
vi.mock('./ActiveSignalsRibbon', () => ({
  ActiveSignalsRibbon: () => <div data-testid="active-signals-ribbon" />,
}));
vi.mock('./PaperPnLWidget', () => ({
  PaperPnLWidget: () => <div data-testid="paper-pnl-widget" />,
}));
vi.mock('@/components/dashboard/WhyStrip', () => ({
  WhyStrip: () => <div data-testid="why-strip" />,
}));
vi.mock('@/components/dashboard/ForecastOutcomes', () => ({
  ForecastOutcomes: () => <div data-testid="forecast-outcomes" />,
}));
vi.mock('@/context/InstrumentContext', () => ({
  useInstrument: () => ({ instrument: 'NIFTY', timeframe: '1h' }),
}));
vi.mock('@/context/MarketDataContext', () => ({
  useOptionalMarketDataContext: () => marketMock,
}));
vi.mock('@/context/PaperTradingContext', () => ({
  PaperTradingProvider: ({
    children,
    pollIntervalMs,
  }: {
    children: React.ReactNode;
    pollIntervalMs?: number;
  }) => (
    <div data-testid="paper-provider" data-poll-interval={pollIntervalMs}>
      {children}
    </div>
  ),
}));
vi.mock('@/lib/featureFlags', () => ({
  isMinimalUi: () => flag.minimal,
}));

import { CommandDesk } from './CommandDesk';
import CommandCenterPage from '@/app/(app)/page';

afterEach(() => {
  cleanup();
  marketMock.regimeOverview = null;
  flag.minimal = false;
});

describe('CommandDesk', () => {
  it('renders left/center/right sections with the expected children in each', () => {
    render(<CommandDesk />);

    expect(screen.getByTestId('system-health-strip')).toBeTruthy();

    const left = screen.getByRole('region', { name: 'Market and bias' });
    expect(left.contains(screen.getByTestId('market-pulse-bar'))).toBe(true);
    expect(left.contains(screen.getByTestId('ml-prediction-badges'))).toBe(true);

    const center = screen.getByRole('region', { name: 'Signals and forecast' });
    expect(center.contains(screen.getByTestId('active-signals-ribbon'))).toBe(true);
    expect(center.contains(screen.getByTestId('forecast-outcomes'))).toBe(true);

    const rail = screen.getByRole('complementary', { name: 'Context rail' });
    expect(rail.contains(screen.getByTestId('why-strip'))).toBe(true);
    expect(rail.contains(screen.getByTestId('paper-pnl-widget'))).toBe(true);
    expect(screen.getByTestId('paper-provider').getAttribute('data-poll-interval')).toBe('4000');
  });

  it('collapses and restores the context rail from the toggle button', () => {
    render(<CommandDesk />);

    fireEvent.click(screen.getByRole('button', { name: /hide context rail/i }));
    expect(screen.queryByRole('complementary', { name: 'Context rail' })).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /show context rail/i }));
    expect(screen.getByRole('complementary', { name: 'Context rail' })).toBeTruthy();
  });

  it('renders the bias summary from the shared market context when usable', () => {
    marketMock.regimeOverview = {
      symbol: 'NIFTY',
      spot_price: 24500,
      regime_state: 'TRENDING_BULLISH',
      confidence_score: 72,
      summary_headline: 'Trend intact above the rising 20 EMA.',
      institutional_rationale: 'FIIs net buyers.',
      indicators: {},
      key_levels: {},
      vix_regime: { vix_value: 13.5, regime_category: 'LOW_VOLATILITY' },
    };

    render(<CommandDesk />);

    expect(screen.getByText('Bias summary')).toBeTruthy();
    expect(screen.getByText('TRENDING BULLISH')).toBeTruthy();
    expect(screen.getByText('72% conf')).toBeTruthy();
  });

  it('omits the bias summary when the context has no usable regime', () => {
    render(<CommandDesk />);
    expect(screen.queryByText('Bias summary')).toBeNull();
  });
});

describe('CommandCenterPage flag gate', () => {
  it('default export is a component', () => {
    expect(typeof CommandCenterPage).toBe('function');
  });

  it('renders the legacy composition when the minimal UI flag is off', () => {
    render(<CommandCenterPage />);

    expect(screen.getByTestId('system-health-strip')).toBeTruthy();
    expect(screen.getByTestId('market-pulse-bar')).toBeTruthy();
    expect(screen.getByTestId('active-signals-ribbon')).toBeTruthy();
    expect(screen.getByTestId('ml-prediction-badges')).toBeTruthy();
    expect(screen.getByTestId('why-strip')).toBeTruthy();
    expect(screen.getByTestId('forecast-outcomes')).toBeTruthy();
    expect(screen.queryByRole('region', { name: 'Signals and forecast' })).toBeNull();
  });

  it('renders the Command desk when the minimal UI flag is on', () => {
    flag.minimal = true;
    render(<CommandCenterPage />);

    expect(screen.getByRole('region', { name: 'Market and bias' })).toBeTruthy();
    expect(screen.getByRole('region', { name: 'Signals and forecast' })).toBeTruthy();
    expect(screen.getByRole('complementary', { name: 'Context rail' })).toBeTruthy();
  });
});
