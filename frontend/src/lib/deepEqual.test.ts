import { describe, expect, it } from 'vitest';
import { deepEqual } from './deepEqual';

describe('deepEqual', () => {
  it('compares primitives and references', () => {
    expect(deepEqual(1, 1)).toBe(true);
    expect(deepEqual('a', 'a')).toBe(true);
    expect(deepEqual(1, '1')).toBe(false);
    expect(deepEqual(null, null)).toBe(true);
    expect(deepEqual(null, undefined)).toBe(false);
    expect(deepEqual(undefined, undefined)).toBe(true);
    const ref = { a: 1 };
    expect(deepEqual(ref, ref)).toBe(true);
  });

  it('treats NaN as equal to NaN but not to numbers', () => {
    expect(deepEqual(NaN, NaN)).toBe(true);
    expect(deepEqual(NaN, 0)).toBe(false);
    expect(deepEqual({ x: NaN }, { x: NaN })).toBe(true);
    expect(deepEqual({ x: NaN }, { x: 1 })).toBe(false);
    expect(deepEqual([NaN, 1], [NaN, 1])).toBe(true);
  });

  it('compares Dates by value, not by enumerable keys', () => {
    expect(deepEqual(new Date(1700000000000), new Date(1700000000000))).toBe(true);
    expect(deepEqual(new Date(1700000000000), new Date(1700000000001))).toBe(false);
    expect(deepEqual(new Date(1700000000000), {})).toBe(false);
    expect(deepEqual({}, new Date(1700000000000))).toBe(false);
    expect(deepEqual(new Date(NaN), new Date(NaN))).toBe(true);
    expect(deepEqual(new Date(NaN), new Date(0))).toBe(false);
  });

  it('compares Maps by entries, order-independent', () => {
    expect(deepEqual(new Map([['a', 1]]), new Map([['a', 1]]))).toBe(true);
    expect(deepEqual(new Map([['a', 1]]), new Map([['a', 2]]))).toBe(false);
    expect(deepEqual(new Map([['a', 1]]), new Map())).toBe(false);
    expect(deepEqual(new Map([['a', 1], ['b', 2]]), new Map([['b', 2], ['a', 1]]))).toBe(true);
    expect(deepEqual(new Map([['a', { x: 1 }]]), new Map([['a', { x: 1 }]]))).toBe(true);
    expect(deepEqual(new Map(), {})).toBe(false);
  });

  it('compares Sets by entries, order-independent', () => {
    expect(deepEqual(new Set([1, 2, 3]), new Set([3, 2, 1]))).toBe(true);
    expect(deepEqual(new Set([1, 2]), new Set([1, 3]))).toBe(false);
    expect(deepEqual(new Set([1]), new Set([1, 2]))).toBe(false);
    expect(deepEqual(new Set(), new Set())).toBe(true);
    expect(deepEqual(new Set([1]), [1])).toBe(false);
  });

  it('recurses through nested arrays/objects regardless of key order', () => {
    expect(deepEqual({ a: [1, { b: 2 }] }, { a: [1, { b: 2 }] })).toBe(true);
    expect(deepEqual({ a: 1, b: 2 }, { b: 2, a: 1 })).toBe(true);
    expect(deepEqual({ a: 1 }, { a: 1, b: 2 })).toBe(false);
    expect(deepEqual({ a: 1 }, { b: 1 })).toBe(false);
    expect(deepEqual([1, 2], [1, 2, 3])).toBe(false);
    expect(deepEqual([1, 2], { 0: 1, 1: 2 })).toBe(false);
  });
});
