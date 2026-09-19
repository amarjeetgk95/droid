import { describe, expect, it } from 'vitest';
import {
  badgeClass,
  circuitStates,
  countOpenCircuits,
  fmtCell,
  kvEntries,
  parseNumField,
  subsystemEntries,
  summarizeBreaker,
  summarizeCache,
  tagClass,
  toneForBreaker,
  toneForSession,
  toneForStatus,
} from './opsDesk';

describe('toneForStatus', () => {
  it('maps healthy tokens to bull', () => {
    expect(toneForStatus('ok')).toBe('bull');
    expect(toneForStatus('HEALTHY')).toBe('bull');
    expect(toneForStatus('LIVE')).toBe('bull');
  });
  it('maps failure tokens to bear', () => {
    expect(toneForStatus('TRIPPED')).toBe('bear');
    expect(toneForStatus('down')).toBe('bear');
    expect(toneForStatus('UNAVAILABLE')).toBe('bear');
  });
  it('maps degraded tokens to warn', () => {
    expect(toneForStatus('DEGRADED')).toBe('warn');
    expect(toneForStatus('STALE')).toBe('warn');
    expect(toneForStatus('OFFLINE')).toBe('warn');
  });
  it('falls back to neut for unknown/null', () => {
    expect(toneForStatus('WEEKEND')).toBe('neut');
    expect(toneForStatus(null)).toBe('neut');
    expect(toneForStatus(undefined)).toBe('neut');
    expect(toneForStatus('something-new')).toBe('neut');
  });
});

describe('toneForSession / toneForBreaker', () => {
  it('open session is bull, closed is neut', () => {
    expect(toneForSession('OPEN')).toBe('bull');
    expect(toneForSession('CLOSED')).toBe('neut');
    expect(toneForSession('PRE_OPEN')).toBe('info');
  });
  it('breaker CLOSED is bull, OPEN is bear, HALF_OPEN is warn', () => {
    expect(toneForBreaker('CLOSED')).toBe('bull');
    expect(toneForBreaker('OPEN')).toBe('bear');
    expect(toneForBreaker('HALF_OPEN')).toBe('warn');
  });
  it('badge/tag class helpers prefix correctly', () => {
    expect(badgeClass('bull')).toBe('b-bull');
    expect(tagClass('warn')).toBe('warn');
  });
});

describe('fmtCell / kvEntries', () => {
  it('renders scalars and placeholders', () => {
    expect(fmtCell(null)).toBe('—');
    expect(fmtCell('')).toBe('—');
    expect(fmtCell(true)).toBe('true');
    expect(fmtCell('ok')).toBe('ok');
    expect(fmtCell(Number.NaN)).toBe('—');
  });
  it('skips nested objects in kvEntries', () => {
    const entries = kvEntries({ a: 1, nested: { x: 1 }, b: 'hi' });
    expect(entries).toEqual([
      ['a', '1'],
      ['b', 'hi'],
    ]);
  });
  it('returns [] for null', () => {
    expect(kvEntries(null)).toEqual([]);
  });
});

describe('summarizeCache / summarizeBreaker', () => {
  it('reads live backend shapes', () => {
    const cache = summarizeCache({
      backend: 'in_memory_lru',
      items_count: 4,
      max_capacity: 50000,
      hit_ratio_percent: 44.74,
      hit_count: 119,
      miss_count: 147,
      eviction_count: 0,
    });
    expect(cache.items).toBe(4);
    expect(cache.hitRatio).toBe(44.74);
    expect(cache.evictions).toBe(0);
  });
  it('reads breaker shape', () => {
    const breaker = summarizeBreaker({
      name: 'fyers',
      state: 'CLOSED',
      failure_count: 0,
      failure_threshold: 5,
      total_calls: 10,
      tripped_count: 0,
    });
    expect(breaker.state).toBe('CLOSED');
    expect(breaker.threshold).toBe(5);
  });
  it('tolerates hostile input', () => {
    expect(summarizeCache('nope').items).toBeNull();
    expect(summarizeBreaker(null).state).toBeNull();
  });
});

describe('circuitStates / countOpenCircuits', () => {
  it('reads REST feed-health states map', () => {
    const states = circuitStates({ status: 'x', states: { NIFTY: 'CLOSED', BANKNIFTY: 'OPEN' } });
    expect(states).toEqual([
      ['NIFTY', 'CLOSED'],
      ['BANKNIFTY', 'OPEN'],
    ]);
    expect(countOpenCircuits(states)).toBe(1);
  });
  it('reads stream feed_circuits envelope', () => {
    const states = circuitStates({ feed_circuits: { states: { NIFTY: 'OK' } } });
    expect(states).toEqual([['NIFTY', 'OK']]);
    expect(countOpenCircuits(states)).toBe(0);
  });
  it('returns [] when no state map exists', () => {
    expect(circuitStates({ status: 'ok' })).toEqual([]);
    expect(circuitStates(null)).toEqual([]);
  });
});

describe('subsystemEntries', () => {
  it('maps booleans to on/off tones', () => {
    const entries = subsystemEntries({ elements: { server: true, central_feed: false, token_status: 'present' } });
    expect(entries[0]).toEqual(['server', 'on', 'bull']);
    expect(entries[1]).toEqual(['central feed', 'off', 'neut']);
    expect(entries[2][0]).toBe('token status');
  });
  it('returns [] for missing elements', () => {
    expect(subsystemEntries({})).toEqual([]);
  });
});

describe('parseNumField', () => {
  it('parses numbers, blanks to null', () => {
    expect(parseNumField(' 12.5 ')).toBe(12.5);
    expect(parseNumField('')).toBeNull();
    expect(parseNumField('   ')).toBeNull();
    expect(parseNumField('abc')).toBeNull();
  });
});
