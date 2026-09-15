import { describe, it, expect } from 'vitest';
import { calculateSpread } from './useOptionQuotes';

describe('useOptionQuotes calculateSpread', () => {
  it('identifies missing quotes when bid/ask are null', () => {
    const res = calculateSpread(null, null, null);
    expect(res.missing).toBe(true);
    expect(res.spread).toBe(null);
  });

  it('calculates spread correctly for standard liquid option quotes', () => {
    const res = calculateSpread(120.0, 120.5, 120.25);
    expect(res.missing).toBe(false);
    expect(res.spread).toBe(0.5);
    expect(res.wide).toBe(false);
  });

  it('flags abnormally wide spreads exceeding 3% or 1.5 points', () => {
    // Bid: 100, Ask: 110, LTP: 105 (Spread = 10, threshold = max(1.5, 3.15) = 3.15)
    const res = calculateSpread(100.0, 110.0, 105.0);
    expect(res.wide).toBe(true);
    expect(res.spread).toBe(10);
  });

  it('handles inverted quotes as wide/abnormal', () => {
    const res = calculateSpread(105.0, 95.0, 100.0);
    expect(res.wide).toBe(true);
  });
});
