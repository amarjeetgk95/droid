import { describe, expect, it } from 'vitest';
import type { HourForecast } from '@/lib/types';
import {
  FORECAST_HORIZONS,
  confidencePct,
  consensusOf,
  directionLabel,
  directionOf,
  expectedMovePct,
  forecastInstrument,
  forecastTone,
  layerRows,
  statusClass,
} from './forecastBoard';

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

describe('forecastBoard', () => {
  it('exposes the five dashboard horizons in order', () => {
    expect(FORECAST_HORIZONS).toEqual(['1m', '5m', '15m', '30m', '1h']);
  });

  it('maps context tokens to backend instrument names', () => {
    expect(forecastInstrument('NIFTY')).toBe('NIFTY 50');
    expect(forecastInstrument('BANKNIFTY')).toBe('BANKNIFTY');
    expect(forecastInstrument('SENSEX')).toBe('SENSEX');
  });

  it('normalizes unknown directions to UNKNOWN', () => {    expect(directionOf(null)).toBe('UNKNOWN');
    expect(directionOf(forecast({ direction: undefined as unknown as HourForecast['direction'] }))).toBe('UNKNOWN');
    expect(directionOf(forecast({ direction: 'BULLISH' }))).toBe('BULLISH');
  });

  it('never paints an ABSTAIN forecast as directional', () => {
    const f = forecast({ direction: 'BULLISH', probabilities: { bullish: 0.7, neutral: 0.2, bearish: 0.1 }, status: 'ABSTAIN' });
    expect(forecastTone(f)).toBe('neut');
    expect(directionLabel(f)).toBe('ABSTAIN');
  });

  it('prefers probabilities over score for confidence', () => {
    const f = forecast({ score: 90, probabilities: { bullish: 0.62, neutral: 0.2, bearish: 0.18 } });
    expect(confidencePct(f)).toBe(62);
    const scoreOnly = forecast({ score: 61 });
    scoreOnly.confidence = undefined as unknown as number;
    expect(confidencePct(scoreOnly)).toBe(61);
    expect(confidencePct(null)).toBeNull();
  });

  it('normalizes layer scores from both percent and fraction domains', () => {
    const rows = layerRows(
      forecast({
        layer_scores: { mtf_alignment: 0.5, indicators: -40, ml: 0, options: undefined },
      }),
    );
    expect(rows.map((r) => [r.label, r.pct, r.tone])).toEqual([
      ['MTF', 50, 'bull'],
      ['IND', 40, 'bear'],
      ['ML', 0, 'neut'],
    ]);
  });

  it('computes expected move percentage from the range', () => {
    const f = forecast({ expected_range: { lower: 99, mid: 100, upper: 103 } });
    expect(expectedMovePct(f)).toBeCloseTo(4, 6);
    expect(expectedMovePct(forecast({}))).toBeNull();
  });

  it('weights the horizon consensus by horizon size', () => {
    const consensus = consensusOf({
      '1m': forecast({ direction: 'BEARISH' }),
      '5m': forecast({ direction: 'BEARISH' }),
      '15m': forecast({ direction: 'BEARISH' }),
      '30m': forecast({ direction: 'BULLISH' }),
      '1h': forecast({ direction: 'BULLISH' }),
    });
    expect(consensus.bull).toBe(2);
    expect(consensus.bear).toBe(3);
    expect(consensus.weightedScore).toBeGreaterThan(0);
    expect(consensus.tone).toBe('bull');
  });

  it('reports no data when every horizon is missing', () => {
    const consensus = consensusOf({});
    expect(consensus.label).toBe('NO DATA');
    expect(consensus.missing).toBe(5);
    expect(consensus.weightedScore).toBe(0);
  });

  it('counts abstains as neutral and not missing', () => {
    const consensus = consensusOf({
      '1m': forecast({ direction: 'BULLISH', status: 'ABSTAIN' }),
      '5m': null,
    });
    expect(consensus.neut).toBe(1);
    expect(consensus.missing).toBe(4);
  });

  it('maps statuses to chip classes', () => {
    expect(statusClass('DEGRADED')).toBe('b-warn');
    expect(statusClass('ABSTAIN')).toBe('b-neut');
    expect(statusClass('MVIG')).toBe('b-info');
    expect(statusClass('RESEARCH')).toBe('b-neut');
  });
});
