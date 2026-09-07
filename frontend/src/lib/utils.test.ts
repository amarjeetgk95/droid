import { describe, expect, it } from 'vitest';
import { safeInt, safeNum, safeStr, safeTime } from './utils';

describe('safe formatting helpers', () => {
  it('safeNum never crashes on null/NaN', () => {
    expect(safeNum(null)).toBe('—');
    expect(safeNum(undefined)).toBe('—');
    expect(safeNum(NaN)).toBe('—');
    expect(safeNum(Infinity)).toBe('—');
    expect(safeNum(24750.123)).toBe('24750.12');
    expect(safeNum(24750.123, '—', 0)).toBe('24750');
  });

  it('safeInt rounds and localizes', () => {
    expect(safeInt(null)).toBe('—');
    expect(safeInt(1234.6)).toBe('1,235');
  });

  it('safeStr falls back on empty', () => {
    expect(safeStr('')).toBe('—');
    expect(safeStr(undefined, 'n/a')).toBe('n/a');
    expect(safeStr('NIFTY')).toBe('NIFTY');
  });

  it('safeTime avoids Invalid Date', () => {
    expect(safeTime(null)).toBe('—');
    expect(safeTime('not-a-date')).toBe('—');
    expect(safeTime('2026-01-02T03:04:05Z')).not.toBe('—');
  });
});
