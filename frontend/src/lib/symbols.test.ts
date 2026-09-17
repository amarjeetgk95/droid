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

  it('normalizes spaced/BSE aliases used by the backend alias map', () => {
    expect(normalizeDashboardSymbol(' BSE SENSEX ')).toBe('SENSEX');
    expect(normalizeDashboardSymbol('BANK NIFTY')).toBe('BANKNIFTY');
    expect(normalizeDashboardSymbol('NIFTY BANK')).toBe('BANKNIFTY');
    expect(normalizeDashboardSymbol('NIFTY 50')).toBe('NIFTY');
    expect(normalizeDashboardSymbol('NIFTY50')).toBe('NIFTY');
  });

  it('resolves spaced bank aliases on cards', () => {
    expect(resolveCardSymbol('BANK NIFTY')).toBe('BANKNIFTY');
    expect(resolveCardSymbol('NIFTY BANK')).toBe('BANKNIFTY');
    expect(resolveCardSymbol('BSE:SENSEX')).toBe('SENSEX');
    expect(resolveCardSymbol('NSE:NIFTY50-INDEX')).toBe('NIFTY');
  });
});
