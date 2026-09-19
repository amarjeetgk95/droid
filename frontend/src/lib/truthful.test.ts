import { describe, expect, it } from 'vitest';
import type {
  KeyLevelsModel,
  MarketRegimeOverview,
  PivotSetModel,
  TechnicalIndicators,
  VixRegimeInfo,
} from '@/lib/types';
import {
  confidencePct,
  finiteNum,
  hasIndicatorData,
  hasKeyLevelData,
  hasVixData,
  isStale,
  isUsableRegimeOverview,
  normalizeSymbol,
  posNum,
  provenanceLabel,
  symbolsMatch,
} from './truthful';

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
  return pivotSet({
    pivot: 0,
    r1: 0,
    r2: 0,
    r3: 0,
    r4: 0,
    s1: 0,
    s2: 0,
    s3: 0,
    s4: 0,
  });
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

const placeholderVix: VixRegimeInfo = {
  vix_value: 0,
  change: 0,
  change_percent: 0,
  regime_category: 'NORMAL_VOLATILITY',
  interpretation: 'India VIX market data currently unavailable.',
  recommended_option_strategy: 'N/A',
  historical_percentile: 50,
};

function makeOverview(overrides: Partial<MarketRegimeOverview> = {}): MarketRegimeOverview {
  return {
    symbol: 'NIFTY',
    spot_price: 22000,
    regime_state: 'TRENDING_BULLISH',
    confidence_score: 90,
    summary_headline: 'Trending Bullish — Strong Institutional Buying',
    institutional_rationale: 'Price commands above key EMAs.',
    indicators: placeholderIndicators,
    key_levels: zeroLevels,
    vix_regime: placeholderVix,
    ...overrides,
  };
}

describe('truthful numeric helpers', () => {
  it('finiteNum accepts numeric strings and rejects non-finite values', () => {
    expect(finiteNum('12.5')).toBe(12.5);
    expect(finiteNum(0)).toBe(0);
    expect(finiteNum(NaN)).toBeNull();
    expect(finiteNum(Infinity)).toBeNull();
    expect(finiteNum(null)).toBeNull();
    expect(finiteNum('abc')).toBeNull();
  });

  it('posNum treats zero and negatives as unavailable', () => {
    expect(posNum(22000)).toBe(22000);
    expect(posNum('22000')).toBe(22000);
    expect(posNum(0)).toBeNull();
    expect(posNum(-5)).toBeNull();
    expect(posNum(undefined)).toBeNull();
  });
});

describe('symbol normalization', () => {
  it('normalizes exchange prefixes and index suffixes', () => {
    expect(normalizeSymbol('NSE:NIFTY 50')).toBe('NIFTY');
    expect(normalizeSymbol('nifty')).toBe('NIFTY');
    expect(normalizeSymbol('BANKNIFTY')).toBe('BANKNIFTY');
    expect(normalizeSymbol('SENSEX')).toBe('SENSEX');
    expect(normalizeSymbol('')).toBeNull();
    expect(normalizeSymbol(null)).toBeNull();
  });

  it('symbolsMatch only matches equivalent symbols', () => {
    expect(symbolsMatch('NSE:NIFTY 50', 'NIFTY')).toBe(true);
    expect(symbolsMatch('NIFTY', 'BANKNIFTY')).toBe(false);
    expect(symbolsMatch(undefined, 'NIFTY')).toBe(false);
  });
});

describe('placeholder payload detection', () => {
  it('rejects the backend placeholder indicator payload', () => {
    expect(hasIndicatorData(placeholderIndicators)).toBe(false);
    expect(hasIndicatorData(null)).toBe(false);
  });

  it('accepts an indicator payload with real price-scale values', () => {
    expect(hasIndicatorData({ ...placeholderIndicators, atr_14: 118.4 })).toBe(true);
    expect(hasIndicatorData({ ...placeholderIndicators, ema_20: 21950 })).toBe(true);
  });

  it('rejects the placeholder VIX payload (vix_value 0)', () => {
    expect(hasVixData(placeholderVix)).toBe(false);
    expect(hasVixData({ ...placeholderVix, vix_value: 14.2 })).toBe(true);
  });

  it('rejects an all-zero key-levels payload', () => {
    expect(hasKeyLevelData(zeroLevels)).toBe(false);
    expect(hasKeyLevelData(null)).toBe(false);
    expect(hasKeyLevelData({ ...zeroLevels, day_open: 21900 })).toBe(true);
  });
});

describe('regime usability', () => {
  it('accepts a classified overview for the expected symbol', () => {
    expect(isUsableRegimeOverview(makeOverview(), 'NIFTY')).toBe(true);
    expect(isUsableRegimeOverview(makeOverview({ symbol: 'NSE:NIFTY 50' }), 'NIFTY')).toBe(true);
  });

  it('rejects unknown state, zero spot, blank headline and symbol mismatch', () => {
    expect(isUsableRegimeOverview(makeOverview({ regime_state: 'UNKNOWN' }), 'NIFTY')).toBe(false);
    expect(isUsableRegimeOverview(makeOverview({ spot_price: 0 }), 'NIFTY')).toBe(false);
    expect(isUsableRegimeOverview(makeOverview({ summary_headline: '   ' }), 'NIFTY')).toBe(false);
    expect(isUsableRegimeOverview(makeOverview({ symbol: 'BANKNIFTY' }), 'NIFTY')).toBe(false);
    expect(isUsableRegimeOverview(null, 'NIFTY')).toBe(false);
  });

  it('guards confidence bounds', () => {
    expect(confidencePct(90)).toBe(90);
    expect(confidencePct('82.4')).toBe(82);
    expect(confidencePct(0)).toBeNull();
    expect(confidencePct(180)).toBeNull();
    expect(confidencePct(undefined)).toBeNull();
  });
});

describe('provenance and staleness', () => {
  it('labels provider and snapshot time from the envelope', () => {
    const label = provenanceLabel('regime_quant_engine', '2026-09-17T04:35:12Z');
    expect(label).toContain('regime_quant_engine');
    expect(label).toContain('snapshot');
    expect(provenanceLabel('regime_quant_engine', null)).toBe('regime_quant_engine');
    expect(provenanceLabel(undefined, undefined)).toBeNull();
  });

  it('flags observations older than the staleness window', () => {
    const now = Date.now();
    expect(isStale(new Date(now - 31_000), now)).toBe(true);
    expect(isStale(new Date(now - 5_000), now)).toBe(false);
    expect(isStale(null, now)).toBe(false);
  });
});
