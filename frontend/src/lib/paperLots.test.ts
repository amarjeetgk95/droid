import { describe, expect, it } from 'vitest';
import { strikeStepFor, syntheticStrikes, buildOptionSymbol, lotSizeFor } from './paperLots';

describe('paper ticket ladder helpers', () => {
  it('strikeStepFor matches the chain step per underlying', () => {
    expect(strikeStepFor('NIFTY')).toBe(50);
    expect(strikeStepFor('BANKNIFTY')).toBe(100);
    expect(strikeStepFor('FINNIFTY')).toBe(100);
    expect(strikeStepFor('SENSEX')).toBe(100);
  });

  it('syntheticStrikes builds an ATM-centred ladder with no manual input', () => {
    const ladder = syntheticStrikes(24812, 50);
    expect(ladder).toContain(24800);
    expect(ladder.length).toBe(11);
    expect([...ladder].sort((a, b) => a - b)).toEqual(ladder);
    expect(ladder[1] - ladder[0]).toBe(50);
  });

  it('syntheticStrikes rejects non-positive centers', () => {
    expect(syntheticStrikes(0, 50)).toEqual([]);
    expect(syntheticStrikes(-5, 100)).toEqual([]);
  });

  it('buildOptionSymbol derives the contract from dropdown state', () => {
    expect(buildOptionSymbol('NIFTY', 24800, 'CE')).toBe('NIFTY24800CE');
    expect(buildOptionSymbol('BANKNIFTY', 55250.6, 'PE')).toBe('BANKNIFTY55251PE');
    expect(lotSizeFor('NIFTY')).toBe(75);
  });
});
