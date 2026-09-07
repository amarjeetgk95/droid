import { describe, expect, it } from 'vitest';
import { normalizeDashboardSymbol, resolveCardSymbol } from './symbols';

describe('dashboard symbol mapping', () => {
  it('normalizes aliases explicitly', () => {
    expect(normalizeDashboardSymbol('BTCUSDT')).toBe('BTCUSD');
    expect(normalizeDashboardSymbol('banknifty')).toBe('BANKNIFTY');
    expect(normalizeDashboardSymbol('garbage')).toBe('NIFTY');
    expect(normalizeDashboardSymbol(null)).toBe('NIFTY');
  });

  it('resolves card symbols by full token, not bare substring', () => {
    expect(resolveCardSymbol('NIFTY 50')).toBe('NIFTY');
    expect(resolveCardSymbol('BANKNIFTY')).toBe('BANKNIFTY');
    expect(resolveCardSymbol('SENSEX')).toBe('SENSEX');
    expect(resolveCardSymbol('BTCUSDT')).toBe('BTCUSD');
  });
});
