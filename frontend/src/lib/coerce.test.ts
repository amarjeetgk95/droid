import { describe, expect, it } from 'vitest';
import { pickFirst, toNumber } from './coerce';

describe('toNumber', () => {
  it('coerces finite numbers and numeric strings', () => {
    expect(toNumber('42.5')).toBe(42.5);
    expect(toNumber(7)).toBe(7);
  });

  it('returns null for non-finite or non-numeric values', () => {
    expect(toNumber('abc')).toBeNull();
    expect(toNumber(Number.NaN)).toBeNull();
    expect(toNumber(Infinity)).toBeNull();
    expect(toNumber(null)).toBeNull();
    expect(toNumber(undefined)).toBeNull();
    expect(toNumber({})).toBeNull();
  });
});

describe('pickFirst', () => {
  it('mirrors ?? precedence: the first non-nullish candidate wins', () => {
    expect(pickFirst(null, undefined, 'x')).toBe('x');
    expect(pickFirst('present', 'other')).toBe('present');
    expect(pickFirst(0, 5)).toBe(0);
    expect(pickFirst<string | number>('garbage', 3)).toBe('garbage');
    expect(pickFirst(null, null)).toBeNull();
  });
});
