import { describe, expect, it } from 'vitest';
import {
  atmStrikeOf,
  buildupTone,
  chainExpiries,
  chainStrikeRows,
  futuresAvailability,
  netFlowTone,
  normalizeInstrumentKey,
  payoffStats,
  pcrNote,
  pcrTone,
  pickRegimeStreamEntry,
  regimeBadge,
  sentimentTone,
  sliceAtmWindow,
  topFlowsByVolume,
  vixBadge,
} from './optionsDesk';

describe('normalizeInstrumentKey', () => {
  it('canonicalizes display aliases', () => {
    expect(normalizeInstrumentKey('NIFTY')).toBe('NIFTY');
    expect(normalizeInstrumentKey('NIFTY 50')).toBe('NIFTY');
    expect(normalizeInstrumentKey('NIFTY BANK')).toBe('BANKNIFTY');
    expect(normalizeInstrumentKey('BANKNIFTY')).toBe('BANKNIFTY');
    expect(normalizeInstrumentKey('SENSEX')).toBe('SENSEX');
    expect(normalizeInstrumentKey(null)).toBe('NIFTY');
    expect(normalizeInstrumentKey('UNKNOWN')).toBe('NIFTY');
  });
});

describe('pickRegimeStreamEntry', () => {
  const section = {
    regime_overview: { symbol: 'NIFTY 50' },
    options_analytics: { pcr: 1.1 },
    by_symbol: {
      NIFTY: { regime_overview: { symbol: 'N' }, options_analytics: { pcr: 1.2 } },
      BANKNIFTY: { regime_overview: { symbol: 'B' }, options_analytics: null },
    },
  };

  it('prefers the by_symbol entry for the requested instrument', () => {
    const entry = pickRegimeStreamEntry(section, 'BANKNIFTY');
    expect(entry.regimeOverview).toEqual({ symbol: 'B' });
    expect(entry.optionsAnalytics).toBeNull();
  });

  it('matches the NIFTY 50 display alias', () => {
    const entry = pickRegimeStreamEntry(section, 'NIFTY 50');
    expect(entry.regimeOverview).toEqual({ symbol: 'N' });
  });

  it('falls back to top-level legs when the symbol is absent', () => {
    const entry = pickRegimeStreamEntry(section, 'SENSEX');
    expect(entry.regimeOverview).toEqual({ symbol: 'NIFTY 50' });
  });

  it('returns nulls for a missing section', () => {
    expect(pickRegimeStreamEntry(null, 'NIFTY')).toEqual({
      regimeOverview: null,
      optionsAnalytics: null,
    });
  });
});

describe('chain helpers', () => {
  const chain = {
    expiries: ['2026-09-22', 42, null],
    analytics: { atm_strike: 23350 },
    strikes: [
      { strike: 23400, is_atm: false },
      { strike: 23350, is_atm: true },
      { strike: 'bad' },
      null,
      { strike: 23300, is_atm: false },
    ],
  };

  it('extracts string expiries only', () => {
    expect(chainExpiries(chain)).toEqual(['2026-09-22']);
    expect(chainExpiries(null)).toEqual([]);
  });

  it('sorts strikes ascending and drops malformed rows', () => {
    const rows = chainStrikeRows(chain);
    expect(rows.map((r) => r.strike)).toEqual([23300, 23350, 23400]);
  });

  it('resolves ATM from analytics first', () => {
    expect(atmStrikeOf(chain, chainStrikeRows(chain))).toBe(23350);
    expect(atmStrikeOf({ strikes: [] }, [])).toBeNull();
  });

  it('slices an ATM-centred window', () => {
    const rows = chainStrikeRows(chain);
    expect(sliceAtmWindow(rows, 1).map((r) => r.strike)).toEqual([23300, 23350, 23400]);
    expect(sliceAtmWindow(rows, 0).map((r) => r.strike)).toEqual([23350]);
    expect(sliceAtmWindow(rows, null)).toHaveLength(3);
  });
});

describe('tones', () => {
  it('flags PCR extremes as warn without a directional claim', () => {
    expect(pcrTone(1.16)).toBe('neut');
    expect(pcrTone(1.8)).toBe('warn');
    expect(pcrTone(0.4)).toBe('warn');
    expect(pcrTone(null)).toBe('neut');
    expect(pcrNote(1.8)).toBe('put-heavy positioning');
    expect(pcrNote(null)).toBe('PCR unavailable');
  });

  it('maps sentiment/buildup/flow tokens', () => {
    expect(sentimentTone('STRONG_BEARISH')).toBe('bear');
    expect(sentimentTone('BULLISH')).toBe('bull');
    expect(sentimentTone('NEUTRAL')).toBe('neut');
    expect(sentimentTone('UNAVAILABLE')).toBe('neut');
    expect(buildupTone('LONG_BUILDUP')).toBe('bull');
    expect(buildupTone('SHORT_BUILDUP')).toBe('bear');
    expect(buildupTone('NEUTRAL')).toBe('neut');
    expect(netFlowTone('BULLISH')).toBe('bull');
    expect(netFlowTone('BEARISH')).toBe('bear');
  });

  it('badges regime and VIX states', () => {
    expect(regimeBadge('TRENDING_BULLISH').cls).toBe('b-bull');
    expect(regimeBadge('TRENDING_BEARISH').cls).toBe('b-bear');
    expect(regimeBadge('VOLATILE_EXPANSION').cls).toBe('b-warn');
    expect(regimeBadge('UNKNOWN').cls).toBe('b-neut');
    expect(vixBadge('LOW_VOLATILITY').cls).toBe('b-info');
    expect(vixBadge('EXTREME_VOLATILITY').cls).toBe('b-bear');
  });
});

describe('futuresAvailability', () => {
  it('treats the unwired UNAVAILABLE overview as unavailable', () => {
    const overview = {
      underlying: 'NIFTY',
      spot_price: 23346.4,
      near_future_price: null,
      basis_pts: null,
      term_structure: { underlying: 'NIFTY', curve_state: 'UNAVAILABLE', contracts: [] },
      buildup: { buildup_type: 'UNAVAILABLE' },
      rollover: { rollover_pace: 'UNAVAILABLE' },
    };
    const result = futuresAvailability(overview);
    expect(result.available).toBe(false);
    expect(result.reason).toContain('offline');
  });

  it('accepts a live overview with contracts', () => {
    const overview = {
      near_future_price: 23361.88,
      term_structure: { curve_state: 'CONTANGO', contracts: [{ expiry: '2026-09-22' }] },
    };
    expect(futuresAvailability(overview).available).toBe(true);
  });

  it('is unavailable when the payload is missing', () => {
    expect(futuresAvailability(null).available).toBe(false);
  });
});

describe('payoffStats', () => {
  it('computes max/min and zero crossings', () => {
    const curve = [
      { spot: 100, pnl: -10 },
      { spot: 110, pnl: -5 },
      { spot: 120, pnl: 5 },
      { spot: 130, pnl: 15 },
      { spot: 140, pnl: 15 },
    ];
    const stats = payoffStats(curve);
    expect(stats.points).toBe(5);
    expect(stats.maxProfit).toBe(15);
    expect(stats.maxLoss).toBe(-10);
    expect(stats.breakevens).toEqual([115]);
  });

  it('returns empty stats for malformed curves', () => {
    expect(payoffStats(null)).toEqual({ points: 0, maxProfit: null, maxLoss: null, breakevens: [] });
    expect(payoffStats([{ spot: 'x' }]).points).toBe(0);
  });
});

describe('topFlowsByVolume', () => {
  it('ranks by combined volume and caps at the limit', () => {
    const flows = [
      { strike: 1, call_volume: 10, put_volume: 0 },
      { strike: 2, call_volume: 0, put_volume: 100 },
      { strike: 'bad', call_volume: 9999, put_volume: 9999 },
    ];
    const top = topFlowsByVolume(flows, 1);
    expect(top).toHaveLength(1);
    expect(top[0].strike).toBe(2);
  });
});
