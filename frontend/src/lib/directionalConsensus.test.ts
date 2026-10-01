import { describe, expect, it } from 'vitest';
import type { ActiveRow } from '@/lib/signalsNormalize';
import { toActiveRow } from '@/lib/signalsNormalize';
import type { HourForecast } from '@/lib/types';
import type { PapHorizon, PapLive } from '@/lib/api/pap';
import {
  DIRECTION_THRESHOLD,
  buildDirectionalConsensus,
  forecastRead,
  fuseDirectional,
  papRead,
  signalDirectionTone,
  signalsRead,
  toneOfScore,
  type DirectionalSourceRead,
} from './directionalConsensus';

const NOW = new Date('2026-09-23T09:00:00+05:30').getTime();
const TODAY_ISO = '2026-09-23T08:30:00+05:30';
const YESTERDAY_ISO = '2026-09-22T08:30:00+05:30';

function forecast(patch: Partial<HourForecast>): HourForecast {
  return {
    instrument: 'NIFTY 50',
    timeframe: '5m',
    direction: 'NEUTRAL',
    score: 0,
    confidence: 0,
    ...patch,
  };
}

function papHorizon(
  up: number,
  neutral: number,
  down: number,
  prediction: PapHorizon['prediction'],
): PapHorizon {
  return {
    up,
    neutral,
    down,
    prediction,
    probability: Math.max(up, neutral, down),
    confidence: null,
    prediction_state: 'ACTIVE',
    model_source: 'trained_ensemble',
    calibrated: false,
    artifact_horizon_minutes: 5,
    model_version: 'v1',
  };
}

function papLive(patch: Partial<PapLive>): PapLive {
  const base: PapLive = {
    instrument: 'NIFTY',
    timeframe: '1m',
    timestamp: '2026-09-23T08:59:00+05:30',
    price: 25000,
    data_status: 'LIVE',
    data_age_s: 3,
    available: true,
    mode: 'SHADOW',
    execution: 'ADVISORY',
    horizons: null,
    features: null,
    market_state: null,
    evidence: [],
    droid_alignment: {
      droid_signal: null,
      pap_primary: null,
      alignment: 'NO_DROID_SIGNAL',
      advisory_only: true,
    },
    horizon_consensus: { consensus: 'MIXED', predictions: null },
    model: {
      name: 'pap',
      versions: ['v1'],
      feature_schema: 'pap_v1',
      calibration: 'none',
      data_quality: 'LIVE',
      prediction_age_s: 3,
      status: 'VALID',
      shadow_mode: 'ON',
      execution: 'ADVISORY',
    },
    calibration: { status: 'NOT_CALIBRATED', note: '' },
  };
  return { ...base, ...patch };
}

let signalSeq = 0;
function signalRow(direction: string, state: string, createdAt = TODAY_ISO): ActiveRow {
  signalSeq += 1;
  const row = toActiveRow({
    signal_id: `sig-${signalSeq}`,
    underlying: 'NIFTY',
    direction,
    status: state,
    created_at: createdAt,
  });
  if (!row) throw new Error('failed to build test signal row');
  return row;
}

function read(
  id: DirectionalSourceRead['id'],
  tone: DirectionalSourceRead['tone'],
  score: number | null,
): DirectionalSourceRead {
  return {
    id,
    label: id,
    href: '/',
    tone,
    score,
    headline: tone.toUpperCase(),
    detail: '',
    samples: 1,
    available: score !== null,
  };
}

describe('signalDirectionTone', () => {
  it('maps call/put family tokens to a side', () => {
    expect(signalDirectionTone('LONG_CALL')).toBe('bull');
    expect(signalDirectionTone('BULLISH')).toBe('bull');
    expect(signalDirectionTone('LONG_PUT')).toBe('bear');
    expect(signalDirectionTone('BEARISH')).toBe('bear');
    expect(signalDirectionTone('SHORT')).toBe('bear');
    expect(signalDirectionTone('NEUTRAL')).toBe('neut');
    expect(signalDirectionTone(null)).toBe('neut');
  });
});

describe('toneOfScore', () => {
  it('applies the directional threshold symmetrically', () => {
    expect(toneOfScore(DIRECTION_THRESHOLD)).toBe('bull');
    expect(toneOfScore(-DIRECTION_THRESHOLD)).toBe('bear');
    expect(toneOfScore(DIRECTION_THRESHOLD - 1)).toBe('neut');
    expect(toneOfScore(null)).toBe('neut');
  });
});

describe('forecastRead', () => {
  it('exposes the horizon consensus as a signed lean', () => {
    const r = forecastRead({
      '1m': forecast({ direction: 'BULLISH' }),
      '5m': forecast({ direction: 'BULLISH' }),
      '15m': forecast({ direction: 'BEARISH' }),
      '30m': forecast({ direction: 'BULLISH' }),
      '1h': forecast({ direction: 'BULLISH' }),
    });
    expect(r.available).toBe(true);
    expect(r.tone).toBe('bull');
    expect(r.headline).toBe('BULLISH');
    expect(r.samples).toBe(5);
    expect(r.score).toBeGreaterThan(0);
  });

  it('reports no data when the board is empty', () => {
    const r = forecastRead({});
    expect(r.available).toBe(false);
    expect(r.score).toBeNull();
    expect(r.headline).toBe('NO DATA');
  });
});

describe('papRead', () => {
  it('leans bullish when UP dominance is probability-weighted', () => {
    const r = papRead(
      papLive({
        horizons: {
          '3m': papHorizon(70, 20, 10, 'UP'),
          '5m': papHorizon(60, 25, 15, 'UP'),
          '10m': papHorizon(55, 25, 20, 'UP'),
        },
      }),
    );
    expect(r.available).toBe(true);
    expect(r.tone).toBe('bull');
    expect(r.samples).toBe(3);
    expect(r.detail).toContain('3 up');
  });

  it('leans bearish when DOWN dominates', () => {
    const r = papRead(
      papLive({
        horizons: {
          '3m': papHorizon(10, 20, 70, 'DOWN'),
          '5m': papHorizon(15, 25, 60, 'DOWN'),
        },
      }),
    );
    expect(r.tone).toBe('bear');
    expect(r.score).toBeLessThan(0);
  });

  it('is unavailable without live horizons', () => {
    expect(papRead(null).available).toBe(false);
    expect(papRead(papLive({ horizons: null })).available).toBe(false);
    expect(papRead(papLive({ available: false, unavailable_reason: 'PAP offline' })).detail).toBe(
      'PAP offline',
    );
  });
});

describe('signalsRead', () => {
  it("counts today's live long/short book and ignores closed rows", () => {
    const rows = [
      signalRow('LONG_CALL', 'ARMED'),
      signalRow('LONG_CALL', 'CONFIRMED'),
      signalRow('LONG_PUT', 'TRIGGERED'),
      signalRow('LONG_PUT', 'CLOSED'),
    ];
    const r = signalsRead(rows, NOW);
    expect(r.available).toBe(true);
    expect(r.tone).toBe('bull');
    expect(r.samples).toBe(3);
    expect(r.detail).toContain('2 long');
    expect(r.detail).toContain('1 short');
  });

  it('excludes rows from a previous trading day', () => {
    const r = signalsRead([signalRow('LONG_PUT', 'ARMED', YESTERDAY_ISO)], NOW);
    expect(r.available).toBe(false);
    expect(r.headline).toBe('NO LIVE SIGNALS');
  });

  it('reports no direction when only neutral signals are live', () => {
    const r = signalsRead([signalRow('NEUTRAL', 'ARMED')], NOW);
    expect(r.available).toBe(false);
    expect(r.headline).toBe('NO DIRECTION');
    expect(r.samples).toBe(1);
  });
});

describe('fuseDirectional', () => {
  it('returns NO DATA when no source reports', () => {
    const consensus = fuseDirectional([read('forecast', 'neut', null), read('pap', 'neut', null)]);
    expect(consensus.available).toBe(false);
    expect(consensus.label).toBe('NO DATA');
    expect(consensus.alignment).toBe('NO DATA');
  });

  it('is ALIGNED when every reporting source agrees', () => {
    const consensus = fuseDirectional([
      read('forecast', 'bull', 60),
      read('signals', 'bull', 40),
      read('pap', 'bull', 50),
    ]);
    expect(consensus.label).toBe('BULLISH');
    expect(consensus.alignment).toBe('ALIGNED');
    expect(consensus.bull).toBe(3);
    expect(consensus.confidence).toBeGreaterThan(0);
  });

  it('is SPLIT when sources disagree and reports the mixed verdict honestly', () => {
    const consensus = fuseDirectional([
      read('forecast', 'bull', 80),
      read('signals', 'bear', -80),
      read('pap', 'neut', null),
    ]);
    expect(consensus.alignment).toBe('SPLIT');
    expect(consensus.bull).toBe(1);
    expect(consensus.bear).toBe(1);
  });

  it('weights the forecast board above the shadow model', () => {
    const consensus = fuseDirectional([
      read('forecast', 'bull', 100),
      read('pap', 'bear', -100),
    ]);
    // 1.2 * 100 + 0.8 * -100 = 40 over 2.0 weight => +20.
    expect(consensus.score).toBe(20);
    expect(consensus.label).toBe('BULLISH');
  });
});

describe('buildDirectionalConsensus', () => {
  it('fuses the three module reads end to end', () => {
    const { consensus, reads } = buildDirectionalConsensus({
      forecasts: {
        '1m': forecast({ direction: 'BULLISH' }),
        '5m': forecast({ direction: 'BULLISH' }),
        '15m': forecast({ direction: 'BULLISH' }),
      },
      pap: papLive({
        horizons: {
          '3m': papHorizon(70, 20, 10, 'UP'),
          '5m': papHorizon(65, 25, 10, 'UP'),
        },
      }),
      signals: [signalRow('LONG_CALL', 'ARMED'), signalRow('LONG_CALL', 'TRIGGERED')],
      nowMs: NOW,
    });

    expect(reads.map((r) => r.id)).toEqual(['forecast', 'signals', 'pap']);
    expect(consensus.available).toBe(true);
    expect(consensus.label).toBe('BULLISH');
    expect(consensus.alignment).toBe('ALIGNED');
    expect(consensus.sources).toHaveLength(3);
  });
});
