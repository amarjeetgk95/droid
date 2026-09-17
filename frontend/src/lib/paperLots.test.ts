import { describe, expect, it } from 'vitest';
import { strikeStepFor, syntheticStrikes, buildOptionSymbol, lotSizeFor, estimateMarginLocal } from './paperLots';

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

  it('syntheticStrikes returns exactly the requested count, including even/zero counts', () => {
    expect(syntheticStrikes(100, 10, 4)).toEqual([90, 100, 110, 120]);
    expect(syntheticStrikes(100, 10, 4)).toHaveLength(4);
    expect(syntheticStrikes(100, 10, 1)).toEqual([100]);
    expect(syntheticStrikes(100, 10, 0)).toEqual([]);
    expect(syntheticStrikes(100, 10, -3)).toEqual([]);
  });

  it('syntheticStrikes rejects non-positive centers and invalid steps', () => {
    expect(syntheticStrikes(0, 50)).toEqual([]);
    expect(syntheticStrikes(-5, 100)).toEqual([]);
    expect(syntheticStrikes(NaN, 50)).toEqual([]);
    expect(syntheticStrikes(100, NaN)).toEqual([]);
    expect(syntheticStrikes(100, 0)).toEqual([]);
  });

  it('buildOptionSymbol derives the contract from dropdown state', () => {
    expect(buildOptionSymbol('NIFTY', 24800, 'CE')).toBe('NIFTY24800CE');
    expect(buildOptionSymbol('BANKNIFTY', 55250.6, 'PE')).toBe('BANKNIFTY55251PE');
    expect(lotSizeFor('NIFTY')).toBe(75);
  });

  it('estimateMarginLocal prices option buys and short margins', () => {
    expect(
      estimateMarginLocal({ symbol: 'NIFTY24800CE', underlying: 'NIFTY', side: 'BUY', price: 150, quantity: 75 }),
    ).toEqual({ requiredMargin: 11250, premium: 11250 });

    // Above the index floor the price is spot, so estimate ~1.5% ATM premium.
    expect(
      estimateMarginLocal({ symbol: 'NIFTY24800CE', underlying: 'NIFTY', side: 'BUY', price: 24800, quantity: 75 }),
    ).toEqual({ requiredMargin: 27900, premium: 27900 });

    expect(
      estimateMarginLocal({ symbol: 'NIFTY24800PE', underlying: 'NIFTY', side: 'SELL', price: 150, quantity: 75 }),
    ).toEqual({ requiredMargin: 125000, premium: 0 });
  });

  it('estimateMarginLocal never leaks NaN from bad inputs', () => {
    const optionBuy = estimateMarginLocal({
      symbol: 'NIFTY24800CE',
      underlying: 'NIFTY',
      side: 'BUY',
      price: NaN,
      quantity: NaN,
    });
    expect(optionBuy).toEqual({ requiredMargin: 0, premium: 0 });

    const optionSell = estimateMarginLocal({
      symbol: 'NIFTY24800PE',
      underlying: 'NIFTY',
      side: 'SELL',
      price: NaN,
      quantity: NaN,
    });
    expect(optionSell).toEqual({ requiredMargin: 125000, premium: 0 });
    expect(Number.isFinite(optionSell.requiredMargin)).toBe(true);
  });
});
