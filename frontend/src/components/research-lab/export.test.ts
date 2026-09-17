import { describe, expect, it } from 'vitest';
import { scalarToString, toCsv } from './export';

describe('scalarToString', () => {
  it('renders null/undefined as empty and objects as JSON', () => {
    expect(scalarToString(null)).toBe('');
    expect(scalarToString(undefined)).toBe('');
    expect(scalarToString('a')).toBe('a');
    expect(scalarToString(3)).toBe('3');
    expect(scalarToString(false)).toBe('false');
    expect(scalarToString({ a: 1 })).toBe('{"a":1}');
  });
});

describe('toCsv', () => {
  it('builds a header from the union of row keys', () => {
    const csv = toCsv([
      { a: 1, b: 'x' },
      { a: 2, c: true },
    ]);
    expect(csv).toBe('a,b,c\r\n1,x,\r\n2,,true');
  });

  it('quotes values containing commas, quotes or newlines', () => {
    const csv = toCsv([{ note: 'a,b', quote: 'say "hi"' }], ['note', 'quote']);
    expect(csv).toBe('note,quote\r\n"a,b","say ""hi"""');
  });

  it('respects an explicit column order', () => {
    const csv = toCsv([{ a: 1, b: 2 }], ['b', 'a']);
    expect(csv).toBe('b,a\r\n2,1');
  });

  it('returns an empty string for no rows', () => {
    expect(toCsv([])).toBe('');
  });
});
