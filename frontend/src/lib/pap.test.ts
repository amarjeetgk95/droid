import { describe, expect, it } from 'vitest';
import {
  PAP_UNAVAILABLE_LABEL,
  alignmentBadgeClass,
  alignmentLabel,
  confidenceLabel,
  fmtAge,
  fmtPrice,
  horizonDist,
  horizonToMinutes,
  isPapUnavailable,
  papFreshnessOf,
  predictionBadgeClass,
} from './pap';
import type { PapHorizon, PapLive } from './api/pap';

const HORIZON: PapHorizon = {
  up: 68,
  neutral: 19,
  down: 13,
  prediction: 'UP',
  probability: 68,
  confidence: null,
  prediction_state: 'ACTIVE',
  model_source: 'heuristic_ensemble',
  calibrated: false,
  artifact_horizon_minutes: null,
  model_version: 'XGBoost-LightGBM-Ensemble-v1.0-heuristic',
};

function liveWith(horizons: PapLive['horizons']): PapLive {
  return {
    instrument: 'NIFTY',
    timeframe: '1 MIN',
    timestamp: new Date().toISOString(),
    price: 25000,
    data_status: 'LIVE',
    data_age_s: 4,
    available: true,
    mode: 'SHADOW',
    execution: 'DISABLED',
    horizons,
    features: null,
    market_state: null,
    evidence: [],
    droid_alignment: {
      droid_signal: null,
      pap_primary: 'UP',
      alignment: 'NO_DROID_SIGNAL',
      advisory_only: true,
    },
    horizon_consensus: { consensus: 'SHORT-TERM BULLISH', predictions: null },
    model: {
      name: 'XGBoost',
      versions: [],
      feature_schema: 'f10-v1',
      calibration: 'NOT_CALIBRATED',
      data_quality: 'GOOD',
      prediction_age_s: 4,
      status: 'VALID',
      shadow_mode: 'ACTIVE',
      execution: 'DISABLED',
    },
    calibration: { status: 'NOT_CALIBRATED', note: '' },
  };
}

describe('pap helpers', () => {
  it('renders the full probability distribution, largest first', () => {
    const dist = horizonDist(HORIZON);
    expect(dist.map((d) => d.label)).toEqual(['UP', 'NEUTRAL', 'DOWN']);
    expect(dist[0].pct).toBe(68);
    const total = dist.reduce((s, d) => s + d.pct, 0);
    expect(total).toBeGreaterThanOrEqual(99);
    expect(total).toBeLessThanOrEqual(101);
  });

  it('treats missing horizons as unavailable (never fabricates)', () => {
    expect(isPapUnavailable(null)).toBe(true);
    expect(isPapUnavailable(liveWith(null))).toBe(true);
    expect(isPapUnavailable(liveWith({ '5m': HORIZON }))).toBe(false);
    expect(PAP_UNAVAILABLE_LABEL).toBe('PAP DATA UNAVAILABLE');
  });

  it('maps backend freshness without ever upgrading stale to live', () => {
    expect(papFreshnessOf('STALE', 2)).toBe('STALE');
    expect(papFreshnessOf('LIVE', 4)).toBe('LIVE');
    expect(papFreshnessOf('UNKNOWN', null)).toBe('OFFLINE');
    expect(papFreshnessOf(null, 45)).toBe('STALE');
  });

  it('withholds confidence when the backend did not calibrate', () => {
    expect(confidenceLabel(HORIZON)).toBe('—');
    expect(confidenceLabel({ ...HORIZON, calibrated: true, confidence: 72 })).toBe('72%');
  });

  it('covers every alignment state distinctly', () => {
    expect(alignmentLabel('ALIGNED')).toBe('ALIGNED');
    expect(alignmentLabel('CONFLICT')).toBe('CONFLICT');
    expect(alignmentLabel('NO_DROID_SIGNAL')).toBe('NO DROID SIGNAL');
    expect(alignmentLabel('PAP_UNAVAILABLE')).toBe('PAP UNAVAILABLE');
    expect(new Set(['ALIGNED', 'CONFLICT', 'NEUTRAL', 'NO_DROID_SIGNAL', 'PAP_UNAVAILABLE'].map(alignmentBadgeClass)).size).toBeGreaterThanOrEqual(4);
  });

  it('badges predictions without casino language', () => {
    expect(predictionBadgeClass('UP')).toContain('bull');
    expect(predictionBadgeClass('DOWN')).toContain('bear');
    expect(predictionBadgeClass('NEUTRAL')).toContain('neut');
  });

  it('maps horizon filters to backend minutes', () => {
    expect(horizonToMinutes('3M')).toBe(3);
    expect(horizonToMinutes('5M')).toBe(5);
    expect(horizonToMinutes('10M')).toBe(10);
    expect(horizonToMinutes('ALL')).toBeUndefined();
  });

  it('formats age and price honestly', () => {
    expect(fmtAge(null)).toBe('age unknown');
    expect(fmtAge(4)).toBe('4s');
    expect(fmtPrice(null)).toBe('—');
    expect(fmtPrice(25000)).toContain('25,000');
  });
});
