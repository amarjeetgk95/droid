import { describe, expect, it } from 'vitest';
import {
  countManifests,
  directionToneOf,
  mlProbs,
  probToPct,
  shadowDecision,
  summarizeForecastSection,
  toAnnotationSummary,
  toIndicatorSummary,
  toPredictionSummary,
  toSnapshotSummary,
  unwrapMlData,
} from './labDesk';

describe('labDesk', () => {
  it('maps direction tones', () => {
    expect(directionToneOf('BULLISH')).toBe('bull');
    expect(directionToneOf('bearish')).toBe('bear');
    expect(directionToneOf('NEUTRAL')).toBe('neut');
    expect(directionToneOf(null)).toBe('neut');
  });

  it('normalizes indicator rows defensively', () => {
    expect(toIndicatorSummary(null)).toBeNull();
    expect(toIndicatorSummary({})).toBeNull();
    const row = toIndicatorSummary({ indicator_id: 'rsi_mom', category: 'momentum' });
    expect(row?.id).toBe('rsi_mom');
    expect(row?.name).toBe('rsi_mom');
  });

  it('normalizes prediction rows defensively', () => {
    const row = toPredictionSummary({
      prediction_id: 'p1',
      direction: 'BULLISH',
      confidence: 0.7,
      score: 12,
    });
    expect(row?.id).toBe('p1');
    expect(row?.confidence).toBe(0.7);
    expect(toPredictionSummary({})).toBeNull();
  });

  it('normalizes snapshots and annotations', () => {
    expect(toSnapshotSummary({ snapshot_id: 's1', price: 100 })?.price).toBe(100);
    expect(toSnapshotSummary({})).toBeNull();
    expect(toAnnotationSummary({ annotation_id: 'a1', title: 't' })?.title).toBe('t');
    expect(toAnnotationSummary(null)).toBeNull();
  });

  it('unwraps ML envelopes and reads probs', () => {
    expect(unwrapMlData(null)).toBeNull();
    const data = unwrapMlData({ data: { bullish_prob: 0.6 }, error: null });
    expect(data?.bullish_prob).toBe(0.6);
    expect(mlProbs(data)).toMatchObject({ bull: 0.6 });
    expect(probToPct(0.6)).toBe(60);
    expect(probToPct(60)).toBe(60);
    expect(probToPct(null)).toBeNull();
  });

  it('counts manifests and reads shadow decisions', () => {
    expect(countManifests({ challenger_models: { a: {}, b: {} } }, 'challenger_models')).toBe(2);
    expect(countManifests(null, 'challenger_models')).toBe(0);
    expect(shadowDecision({ shadow_decision: { recommendation: 'PASS' } }).tone).toBe('bull');
    expect(shadowDecision({ shadow_decision: { recommendation: 'VETO' } }).tone).toBe('bear');
  });

  it('summarizes forecast sections without fabricating', () => {
    expect(summarizeForecastSection(null)).toMatchObject({ count: 0 });
    const s = summarizeForecastSection({
      predictions: [{ direction: 'BULLISH' }, { direction: 'BEARISH' }, {}],
    });
    expect(s.count).toBe(3);
    expect(s.bull).toBe(1);
    expect(s.bear).toBe(1);
  });
});
