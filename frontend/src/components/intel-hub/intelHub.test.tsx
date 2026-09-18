// @vitest-environment happy-dom
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

const {
  getMIFullMock,
  getRegimeOverviewMock,
  getCallsPutsFullMock,
  getInstitutionalDataHealthDashboardMock,
  getFIIDIIOverviewMock,
  tripFeedCircuitMock,
  resyncFeedCircuitMock,
} = vi.hoisted(() => ({
  getMIFullMock: vi.fn(),
  getRegimeOverviewMock: vi.fn(),
  getCallsPutsFullMock: vi.fn(),
  getInstitutionalDataHealthDashboardMock: vi.fn(),
  getFIIDIIOverviewMock: vi.fn(),
  tripFeedCircuitMock: vi.fn(),
  resyncFeedCircuitMock: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  api: {
    getMIFull: getMIFullMock,
    getRegimeOverview: getRegimeOverviewMock,
    getCallsPutsFull: getCallsPutsFullMock,
    getInstitutionalDataHealthDashboard: getInstitutionalDataHealthDashboardMock,
    getFIIDIIOverview: getFIIDIIOverviewMock,
    tripFeedCircuit: tripFeedCircuitMock,
    resyncFeedCircuit: resyncFeedCircuitMock,
  },
}));

import { InstrumentProvider } from '@/context/InstrumentContext';
import { IntelHubProvider } from './IntelHubData';
import { InstrumentSelector } from './InstrumentSelector';
import { RegimePanel } from './RegimePanel';
import { EvidenceGrid } from './EvidenceGrid';
import { BreakoutMeter } from './BreakoutMeter';
import { OptionsFlowPanel } from './OptionsFlowPanel';
import { DataHealthMatrix } from './DataHealthMatrix';
import { InstitutionalFlowTicker } from './InstitutionalFlowTicker';
import { ShortHorizonCard } from './ShortHorizonCard';
import { ContinuationCard } from './ContinuationCard';

/* ───────────────────────────── fixtures ──────────────────────────────── */

function miPayload(
  instrument: string,
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    instrument_id: instrument,
    header: {
      display_name: instrument,
      price: '22100.5',
      price_formatted: '22,100.50',
      live_status: 'HEALTHY',
      session: 'OPEN',
      data_quality: 'LIVE',
      used_cache: false,
    },
    session: { is_open: true, session_type: 'OPEN', is_tradable: true, now_ist: '10:15:00' },
    feed_health: {
      health: 'HEALTHY',
      reason: null,
      circuit_state: 'CLOSED',
      staleness_ms: 800,
      is_stale: false,
      used_cache: false,
    },
    sequence: { gap_detected: false },
    market_state: {
      regime: 'TRENDING_BULLISH',
      momentum: 'STRONG',
      volatility: 'NORMAL',
      scores: { breakout_pressure: 72, breakdown_pressure: 24, false_breakout_risk: 33 },
    },
    details: { multi_timeframe: { '1m': 'BULL', '5m': 'BULL', '15m': 'BEAR' } },
    breakout: {
      direction: 'BULLISH',
      status: 'WATCH',
      confidence: 61,
      breakout_level: '22120.00',
      breakout_pressure: 72,
      breakdown_pressure: 24,
      false_breakout_risk: 33,
      breakout_quality: 67,
      reason: 'conditions partially met',
      supporting: ['MOMENTUM'],
      conflicts: ['BREADTH'],
    },
    short_horizon: {
      strategy: '10_MINUTE_TRADE',
      instrument,
      direction: 'BULLISH',
      status: 'WATCH',
      confidence: 55,
      horizon_minutes: 10,
      entry_zone: ['22100', '22120'],
      stop_loss: '22050',
      target_zone: ['22220'],
      false_breakout_risk: 33,
      reason: 'awaiting volume expansion',
    },
    continuation: {
      strategy: 'INTRADAY_CONTINUATION',
      instrument,
      direction: 'BULLISH',
      status: 'POSSIBLE',
      confidence: 48,
      max_holding_minutes: 119,
      reason: 'trend intact',
      invalidation: 'below VWAP',
    },
    evidence: {
      supporting: [
        { dimension: 'TECHNICAL', signal: 'VWAP_SUPPORT', detail: 'price above VWAP', state: 'VALID' },
      ],
      conflicting: [
        { dimension: 'BREADTH', signal: 'AD_DIVERGENCE', detail: 'breadth lagging', state: 'VALID' },
      ],
      missing: [],
      stale: [],
      invalid: [],
    },
    generated_at_ms: 1_700_000_000_000,
    ...overrides,
  };
}

function regimePayload(symbol: string) {
  return {
    data: {
      symbol,
      spot_price: 22100,
      regime_state: 'TRENDING_BULLISH',
      confidence_score: 78,
      summary_headline: `Rally in ${symbol}`,
      institutional_rationale: 'Structure and momentum aligned.',
      indicators: {
        rsi_14: 62,
        adx_14: 31.5,
        plus_di: 30,
        minus_di: 12,
        atr_14: 120,
        supertrend_value: 21900,
        supertrend_direction: 'BULLISH',
        bollinger_upper: 0,
        bollinger_middle: 0,
        bollinger_lower: 0,
        bollinger_bandwidth: 0,
        bollinger_pct_b: 0.5,
        ema_20: null,
        ema_50: null,
        sma_200: null,
      },
      key_levels: {},
      vix_regime: {},
    },
    error: null,
    meta: { provider: 'regime_quant_engine', timestamp: '2026-09-17T04:35:12Z', status: 'OFFLINE' },
  };
}

function optionsPayload() {
  return {
    underlying: 'NIFTY',
    status: 'LIVE',
    expiry: '2026-09-24',
    pcr_oi: 1.18,
    pcr_volume: 1.05,
    call_resistance: 24500,
    put_support: 24200,
    analytics: { max_pain: 24300, total_call_oi: 4_280_000, total_put_oi: 5_050_000 },
    breakout_confirmation: 'BULLISH_CONFIRMED',
  };
}

function healthPayload() {
  return {
    data_health: {
      NIFTY: { status: 'LIVE', feed: 'HEALTHY' },
      BANKNIFTY: { status: 'STALE', feed: 'FEED_DEGRADED' },
    },
    overall: { clock_sync: 'VALID', sequence: 'VALID', snapshot: 'VALID', contracts: 'VALID' },
    generated_at_ms: 1_700_000_000_000,
  };
}

function fiiPayload() {
  return {
    data: {
      timestamp: '2026-09-17T04:35:12Z',
      source: 'static_snapshot',
      as_of: '2026-08-29',
      live_available: false,
      fii_long_short_ratio: 1.26,
      fii_futures_net_contracts: 16270,
      dii_futures_net_contracts: -5600,
      client_futures_net_contracts: -12970,
      pro_futures_net_contracts: 2300,
      fii_cash_net_crores: -1234.5,
      dii_cash_net_crores: 987.6,
      institutional_sentiment: 'MILD_BULLISH',
      breakdown_by_category: [],
      recent_cash_flows: [],
    },
    error: null,
    meta: { provider: 'fii_dii', timestamp: '2026-09-17T04:35:12Z', status: 'OFFLINE' },
  };
}

const Hub: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <IntelHubProvider>{children}</IntelHubProvider>
);

function renderWithProviders(ui: React.ReactNode) {
  return render(<InstrumentProvider>{ui}</InstrumentProvider>);
}

beforeEach(() => {
  window.localStorage.clear();
  getMIFullMock.mockReset();
  getRegimeOverviewMock.mockReset();
  getCallsPutsFullMock.mockReset();
  getInstitutionalDataHealthDashboardMock.mockReset();
  getFIIDIIOverviewMock.mockReset();
  tripFeedCircuitMock.mockReset();
  resyncFeedCircuitMock.mockReset();

  getMIFullMock.mockImplementation(async (instrument: string) => miPayload(instrument));
  getRegimeOverviewMock.mockImplementation(async (symbol: string) => regimePayload(symbol));
  getCallsPutsFullMock.mockImplementation(async () => optionsPayload());
  getInstitutionalDataHealthDashboardMock.mockImplementation(async () => healthPayload());
  getFIIDIIOverviewMock.mockImplementation(async () => fiiPayload());
  tripFeedCircuitMock.mockImplementation(async () => ({ status: 'TRIPPED' }));
  resyncFeedCircuitMock.mockImplementation(async () => ({ status: 'RESYNC' }));
});

afterEach(() => cleanup());

/* ────────────────────────────── tests ────────────────────────────────── */

describe('RegimePanel', () => {
  it('renders the regime engine values and MI multi-timeframe vector', async () => {
    renderWithProviders(
      <Hub>
        <RegimePanel />
      </Hub>,
    );

    expect(await screen.findByText('TRENDING BULLISH')).toBeTruthy();
    expect(screen.getByText('78%')).toBeTruthy();
    expect(screen.getByText('1M')).toBeTruthy();
    expect(screen.getAllByText('BULL').length).toBeGreaterThan(0);
    expect(screen.getByText('BEAR')).toBeTruthy();
    expect(screen.getByText(/31\.5/)).toBeTruthy();
    expect(screen.queryByText('BULLISH EXPANSION')).toBeNull();
  });

  it('renders unavailable states instead of a fabricated trend strength', async () => {
    getRegimeOverviewMock.mockImplementation(async (symbol: string) => {
      const payload = regimePayload(symbol);
      payload.data.indicators = { ...payload.data.indicators, adx_14: 0 };
      return payload;
    });
    getMIFullMock.mockImplementation(async (instrument: string) =>
      miPayload(instrument, { details: {} }),
    );

    renderWithProviders(
      <Hub>
        <RegimePanel />
      </Hub>,
    );

    expect(await screen.findByText(/no ADX\(14\) reading/)).toBeTruthy();
    expect(await screen.findByText(/MTF alignment unavailable/)).toBeTruthy();
  });
});

describe('EvidenceGrid', () => {
  it('maps evidence.supporting/conflicting and shows error-free counts', async () => {
    renderWithProviders(
      <Hub>
        <EvidenceGrid />
      </Hub>,
    );

    expect(await screen.findByText('VWAP_SUPPORT')).toBeTruthy();
    expect(screen.getByText('AD_DIVERGENCE')).toBeTruthy();
    expect(screen.getByText('1 SUPPORTING')).toBeTruthy();
    expect(screen.getByText('1 CONFLICTING')).toBeTruthy();
  });

  it('maps the flattened supporting_evidence/conflicting_evidence shape too', async () => {
    getMIFullMock.mockImplementation(async (instrument: string) =>
      miPayload(instrument, {
        evidence: undefined,
        supporting_evidence: [
          { dimension: 'ORDER_FLOW', signal: 'CVD_POSITIVE', detail: 'delta absorbed', state: 'VALID' },
        ],
        conflicting_evidence: [
          { dimension: 'MACRO', signal: 'CRUDE_HEADWIND', detail: 'brent up', state: 'VALID' },
        ],
      }),
    );

    renderWithProviders(
      <Hub>
        <EvidenceGrid />
      </Hub>,
    );

    expect(await screen.findByText('CVD_POSITIVE')).toBeTruthy();
    expect(screen.getByText('CRUDE_HEADWIND')).toBeTruthy();
  });

  it('shows an empty state when the backend reports no evidence', async () => {
    getMIFullMock.mockImplementation(async (instrument: string) =>
      miPayload(instrument, {
        evidence: { supporting: [], conflicting: [], missing: [], stale: [], invalid: [] },
      }),
    );

    renderWithProviders(
      <Hub>
        <EvidenceGrid />
      </Hub>,
    );

    expect(
      await screen.findByText(/No supporting or conflicting evidence/),
    ).toBeTruthy();
  });
});

describe('BreakoutMeter', () => {
  it('renders the breakout engine block, never the old fabricated gauges', async () => {
    renderWithProviders(
      <Hub>
        <BreakoutMeter />
      </Hub>,
    );

    expect(await screen.findByText('WATCH')).toBeTruthy();
    expect(screen.getByText(/72\.0/)).toBeTruthy();
    expect(screen.getByText(/33\.0/)).toBeTruthy();
    expect(screen.getByText('₹22,120')).toBeTruthy();
    expect(screen.queryByText(/24390/)).toBeNull();
    expect(screen.queryByText(/24280/)).toBeNull();
    expect(screen.queryByText(/84\.0/)).toBeNull();
  });
});

describe('ShortHorizonCard / ContinuationCard', () => {
  it('binds the real short_horizon and continuation payloads', async () => {
    renderWithProviders(
      <Hub>
        <ShortHorizonCard />
        <ContinuationCard />
      </Hub>,
    );

    expect(await screen.findByText('10 min')).toBeTruthy();
    expect(screen.getByText('22100 – 22120')).toBeTruthy();
    expect(screen.getByText('22050')).toBeTruthy();
    expect(screen.getByText('awaiting volume expansion')).toBeTruthy();
    expect(screen.getByText('119 min')).toBeTruthy();
    expect(screen.getByText('trend intact')).toBeTruthy();
    expect(screen.getByText('below VWAP')).toBeTruthy();
    expect(screen.getByText('POSSIBLE')).toBeTruthy();
    expect(screen.queryByText(/TRIGGER PRIMED/)).toBeNull();
    expect(screen.queryByText(/2\.18 R/)).toBeNull();
  });

  it('renders unavailable when the horizon blocks are absent', async () => {
    getMIFullMock.mockImplementation(async (instrument: string) =>
      miPayload(instrument, { short_horizon: undefined, continuation: undefined }),
    );

    renderWithProviders(
      <Hub>
        <ShortHorizonCard />
        <ContinuationCard />
      </Hub>,
    );

    expect(await screen.findByText(/Short-horizon block missing/)).toBeTruthy();
    expect(screen.getByText(/Continuation block missing/)).toBeTruthy();
  });
});

describe('OptionsFlowPanel', () => {
  it('maps real OI fields, walls and breakout confirmation', async () => {
    renderWithProviders(
      <Hub>
        <OptionsFlowPanel />
      </Hub>,
    );

    expect(await screen.findByText('1.18')).toBeTruthy();
    expect(screen.getByText('₹24,300')).toBeTruthy();
    expect(screen.getByText('₹24,200')).toBeTruthy();
    expect(screen.getByText('₹24,500')).toBeTruthy();
    expect(screen.getByText('BULLISH_CONFIRMED')).toBeTruthy();
    expect(screen.getByText(/PUT OI: 50\.5L/)).toBeTruthy();
    expect(screen.getByText(/CALL OI: 42\.8L/)).toBeTruthy();
  });

  it('guards the bar against 0/0 OI instead of rendering NaN', async () => {
    getCallsPutsFullMock.mockImplementation(async () => ({
      ...optionsPayload(),
      analytics: { max_pain: 24300, total_call_oi: 0, total_put_oi: 0 },
    }));

    renderWithProviders(
      <Hub>
        <OptionsFlowPanel />
      </Hub>,
    );

    expect(await screen.findByText(/OI split unavailable/)).toBeTruthy();
    expect(screen.queryByRole('progressbar')).toBeNull();
  });

  it('surfaces fetch errors', async () => {
    getCallsPutsFullMock.mockImplementation(async () => {
      throw new Error('chain unavailable');
    });

    renderWithProviders(
      <Hub>
        <OptionsFlowPanel />
      </Hub>,
    );

    expect(await screen.findByText(/Options flow unavailable — chain unavailable/)).toBeTruthy();
  });
});

describe('DataHealthMatrix', () => {
  it('renders real rows, overall integrity and freshness', async () => {
    renderWithProviders(
      <Hub>
        <DataHealthMatrix />
      </Hub>,
    );

    expect(await screen.findByText('NIFTY')).toBeTruthy();
    expect(screen.getByText('HEALTHY')).toBeTruthy();
    expect(screen.getByText('FEED_DEGRADED')).toBeTruthy();
    expect(screen.getByText(/Generated/)).toBeTruthy();
    expect(screen.getByText(/Clock sync: VALID/)).toBeTruthy();
    expect(screen.queryByText(/clock_drift_ms/)).toBeNull();
  });

  it('shows no fabricated rows when the backend returns none', async () => {
    getInstitutionalDataHealthDashboardMock.mockImplementation(async () => ({
      data_health: {},
      overall: {},
      generated_at_ms: 1_700_000_000_000,
    }));

    renderWithProviders(
      <Hub>
        <DataHealthMatrix />
      </Hub>,
    );

    expect(await screen.findByText(/No instrument data-health rows/)).toBeTruthy();
  });

  it('surfaces circuit-action failures instead of swallowing them', async () => {
    tripFeedCircuitMock.mockImplementation(async () => {
      throw new Error('trip denied');
    });

    renderWithProviders(
      <Hub>
        <DataHealthMatrix />
      </Hub>,
    );

    fireEvent.click((await screen.findAllByRole('button', { name: 'Trip circuit' }))[0]);

    expect(await screen.findByText(/Circuit action failed — NIFTY: trip denied/)).toBeTruthy();
  });
});

describe('InstitutionalFlowTicker', () => {
  it('renders real values with an explicit T+1 snapshot label', async () => {
    renderWithProviders(
      <Hub>
        <InstitutionalFlowTicker />
      </Hub>,
    );

    expect(await screen.findByText('-1234.5 Cr')).toBeTruthy();
    expect(screen.getByText('+987.6 Cr')).toBeTruthy();
    expect(screen.getByText('+16270.0 contracts')).toBeTruthy();
    expect(screen.getByText('1.26')).toBeTruthy();
    expect(screen.getByText('DAILY SNAPSHOT (T+1)')).toBeTruthy();
    expect(screen.queryByText(/1420\.5/)).toBeNull();
    expect(screen.queryByText(/fii_index_options_net/)).toBeNull();
  });

  it('surfaces fetch errors', async () => {
    getFIIDIIOverviewMock.mockImplementation(async () => {
      throw new Error('fii feed down');
    });

    renderWithProviders(
      <Hub>
        <InstitutionalFlowTicker />
      </Hub>,
    );

    expect(await screen.findByText(/FII\/DII data unavailable — fii feed down/)).toBeTruthy();
  });
});

describe('InstrumentSelector & request sequencing', () => {
  it('marks the active symbol with aria-pressed and reflects real feed health', async () => {
    renderWithProviders(
      <Hub>
        <InstrumentSelector />
      </Hub>,
    );

    expect(await screen.findByText(/FEED: HEALTHY/)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'NIFTY' }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByRole('button', { name: 'BANKNIFTY' }).getAttribute('aria-pressed')).toBe(
      'false',
    );
    expect(screen.getByText(/SEQUENCE: CONTIGUOUS/)).toBeTruthy();
  });

  it('drops a late response for the previous symbol', async () => {
    const pendingNifty: { resolve: ((value: unknown) => void) | null } = { resolve: null };
    getMIFullMock.mockImplementation((instrument: string) => {
      if (instrument === 'NIFTY') {
        return new Promise((resolve) => {
          pendingNifty.resolve = resolve;
        });
      }
      return Promise.resolve(
        miPayload('BANKNIFTY', {
          evidence: {
            supporting: [
              { dimension: 'TECHNICAL', signal: 'BANK_BREADTH', detail: 'banks leading', state: 'VALID' },
            ],
            conflicting: [],
            missing: [],
            stale: [],
            invalid: [],
          },
        }),
      );
    });

    renderWithProviders(
      <Hub>
        <InstrumentSelector />
        <EvidenceGrid />
      </Hub>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'BANKNIFTY' }));

    expect(await screen.findByText('BANK_BREADTH')).toBeTruthy();
    expect(getMIFullMock).toHaveBeenCalledWith('BANKNIFTY', expect.anything());

    pendingNifty.resolve?.(miPayload('NIFTY'));
    await waitFor(() => expect(screen.queryByText('VWAP_SUPPORT')).toBeNull());
    expect(screen.getByText('BANK_BREADTH')).toBeTruthy();
  });

  it('shares a single MI poll across all MI-backed panels', async () => {
    renderWithProviders(
      <Hub>
        <RegimePanel />
        <EvidenceGrid />
        <BreakoutMeter />
        <ShortHorizonCard />
        <ContinuationCard />
      </Hub>,
    );

    expect(await screen.findByText('VWAP_SUPPORT')).toBeTruthy();
    expect(getMIFullMock).toHaveBeenCalledTimes(1);
    expect(getRegimeOverviewMock).toHaveBeenCalledTimes(1);
  });
});
