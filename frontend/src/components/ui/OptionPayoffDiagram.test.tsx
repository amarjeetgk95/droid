import { describe, expect, it } from 'vitest';
import { calculatePayoffAtExpiry } from './OptionPayoffDiagram';

describe('OptionPayoff calculations', () => {
  it('computes correct payoff for LONG_CALL at expiry', () => {
    const strike = 22000;
    const premium = 100;
    const lotSize = 25;

    // Below strike (OTM): max loss = premium * lotSize = -2500
    expect(calculatePayoffAtExpiry('LONG_CALL', 21500, strike, premium, lotSize)).toBe(-2500);
    expect(calculatePayoffAtExpiry('LONG_CALL', 22000, strike, premium, lotSize)).toBe(-2500);

    // At breakeven (22100): PnL = 0
    expect(calculatePayoffAtExpiry('LONG_CALL', 22100, strike, premium, lotSize)).toBe(0);

    // Above breakeven (22300): PnL = (300 - 100) * 25 = 5000
    expect(calculatePayoffAtExpiry('LONG_CALL', 22300, strike, premium, lotSize)).toBe(5000);
  });

  it('computes correct payoff for LONG_PUT at expiry', () => {
    const strike = 22000;
    const premium = 120;
    const lotSize = 25;

    // Above strike (OTM): max loss = premium * lotSize = -3000
    expect(calculatePayoffAtExpiry('LONG_PUT', 22500, strike, premium, lotSize)).toBe(-3000);
    expect(calculatePayoffAtExpiry('LONG_PUT', 22000, strike, premium, lotSize)).toBe(-3000);

    // At breakeven (21880): PnL = 0
    expect(calculatePayoffAtExpiry('LONG_PUT', 21880, strike, premium, lotSize)).toBe(0);

    // Below breakeven (21500): PnL = (500 - 120) * 25 = 9500
    expect(calculatePayoffAtExpiry('LONG_PUT', 21500, strike, premium, lotSize)).toBe(9500);
  });
});
