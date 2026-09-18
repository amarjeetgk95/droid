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

  it('keeps the default Number("") === 0 coercion', () => {
    expect(toNumber('')).toBe(0);
    expect(toNumber('   ')).toBe(0);
  });

  it('rejectEmptyString rejects only the exact empty string', () => {
    expect(toNumber('', { rejectEmptyString: true })).toBeNull();
    expect(toNumber('   ', { rejectEmptyString: true })).toBe(0);
    expect(toNumber('42', { rejectEmptyString: true })).toBe(42);
  });

  it('rejectBlankString rejects empty and whitespace-only strings', () => {
    expect(toNumber('', { rejectBlankString: true })).toBeNull();
    expect(toNumber('   ', { rejectBlankString: true })).toBeNull();
    expect(toNumber('42', { rejectBlankString: true })).toBe(42);
  });

  it('coerceNonString parses non-string, non-number values with Number()', () => {
    expect(toNumber(true, { coerceNonString: true })).toBe(1);
    expect(toNumber([], { coerceNonString: true })).toBe(0);
    expect(toNumber({}, { coerceNonString: true })).toBeNull();
    expect(toNumber(null, { coerceNonString: true })).toBeNull();
    expect(toNumber(undefined, { coerceNonString: true })).toBeNull();
    expect(toNumber(true)).toBeNull();
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
