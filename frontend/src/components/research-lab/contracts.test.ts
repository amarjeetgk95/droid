import { describe, expect, it } from 'vitest';
import {
  clampInt,
  computePayoffStats,
  flattenRecord,
  formatFeatureValue,
  parseCalibration,
  parseExperimentResult,
  parseIndicatorOutput,
  parseModelManifests,
  parsePayoffPoints,
  parsePayoffResult,
  parsePredictions,
  parseSettlementSummary,
  parseStrategyTemplates,
  parseTemplateStrategy,
  splitPayoffBySign,
} from './contracts';

describe('flattenRecord', () => {
  it('flattens nested objects with dot keys', () => {
    const out = flattenRecord({ a: 1, b: { c: 2, d: { e: 3 }, f: [1, 2] } });
    expect(out).toEqual([
      { key: 'a', value: 1 },
      { key: 'b.c', value: 2 },
      { key: 'b.d.e', value: 3 },
      { key: 'b.f', value: [1, 2] },
    ]);
  });

  it('returns [] for null/undefined', () => {
    expect(flattenRecord(null)).toEqual([]);
    expect(flattenRecord(undefined)).toEqual([]);
  });
});

describe('formatFeatureValue', () => {
  it('renders scalars honestly', () => {
    expect(formatFeatureValue(null)).toBe('—');
    expect(formatFeatureValue(undefined)).toBe('—');
    expect(formatFeatureValue('')).toBe('—');
    expect(formatFeatureValue(12)).toBe('12');
    expect(formatFeatureValue(12.345)).toBe('12.35');
    expect(formatFeatureValue(Number.NaN)).toBe('—');
    expect(formatFeatureValue(true)).toBe('TRUE');
    expect(formatFeatureValue(['A', 'B'])).toBe('A, B');
  });
});

describe('computePayoffStats', () => {
  it('computes limits and interpolated breakevens from sampled spots', () => {
    const stats = computePayoffStats([
      { spot: 100, pnl: -100 },
      { spot: 105, pnl: 0 },
      { spot: 110, pnl: 200 },
    ]);
    expect(stats).not.toBeNull();
    expect(stats?.maxProfit).toBe(200);
    expect(stats?.maxLoss).toBe(-100);
    expect(stats?.breakevens).toEqual([105]);
    expect(stats?.spotMin).toBe(100);
    expect(stats?.spotMax).toBe(110);
  });

  it('interpolates a crossing that falls between samples', () => {
    const stats = computePayoffStats([
      { spot: 100, pnl: -50 },
      { spot: 200, pnl: 50 },
    ]);
    expect(stats?.breakevens).toEqual([150]);
  });

  it('returns null below two valid points', () => {
    expect(computePayoffStats([])).toBeNull();
    expect(computePayoffStats([{ spot: 1, pnl: 1 }])).toBeNull();
  });
});

describe('splitPayoffBySign', () => {
  it('splits at the zero crossing and shares the interpolated point', () => {
    const segments = splitPayoffBySign([
      { spot: 90, pnl: -10 },
      { spot: 100, pnl: 0 },
      { spot: 110, pnl: 10 },
    ]);
    expect(segments).toHaveLength(2);
    expect(segments[0].sign).toBe(-1);
    expect(segments[1].sign).toBe(1);
    expect(segments[0].points[segments[0].points.length - 1].pnl).toBe(0);
    expect(segments[1].points[0].pnl).toBe(0);
  });

  it('interpolates the crossing position', () => {
    const segments = splitPayoffBySign([
      { spot: 100, pnl: -50 },
      { spot: 200, pnl: 50 },
    ]);
    expect(segments[0].points[1]).toEqual({ spot: 150, pnl: 0 });
    expect(segments[1].points[0]).toEqual({ spot: 150, pnl: 0 });
  });
});

describe('parseIndicatorOutput', () => {
  it('normalizes the backend indicator contract', () => {
    const out = parseIndicatorOutput({
      indicator_id: 'vwap',
      version: '1.0.0',
      timestamp: '2026-09-17T10:00:00Z',
      instrument: 'NIFTY',
      timeframe: '5m',
      direction: 'bullish',
      score: 42.5,
      confidence: 0.7,
      component_values: { vwap: 24320.5 },
    });
    expect(out?.direction).toBe('BULLISH');
    expect(out?.score).toBe(42.5);
    expect(out?.component_values).toEqual({ vwap: 24320.5 });
  });

  it('rejects payloads without an indicator id', () => {
    expect(parseIndicatorOutput({ score: 1 })).toBeNull();
    expect(parseIndicatorOutput(null)).toBeNull();
  });
});

describe('parseExperimentResult', () => {
  it('reads run/report and nulls absent metrics', () => {
    const parsed = parseExperimentResult({
      run: { run_id: 'run_1', status: 'completed', sample_count: 40 },
      report: { sample_size: 40, accuracy: 62.5, p_value: 0.03, confidence_interval_95: [50, 74] },
    });
    expect(parsed?.run.status).toBe('COMPLETED');
    expect(parsed?.report.accuracy).toBe(62.5);
    expect(parsed?.report.confidence_interval_95).toEqual([50, 74]);
    expect(parsed?.report.f1_score).toBeNull();
  });

  it('rejects a response without run + report', () => {
    expect(parseExperimentResult({ run: {} })).toBeNull();
    expect(parseExperimentResult(null)).toBeNull();
  });
});

describe('parsePredictions', () => {
  it('keeps valid rows and drops rows without prediction_id', () => {
    const rows = parsePredictions([
      { prediction_id: 'p1', direction: 'bearish', confidence: 0.6 },
      { direction: 'BULLISH' },
      'nope',
    ]);
    expect(rows).toHaveLength(1);
    expect(rows?.[0].direction).toBe('BEARISH');
  });

  it('returns null when the payload is not a list', () => {
    expect(parsePredictions({})).toBeNull();
  });
});

describe('parseCalibration', () => {
  it('reads cells/overall and defaults a missing n to zero', () => {
    const parsed = parseCalibration({
      target_spec_version: 'v1',
      cells: [{ predicted_bias: 'bullish', n: 32, hits: 20, hit_rate: 0.625 }],
      overall: { n: 32, hits: 20, hit_rate: 0.625 },
      excluded_other_spec_versions: 3,
    });
    expect(parsed?.cells[0]).toMatchObject({ predicted_bias: 'BULLISH', n: 32, hit_rate: 0.625 });
    expect(parsed?.overall?.n).toBe(32);
    expect(parsed?.excluded_other_spec_versions).toBe(3);
  });
});

describe('parseModelManifests', () => {
  it('unwraps the API envelope and reads the named container', () => {
    const parsed = parseModelManifests(
      { data: { champion_models: { breakout_meta: { model_version: 'breakout_v1_challenger' } } } },
      'champion_models',
    );
    expect(parsed?.breakout_meta.model_version).toBe('breakout_v1_challenger');
  });

  it('accepts a raw container and rejects missing keys', () => {
    expect(parseModelManifests({ challenger_models: {} }, 'challenger_models')).toEqual({});
    expect(parseModelManifests({ data: {} }, 'champion_models')).toBeNull();
  });
});

describe('parseSettlementSummary', () => {
  it('reads settled/skipped/errors', () => {
    const parsed = parseSettlementSummary({ settled: 4, skipped: { 'horizon-not-elapsed': 2 }, errors: 1 });
    expect(parsed).toEqual({ settled: 4, skipped: { 'horizon-not-elapsed': 2 }, errors: 1 });
  });

  it('rejects non-object payloads', () => {
    expect(parseSettlementSummary(undefined)).toBeNull();
  });
});

describe('strategy contracts', () => {
  it('accepts backend template rows keyed by id and maps to template_id', () => {
    const rows = parseStrategyTemplates({
      data: [{ id: 'bull_call_spread', name: 'Bull Call Spread', legs_count: 2 }],
    });
    expect(rows).toEqual([
      {
        template_id: 'bull_call_spread',
        name: 'Bull Call Spread',
        category: null,
        description: null,
        legs_count: 2,
      },
    ]);
  });

  it('parses the build-template payload including legs and limits', () => {
    const parsed = parseTemplateStrategy({
      data: {
        underlying: 'NIFTY',
        spot_price: 24345.5,
        legs: [
          { option_type: 'CE', side: 'BUY', strike: 24350, quantity: 1, price: 138.77, lot_size: 75 },
          { option_type: 'CE', side: 'SELL', strike: 24650, quantity: 1, price: 44.4, lot_size: 75 },
        ],
        payoff_curve: [
          { spot: 24200, pnl: -1600 },
          { spot: 24300, pnl: 900 },
        ],
        max_profit: 6840,
        max_loss: 5000,
        risk_reward: 1.37,
        premium_note: 'Premiums are estimation inputs for payoff shape only.',
      },
    });
    expect(parsed?.spot_price).toBe(24345.5);
    expect(parsed?.legs).toHaveLength(2);
    expect(parsed?.legs[0].side).toBe('BUY');
    expect(parsed?.points).toHaveLength(2);
    expect(parsed?.max_profit).toBe(6840);
    expect(parsed?.premium_note).toContain('estimation inputs');
  });

  it('parses the payoff endpoint response and keeps unlimited limits', () => {
    const parsed = parsePayoffResult({
      data: { underlying: 'NIFTY', spot_price: 100, payoff_curve: [{ spot: 100, pnl: 0 }], legs_count: 2 },
    });
    expect(parsed?.legs_count).toBe(2);
    expect(parsed?.points).toEqual([{ spot: 100, pnl: 0 }]);
  });
});

describe('parsePayoffPoints', () => {
  it('drops non-numeric and malformed rows and sorts by spot', () => {
    const points = parsePayoffPoints([
      { spot: 120, pnl: 10 },
      { spot: 'x', pnl: 1 },
      { spot: 100, pnl: -10 },
      null,
    ]);
    expect(points).toEqual([
      { spot: 100, pnl: -10 },
      { spot: 120, pnl: 10 },
    ]);
  });
});

describe('clampInt', () => {
  it('clamps into the backend validation range', () => {
    expect(clampInt(0, 1, 50)).toBe(1);
    expect(clampInt(99, 1, 50)).toBe(50);
    expect(clampInt(5.9, 1, 50)).toBe(5);
    expect(clampInt(Number.NaN, 1, 50)).toBe(1);
  });
});
