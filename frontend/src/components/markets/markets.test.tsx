// @vitest-environment happy-dom
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import type {
  KeyLevelsModel,
  MarketRegimeOverview,
  PivotSetModel,
  TechnicalIndicators,
  VixRegimeInfo,
} from '@/lib/types';

const { getRegimeOverviewMock } = vi.hoisted(() => ({
  getRegimeOverviewMock: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  api: { getRegimeOverview: getRegimeOverviewMock },
}));

import { MarketSessionProvider } from '@/context/MarketSessionContext';
import MarketsPage from '@/app/(app)/markets/page';
import { RegimeBanner } from './RegimeBanner';
import { KeyLevelsTable } from './KeyLevelsTable';
import { IndicatorsGrid } from './IndicatorsGrid';
import { VixRegimeCard } from './VixRegimeCard';
import { MarketSessionBanner } from './MarketSessionBanner';

afterEach(() => cleanup());

const placeholderIndicators: TechnicalIndicators = {
  rsi_14: 50,
  adx_14: 0,
  plus_di: 0,
  minus_di: 0,
  atr_14: 0,
  supertrend_value: 0,
  supertrend_direction: 'BULLISH',
  bollinger_upper: 0,
  bollinger_middle: 0,
  bollinger_lower: 0,
  bollinger_bandwidth: 0,
  bollinger_pct_b: 0.5,
  ema_20: null,
  ema_50: null,
  sma_200: null,
};

const realIndicators: TechnicalIndicators = {
  rsi_14: 62.4,
  adx_14: 28.1,
  plus_di: 30.2,
  minus_di: 12.4,
  atr_14: 120.5,
  supertrend_value: 21900,
  supertrend_direction: 'BULLISH',
  bollinger_upper: 22200,
  bollinger_middle: 22000,
  bollinger_lower: 21800,
  bollinger_bandwidth: 1.82,
  bollinger_pct_b: 0.7,
  ema_20: 21850,
  ema_50: 21700,
  sma_200: 21000,
};

const placeholderVix: VixRegimeInfo = {
  vix_value: 0,
  change: 0,
  change_percent: 0,
  regime_category: 'NORMAL_VOLATILITY',
  interpretation: 'India VIX market data currently unavailable.',
  recommended_option_strategy: 'N/A',
  historical_percentile: 50,
};

const realVix: VixRegimeInfo = {
  vix_value: 14.2,
  change: -0.35,
  change_percent: -2.4,
  regime_category: 'NORMAL_VOLATILITY',
  interpretation: 'Standard volatility environment.',
  recommended_option_strategy: 'Bull Put Spreads',
  historical_percentile: 46,
};

function pivotSet(overrides: Partial<PivotSetModel> = {}): PivotSetModel {
  return {
    pivot: 22000,
    r1: 22200,
    r2: 22400,
    r3: 22600,
    r4: 22800,
    s1: 21800,
    s2: 21600,
    s3: 21400,
    s4: 21200,
    ...overrides,
  };
}

function zeroPivotSet(): PivotSetModel {
  return pivotSet({ pivot: 0, r1: 0, r2: 0, r3: 0, r4: 0, s1: 0, s2: 0, s3: 0, s4: 0 });
}

const zeroLevels: KeyLevelsModel = {
  classic_pivots: zeroPivotSet(),
  fibonacci_pivots: zeroPivotSet(),
  camarilla_pivots: zeroPivotSet(),
  prior_day_high: 0,
  prior_day_low: 0,
  prior_day_close: 0,
  day_open: 0,
  poc: 0,
  vah: 0,
  val: 0,
  nearest_resistance: 0,
  nearest_support: 0,
  distance_to_resistance_pts: 0,
  distance_to_support_pts: 0,
};

const realLevels: KeyLevelsModel = {
  classic_pivots: pivotSet({ r1: 22300, r2: 22400, s1: 21600, s2: 21500 }),
  fibonacci_pivots: pivotSet({ r1: 22600, r2: 22005, s1: 21500, s2: 21000 }),
  camarilla_pivots: pivotSet({ r1: 22800, r2: 22650, s1: 21800, s2: 21995 }),
  prior_day_high: 22500,
  prior_day_low: 21500,
  prior_day_close: 21900,
  day_open: 21850,
  poc: 22010,
  vah: 22100,
  val: 21900,
  nearest_resistance: 22005,
  nearest_support: 21995,
  distance_to_resistance_pts: 5,
  distance_to_support_pts: 5,
};

function makeOverview(
  symbol: string,
  overrides: Partial<MarketRegimeOverview> = {},
): MarketRegimeOverview {
  return {
    symbol,
    spot_price: 22000,
    regime_state: 'TRENDING_BULLISH',
    confidence_score: 90,
    summary_headline: `Rally in ${symbol}`,
    institutional_rationale: 'Structure and momentum aligned.',
    indicators: realIndicators,
    key_levels: realLevels,
    vix_regime: realVix,
    ...overrides,
  };
}

describe('RegimeBanner states', () => {
  it('renders the diagnosis when a usable overview matches the selected symbol', () => {
    render(<RegimeBanner overview={makeOverview('NIFTY')} selectedSymbol="NIFTY" status="ready" />);
    expect(screen.getByText('Rally in NIFTY')).toBeTruthy();
    expect(screen.getByText(/90% conf/)).toBeTruthy();
    expect(screen.getByText('BULLISH')).toBeTruthy();
  });

  it('renders a distinct loading state instead of an endless diagnosis', () => {
    render(<RegimeBanner overview={null} selectedSymbol="NIFTY" status="loading" />);
    expect(screen.getByText('DIAGNOSING')).toBeTruthy();
    expect(screen.getByText(/Computing regime/)).toBeTruthy();
  });

  it('renders a distinct error state with the failure message', () => {
    render(
      <RegimeBanner
        overview={null}
        selectedSymbol="NIFTY"
        status="error"
        errorMessage="Cannot reach backend at 127.0.0.1:8000"
      />,
    );
    expect(screen.getByText('FEED ERROR')).toBeTruthy();
    expect(screen.getByText(/Cannot reach backend/)).toBeTruthy();
  });

  it('renders market closed explicitly, not as a generic error', () => {
    render(
      <RegimeBanner
        overview={null}
        selectedSymbol="NIFTY"
        status="closed"
        sessionNote="Opens next trading day 09:15 IST"
      />,
    );
    expect(screen.getByText('MARKET CLOSED')).toBeTruthy();
    expect(screen.getByText(/Opens next trading day 09:15 IST/)).toBeTruthy();
    expect(screen.queryByText('FEED ERROR')).toBeNull();
  });

  it('renders the provider placeholder payload as no data, not as a signal', () => {
    const placeholder = makeOverview('NIFTY', {
      spot_price: 0,
      regime_state: 'UNKNOWN',
      confidence_score: 0,
      summary_headline: 'Broker Feed Disconnected / No Market Data',
    });
    render(<RegimeBanner overview={placeholder} selectedSymbol="NIFTY" status="ready" />);
    expect(screen.getByText('NO REGIME DATA')).toBeTruthy();
    expect(screen.getByText(/Broker Feed Disconnected/)).toBeTruthy();
  });

  it('never renders a headline echoed for a different symbol', () => {
    render(<RegimeBanner overview={makeOverview('BANKNIFTY')} selectedSymbol="NIFTY" status="ready" />);
    expect(screen.queryByText('Rally in BANKNIFTY')).toBeNull();
    expect(screen.getByText('NO REGIME DATA')).toBeTruthy();
    expect(screen.getByText(/No usable regime diagnosis returned for NIFTY/)).toBeTruthy();
  });
});

describe('KeyLevelsTable', () => {
  it('renders R4/S4 for classic and fib sets, not only Camarilla', () => {
    const levels: KeyLevelsModel = {
      ...realLevels,
      classic_pivots: pivotSet({ r4: 22900, s4: 21100 }),
      fibonacci_pivots: pivotSet({ r4: 23100, s4: 20900 }),
      camarilla_pivots: pivotSet({ r4: null, s4: null }),
    };
    render(<KeyLevelsTable keyLevels={levels} spotPrice={22000} />);
    const r4Row = screen.getByText('Resistance 4').closest('tr') as HTMLElement;
    expect(within(r4Row).getByText('₹22,900')).toBeTruthy();
    expect(within(r4Row).getByText('₹23,100')).toBeTruthy();
    const s4Row = screen.getByText('Support 4').closest('tr') as HTMLElement;
    expect(within(s4Row).getByText('₹21,100')).toBeTruthy();
    expect(within(s4Row).getByText('₹20,900')).toBeTruthy();
  });

  it('computes the nearest badge across classic, fib and Camarilla values', () => {
    render(<KeyLevelsTable keyLevels={realLevels} spotPrice={22000} />);
    const r2Cell = screen.getByText('Resistance 2').closest('td') as HTMLElement;
    expect(within(r2Cell).getByText('Nearest R')).toBeTruthy();
    expect(screen.getAllByText('Nearest R')).toHaveLength(1);
    const s2Cell = screen.getByText('Support 2').closest('td') as HTMLElement;
    expect(within(s2Cell).getByText('Nearest S')).toBeTruthy();
    expect(screen.getAllByText('Nearest S')).toHaveLength(1);
  });

  it('surfaces day open in the reference block', () => {
    render(<KeyLevelsTable keyLevels={realLevels} spotPrice={22000} />);
    const row = screen.getByText('Day open').closest('tr') as HTMLElement;
    expect(within(row).getByText('₹21,850')).toBeTruthy();
  });

  it('treats an all-zero payload as unavailable', () => {
    render(<KeyLevelsTable keyLevels={zeroLevels} spotPrice={0} />);
    expect(screen.getByText(/placeholder levels/)).toBeTruthy();
  });
});

describe('IndicatorsGrid', () => {
  it('treats placeholder indicators as unavailable instead of live signals', () => {
    render(
      <IndicatorsGrid
        indicators={placeholderIndicators}
        spotPrice={0}
        provenance="regime_quant_engine · snapshot 10:05:12"
      />,
    );
    expect(screen.getByText(/placeholder indicator values/)).toBeTruthy();
    expect(screen.queryByText('Bullish zone')).toBeNull();
    expect(screen.queryByText('BULLISH')).toBeNull();
    expect(screen.getByText(/regime_quant_engine/)).toBeTruthy();
  });

  it('renders readings with provenance when real indicator data exists', () => {
    render(
      <IndicatorsGrid
        indicators={realIndicators}
        spotPrice={22000}
        provenance="regime_quant_engine · snapshot 10:05:12"
      />,
    );
    expect(screen.getByText(/Bullish zone/)).toBeTruthy();
    expect(screen.getByText(/Strong trend/)).toBeTruthy();
    expect(screen.getByText('BULLISH')).toBeTruthy();
    expect(screen.getByText(/regime_quant_engine/)).toBeTruthy();
  });
});

describe('VixRegimeCard', () => {
  it('treats the zero/placeholder VIX payload as unavailable', () => {
    render(<VixRegimeCard vixInfo={placeholderVix} provenance="regime_quant_engine" />);
    expect(screen.getByText(/placeholder value/)).toBeTruthy();
    expect(screen.queryByText('NORMAL VOLATILITY')).toBeNull();
    expect(screen.queryByText(/Playbook/)).toBeNull();
  });

  it('renders a real VIX regime with provenance', () => {
    render(<VixRegimeCard vixInfo={realVix} provenance="regime_quant_engine · snapshot 10:05:12" />);
    expect(screen.getByText('NORMAL VOLATILITY')).toBeTruthy();
    expect(screen.getByText('14.20')).toBeTruthy();
    expect(screen.getByText(/Bull Put Spreads/)).toBeTruthy();
    expect(screen.getByText(/regime_quant_engine/)).toBeTruthy();
  });
});

describe('MarketSessionBanner', () => {
  it('labels an open session and shows freshness provenance', () => {
    render(
      <MarketSessionBanner
        phase="OPEN"
        sessionTimeIST="10:00:00 IST"
        nextSessionChange="Closes in 5h 30m"
        lastAt={null}
        fetching={false}
        marketClosed={false}
        provider="regime_quant_engine"
      />,
    );
    expect(screen.getByText('OPEN')).toBeTruthy();
    expect(screen.getByText(/Closes in 5h 30m/)).toBeTruthy();
    expect(screen.getByText(/regime_quant_engine/)).toBeTruthy();
  });

  it('labels a closed session explicitly', () => {
    render(
      <MarketSessionBanner
        phase="CLOSED"
        sessionTimeIST="18:00:00 IST"
        nextSessionChange="Opens next trading day 09:15 IST"
        lastAt={null}
        fetching={false}
        marketClosed
      />,
    );
    expect(screen.getByText('CLOSED')).toBeTruthy();
    expect(screen.getByText(/market closed/)).toBeTruthy();
  });
});

describe('MarketsPage', () => {
  beforeEach(() => {
    getRegimeOverviewMock.mockReset();
    getRegimeOverviewMock.mockImplementation(async (sym: string) => ({
      data: makeOverview(sym),
      error: null,
      meta: {
        provider: 'regime_quant_engine',
        timestamp: '2026-09-17T04:35:12Z',
        status: 'OFFLINE',
      },
    }));
  });

  it('polls getRegimeOverview and swaps symbols without a stale headline', async () => {
    render(
      <MarketSessionProvider>
        <MarketsPage />
      </MarketSessionProvider>,
    );

    expect(await screen.findByText('Rally in NIFTY')).toBeTruthy();
    expect(getRegimeOverviewMock).toHaveBeenCalledWith('NIFTY');

    fireEvent.click(screen.getByRole('button', { name: 'BANKNIFTY' }));

    expect(await screen.findByText('Rally in BANKNIFTY')).toBeTruthy();
    expect(screen.queryByText('Rally in NIFTY')).toBeNull();
    expect(getRegimeOverviewMock).toHaveBeenCalledWith('BANKNIFTY');
  });

  it('renders unavailable panes when the regime endpoint returns no data', async () => {
    getRegimeOverviewMock.mockImplementation(async () => ({ data: null, error: null, meta: null }));
    render(
      <MarketSessionProvider>
        <MarketsPage />
      </MarketSessionProvider>,
    );

    expect(await screen.findByText('No key levels or pivot points available.')).toBeTruthy();
    expect(screen.getByText('No technical indicators available.')).toBeTruthy();
    expect(screen.getByText('No India VIX volatility regime data available.')).toBeTruthy();
  });
});
