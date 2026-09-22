import { describe, expect, it } from 'vitest';
import {
  findInstrumentCard,
  isCryptoCard,
  isNiftySymbol,
  normalizeDashboardSymbol,
  resolveCardSymbol,
  resolveIndexSymbol,
} from './symbols';

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

describe('index quote mapping', () => {
  it('resolves every feed index symbol explicitly, most specific first', () => {
    expect(resolveIndexSymbol('NIFTY 50')).toBe('NIFTY');
    expect(resolveIndexSymbol('NSE:NIFTY50-INDEX')).toBe('NIFTY');
    expect(resolveIndexSymbol('BANKNIFTY')).toBe('BANKNIFTY');
    expect(resolveIndexSymbol('NIFTY BANK')).toBe('BANKNIFTY');
    expect(resolveIndexSymbol('FINNIFTY')).toBe('FINNIFTY');
    expect(resolveIndexSymbol('Nifty Fin Service')).toBe('FINNIFTY');
    expect(resolveIndexSymbol('BSE:SENSEX-INDEX')).toBe('SENSEX');
    expect(resolveIndexSymbol('INDIA VIX')).toBe('INDIAVIX');
    expect(resolveIndexSymbol('NSE:INDIAVIX-INDEX')).toBe('INDIAVIX');
  });

  it('returns null instead of defaulting unknown symbols to NIFTY', () => {
    expect(resolveIndexSymbol('BTCUSDT')).toBeNull();
    expect(resolveIndexSymbol('RELIANCE')).toBeNull();
    expect(resolveIndexSymbol('USDINR')).toBeNull();
    expect(resolveIndexSymbol('')).toBeNull();
    expect(resolveIndexSymbol(null)).toBeNull();
  });
});

describe('shared card helpers', () => {
  it('flags crypto cards by provider or symbol suffix', () => {
    expect(isCryptoCard({ symbol: 'BTCUSDT', provider: 'binance' })).toBe(true);
    expect(isCryptoCard({ symbol: 'ETHUSDT', provider: 'fyers' })).toBe(true);
    expect(isCryptoCard({ symbol: 'NSE:NIFTY50-INDEX', provider: 'fyers' })).toBe(false);
  });

  it('finds the card for both display and dashboard tokens', () => {
    const cards = [
      { symbol: 'NSE:BANKNIFTY-INDEX' },
      { symbol: 'NIFTY 50' },
      { symbol: 'BSE:SENSEX-INDEX' },
      { symbol: 'NSE:INDIAVIX-INDEX' },
    ];
    expect(findInstrumentCard(cards, 'NIFTY 50')?.symbol).toBe('NIFTY 50');
    expect(findInstrumentCard(cards, 'NIFTY')?.symbol).toBe('NIFTY 50');
    expect(findInstrumentCard(cards, 'BANKNIFTY')?.symbol).toBe('NSE:BANKNIFTY-INDEX');
    expect(findInstrumentCard(cards, 'SENSEX')?.symbol).toBe('BSE:SENSEX-INDEX');
    expect(findInstrumentCard(cards, 'INDIAVIX')?.symbol).toBe('NSE:INDIAVIX-INDEX');
    expect(findInstrumentCard([], 'NIFTY')).toBeUndefined();
  });

  it('matches only the NIFTY regime family', () => {
    expect(isNiftySymbol('NIFTY')).toBe(true);
    expect(isNiftySymbol('NIFTY 50')).toBe(true);
    expect(isNiftySymbol('NSE:NIFTY50-INDEX')).toBe(true);
    expect(isNiftySymbol('BANKNIFTY')).toBe(false);
    expect(isNiftySymbol('SENSEX')).toBe(false);
    expect(isNiftySymbol(undefined)).toBe(false);
  });
});
