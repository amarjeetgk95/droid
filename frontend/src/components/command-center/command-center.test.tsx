// @vitest-environment happy-dom
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, act, cleanup } from '@testing-library/react';

const { apiMock, sessionMock, polls, sectionsMock, statusMock } = vi.hoisted(() => {
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
  const sectionsMock: { feed_health: unknown; kill_switch: unknown } = {
    feed_health: null,
    kill_switch: null,
  };
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
  return { apiMock, sessionMock, polls, sectionsMock, statusMock };
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
        : null,
  useStreamStatus: () => statusMock,
}));
vi.mock('@/context/InstrumentContext', () => ({
  useInstrument: () => ({
    instrument: 'NIFTY',
    setInstrument: () => {},
    timeframe: '1h',
    setTimeframe: () => {},
    allInstruments: ['NIFTY'],
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
    apiMock.getSignalsActive.mockResolvedValue({
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
    });
    render(<ActiveSignalsRibbon />);
    await flushPoll();

    expect(screen.getByText('ORB_BREAKOUT')).toBeTruthy();
    expect(screen.getByText(/Conf 0%/)).toBeTruthy();
    expect(screen.queryByText(/84%/)).toBeNull();
  });

  it('blocks paper execution while the market is closed', async () => {
    sessionMock.phase = 'CLOSED';
    sessionMock.isOpen = false;
    apiMock.getSignalsActive.mockResolvedValue({
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
        },
      ],
    });
    render(<ActiveSignalsRibbon />);
    await flushPoll();

    expect(screen.getByText(/paper execution is blocked/i)).toBeTruthy();
    const execButton = screen.getByRole('button', { name: /Paper Exec/i });
    expect(execButton.hasAttribute('disabled')).toBe(true);
  });
});

describe('MLPredictionBadges payload handling', () => {
  it('renders real probabilities and handles empty feature attribution', async () => {
    apiMock.getMLPrediction.mockResolvedValue({
      data: {
        symbol: 'NIFTY',
        timestamp: new Date().toISOString(),
        spot_price: 24500,
        bullish_pct: 55.5,
        neutral_pct: 20,
        bearish_pct: 24.5,
        confidence_score: 61.5,
        predicted_bias: 'BULLISH',
        market_regime: 'TRENDING_BULLISH',
        top_features: [],
        model_version: 'ensemble_v3',
      },
    });
    render(<MLPredictionBadges />);
    await flushPoll();

    expect(screen.getByText('BULLISH')).toBeTruthy();
    expect(screen.getByText(/61.5%/)).toBeTruthy();
    expect(screen.getByText(/BULLISH 55.5%/)).toBeTruthy();
    expect(screen.getByText(/No feature attribution reported by the model./)).toBeTruthy();
    expect(screen.queryByText(/NaN/)).toBeNull();
  });

  it('says probabilities are unavailable when the payload omits them', async () => {
    apiMock.getMLPrediction.mockResolvedValue({
      data: { symbol: 'NIFTY', predicted_bias: 'NEUTRAL', confidence_score: 50 },
    });
    render(<MLPredictionBadges />);
    await flushPoll();

    expect(screen.getByText(/Probability distribution unavailable./)).toBeTruthy();
    expect(screen.queryByText(/NaN/)).toBeNull();
  });
});
