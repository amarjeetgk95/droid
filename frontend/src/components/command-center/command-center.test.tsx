// @vitest-environment happy-dom
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, act, cleanup } from '@testing-library/react';

const { apiMock, sessionMock, polls, sectionsMock, statusMock, instrumentRef, refreshMock } = vi.hoisted(() => {
  const apiMock: Record<string, ReturnType<typeof vi.fn>> = {
    getSignalsFeedHealth: vi.fn(async () => ({ states: {} })),
    getSignalsKillSwitch: vi.fn(async () => ({ active: false })),
    getBrokerTokenStatus: vi.fn(async () => ({
      data: { is_token_valid: true, provider: 'fyers', data_lag_seconds: 2 },
    })),
    getSignalsActive: vi.fn(async () => ({ signals: [] })),
    getMLPrediction: vi.fn(async () => ({ data: null })),
  };
  const sessionMock = { phase: 'OPEN', isOpen: true };
  const polls: Array<() => unknown> = [];
  const sectionsMock: { feed_health: unknown; kill_switch: unknown; ml: unknown; signals: unknown } = {
    feed_health: null,
    kill_switch: null,
    ml: null,
    signals: null,
  };
  const instrumentRef: { current: string } = { current: 'NIFTY' };
  const refreshMock = vi.fn(async () => {});
  const statusMock: {
    connected: boolean;
    lastEventAt: number | null;
    reconnects: number;
    source: 'sse' | 'fetch';
  } = {
    connected: true,
    lastEventAt: Date.parse('2026-09-18T07:22:01.000Z'),
    reconnects: 0,
    source: 'sse',
  };
  return { apiMock, sessionMock, polls, sectionsMock, statusMock, instrumentRef, refreshMock };
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
  useCommandSection: (name: string) =>
    name === 'feed_health'
      ? sectionsMock.feed_health
      : name === 'kill_switch'
        ? sectionsMock.kill_switch
        : name === 'ml'
          ? sectionsMock.ml
          : name === 'signals'
            ? sectionsMock.signals
            : null,
  useStreamStatus: () => statusMock,
  useAppStreamRefresh: () => refreshMock,
}));
vi.mock('@/context/InstrumentContext', () => ({
  useInstrument: () => ({
    instrument: instrumentRef.current,
    setInstrument: () => {},
    timeframe: '1h',
    setTimeframe: () => {},
    allInstruments: ['NIFTY', 'BANKNIFTY', 'SENSEX'],
    allTimeframes: ['1h'],
  }),
}));

import { SystemHealthStrip } from './SystemHealthStrip';
import { ActiveSignalsRibbon } from './ActiveSignalsRibbon';
import { MLPredictionBadges } from './MLPredictionBadges';

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  sessionMock.phase = 'OPEN';
  sessionMock.isOpen = true;
  polls.length = 0;
  sectionsMock.feed_health = null;
  sectionsMock.kill_switch = null;
  sectionsMock.ml = null;
  sectionsMock.signals = null;
  instrumentRef.current = 'NIFTY';
  statusMock.connected = true;
  statusMock.lastEventAt = Date.parse('2026-09-18T07:22:01.000Z');
  statusMock.source = 'sse';
});

async function flushPoll() {
  const cb = polls.at(-1);
  expect(cb).toBeTruthy();
  await act(async () => {
    await cb?.();
  });
}

function sectionEnvelope(value: unknown, degraded = false) {
  return {
    value,
    updated_at: '2026-09-18T07:22:01.000Z',
    freshness_s: 1,
    degraded,
    version: 1,
  };
}

describe('SystemHealthStrip stream consumption', () => {
  it('renders feed circuits, kill switch and broker posture from stream sections without polling', () => {
    sectionsMock.feed_health = sectionEnvelope({
      subsystems: {
        status: 'ok',
        elements: {
          central_feed: true,
          signal_worker: true,
          broker_configured: true,
          token_status: 'present',
          broker_provider_status: 'ok:fyers',
        },
        timestamp: '2026-09-18T07:22:01.000Z',
      },
      feed_circuits: {
        states: {
          NIFTY: { instrument_id: 'NIFTY', health: 'FEED_DEGRADED', reason: 'sequence gap' },
          BANKNIFTY: 'HEALTHY',
          SENSEX: {},
        },
        spot_feed: { tick_age_seconds: 7 },
        broker: { provider: 'fyers', token_status: 'present' },
      },
    });
    sectionsMock.kill_switch = sectionEnvelope({ active: false, reason: null });

    render(<SystemHealthStrip />);

    expect(screen.getByText('FEED_DEGRADED')).toBeTruthy();
    expect(screen.getByText('HEALTHY')).toBeTruthy();
    expect(screen.getAllByText('UNKNOWN').length).toBeGreaterThan(0);
    expect(screen.getByText('STANDBY')).toBeTruthy();
    expect(screen.getByText('FYERS ACTIVE')).toBeTruthy();
    expect(screen.getByText('7s')).toBeTruthy();
    expect(screen.getByText('SSE · command stream')).toBeTruthy();
    expect(apiMock.getSignalsFeedHealth).not.toHaveBeenCalled();
    expect(apiMock.getSignalsKillSwitch).not.toHaveBeenCalled();
    expect(apiMock.getBrokerTokenStatus).not.toHaveBeenCalled();
    expect(polls.length).toBe(0);
  });

  it('shows unavailable instead of healthy when the feed circuit leg is missing', () => {
    sectionsMock.feed_health = sectionEnvelope(
      {
        subsystems: {
          status: 'ok',
          elements: { token_status: 'missing', broker_provider_status: 'ok:fyers' },
          timestamp: '2026-09-18T07:22:01.000Z',
        },
        feed_circuits: null,
      },
      true,
    );

    render(<SystemHealthStrip />);

    expect(screen.getAllByText('unavailable').length).toBeGreaterThan(0);
    expect(screen.queryByText('HEALTHY')).toBeNull();
    expect(screen.getByText('REAUTH REQD')).toBeTruthy();
    expect(screen.getByText(/missing: feed circuits/)).toBeTruthy();
  });

  it('renders an active kill switch from the kill_switch section', () => {
    sectionsMock.kill_switch = sectionEnvelope({ active: true, reason: 'operator panic stop' });

    render(<SystemHealthStrip />);

    expect(screen.getByText('HALTED')).toBeTruthy();
    expect(screen.queryByText('STANDBY')).toBeNull();
  });

  it('renders unavailable, never fabricated values, before the stream has any sections', () => {
    statusMock.lastEventAt = null;

    render(<SystemHealthStrip />);

    expect(screen.getAllByText('unavailable').length).toBeGreaterThan(0);
    expect(screen.getAllByText('UNAVAILABLE').length).toBe(2);
    expect(screen.queryByText('HEALTHY')).toBeNull();
    expect(screen.queryByText('STANDBY')).toBeNull();
    expect(screen.queryByText('HALTED')).toBeNull();
  });
});

describe('ActiveSignalsRibbon safety', () => {
  it('renders real signal fields and never invents confidence', async () => {
    sectionsMock.signals = sectionEnvelope({
      signals: [
        {
          signal_id: 'sig-1',
          underlying: 'NIFTY',
          strategy: 'ORB_BREAKOUT',
          direction: 'CALL',
          fsm_state: 'ARMED',
          trigger: 24500.5,
          stop_loss: 24450,
          target_1: 24600,
          target_2: 24700,
          confidence: 0,
          data_quality: 'LIVE',
        },
      ],
      count: 1,
      data_quality: 'LIVE',
      errors: {},
      timestamp_ms: 1789716120000,
    });
    await act(async () => {
      render(<ActiveSignalsRibbon />);
    });

    expect(screen.getByText('ORB_BREAKOUT')).toBeTruthy();
    expect(screen.getByText(/Conf 0%/)).toBeTruthy();
    expect(screen.queryByText(/84%/)).toBeNull();
    expect(apiMock.getSignalsActive).not.toHaveBeenCalled();
    expect(polls.length).toBe(0);
  });

  it('blocks paper execution while the market is closed', async () => {
    sessionMock.phase = 'CLOSED';
    sessionMock.isOpen = false;
    sectionsMock.signals = sectionEnvelope({
      signals: [
        {
          signal_id: 'sig-2',
          underlying: 'NIFTY',
          strategy: 'VWAP_SCALP',
          direction: 'PUT',
          fsm_state: 'CONFIRMED',
          trigger: 24400,
          stop_loss: 24450,
          target_1: 24300,
          target_2: 24200,
          confidence: 0.72,
          data_quality: 'LIVE',
        },
      ],
      count: 1,
      data_quality: 'LIVE',
      errors: {},
      timestamp_ms: 1789716120000,
    });
    await act(async () => {
      render(<ActiveSignalsRibbon />);
    });

    expect(screen.getByText(/paper execution is blocked/i)).toBeTruthy();
    const execButton = screen.getByRole('button', { name: /Paper Exec/i });
    expect(execButton.hasAttribute('disabled')).toBe(true);
  });
});

describe('MLPredictionBadges stream consumption', () => {
  const NIFTY_PREDICTION = {
    symbol: 'NIFTY',
    timestamp: '2026-09-18T07:21:00.000Z',
    spot_price: 24500,
    bullish_pct: 55.5,
    neutral_pct: 20,
    bearish_pct: 24.5,
    confidence_score: 61.5,
    predicted_bias: 'BULLISH',
    market_regime: 'TRENDING_BULLISH',
    top_features: [],
    model_version: 'ensemble_v3',
  };

  it('renders the selected instrument from ml.value.by_symbol without polling', () => {
    sectionsMock.ml = sectionEnvelope({
      ml_prediction: null,
      by_symbol: { NIFTY: NIFTY_PREDICTION, BANKNIFTY: null, SENSEX: null },
    });
    render(<MLPredictionBadges />);

    expect(screen.getByText('BULLISH')).toBeTruthy();
    expect(screen.getByText(/61.5%/)).toBeTruthy();
    expect(screen.getByText(/BULLISH 55.5%/)).toBeTruthy();
    expect(screen.getByText(/No feature attribution reported by the model./)).toBeTruthy();
    expect(screen.queryByText(/NaN/)).toBeNull();
    expect(apiMock.getMLPrediction).not.toHaveBeenCalled();
    expect(polls.length).toBe(0);
  });

  it('says probabilities are unavailable when the map entry omits them', () => {
    sectionsMock.ml = sectionEnvelope({
      by_symbol: {
        NIFTY: { symbol: 'NIFTY', predicted_bias: 'NEUTRAL', confidence_score: 50 },
        BANKNIFTY: null,
        SENSEX: null,
      },
    });
    render(<MLPredictionBadges />);

    expect(screen.getByText(/Probability distribution unavailable./)).toBeTruthy();
    expect(screen.queryByText(/NaN/)).toBeNull();
    expect(apiMock.getMLPrediction).not.toHaveBeenCalled();
  });

  it('never shows NIFTY values under another instrument label', () => {
    instrumentRef.current = 'BANKNIFTY';
    sectionsMock.ml = sectionEnvelope({
      by_symbol: { NIFTY: NIFTY_PREDICTION, BANKNIFTY: null, SENSEX: null },
    });
    render(<MLPredictionBadges />);

    expect(screen.getByText(/No ML prediction available./)).toBeTruthy();
    expect(screen.queryByText('BULLISH')).toBeNull();

    cleanup();
    sectionsMock.ml = sectionEnvelope({
      by_symbol: {
        NIFTY: NIFTY_PREDICTION,
        BANKNIFTY: {
          ...NIFTY_PREDICTION,
          symbol: 'BANKNIFTY',
          bullish_pct: 18,
          neutral_pct: 21,
          bearish_pct: 61,
          confidence_score: 66.1,
          predicted_bias: 'BEARISH',
        },
        SENSEX: null,
      },
    });
    render(<MLPredictionBadges />);

    expect(screen.getByText('BEARISH')).toBeTruthy();
    expect(screen.getByText(/66.1%/)).toBeTruthy();
    expect(screen.queryByText('BULLISH')).toBeNull();
  });
});
