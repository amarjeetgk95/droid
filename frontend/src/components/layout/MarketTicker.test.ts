import { describe, expect, it } from 'vitest';
import {
  formatIndianPrice,
  formatPointsChange,
  matchBenchmarkAlias,
} from './MarketTicker';
import { IndexCard } from '@/lib/types';

describe('MarketTicker utility functions and robust normalization', () => {
  describe('formatIndianPrice', () => {
    it('formats Indian equity prices with locale separators and 2 decimal places', () => {
      expect(formatIndianPrice(23259.3)).toBe('23,259.30');
      expect(formatIndianPrice(55905.7)).toBe('55,905.70');
      expect(formatIndianPrice(74282.62)).toBe('74,282.62');
    });

    it('handles string price representations safely', () => {
      expect(formatIndianPrice('23,259.30' as unknown as number)).toBe('23,259.30');
      expect(formatIndianPrice('55905.7' as unknown as number)).toBe('55,905.70');
    });

    it('gracefully returns em-dash for zero, negative, null, or invalid prices', () => {
      expect(formatIndianPrice(0)).toBe('—');
      expect(formatIndianPrice(-10)).toBe('—');
      expect(formatIndianPrice(null)).toBe('—');
      expect(formatIndianPrice(undefined)).toBe('—');
      expect(formatIndianPrice(NaN)).toBe('—');
      expect(formatIndianPrice('invalid' as unknown as number)).toBe('—');
    });
  });

  describe('formatPointsChange', () => {
    it('prepends plus sign for positive changes', () => {
      expect(formatPointsChange(142.5)).toBe('+142.50');
      expect(formatPointsChange(0.05)).toBe('+0.05');
    });

    it('prepends minus sign for negative changes', () => {
      expect(formatPointsChange(-218.5)).toBe('-218.50');
      expect(formatPointsChange(-566.25)).toBe('-566.25');
    });

    it('formats neutral change as 0.00 without signs', () => {
      expect(formatPointsChange(0)).toBe('0.00');
      expect(formatPointsChange(0.00001)).toBe('0.00');
    });

    it('gracefully handles missing or NaN values', () => {
      expect(formatPointsChange(null)).toBe('—');
      expect(formatPointsChange(undefined)).toBe('—');
      expect(formatPointsChange(NaN)).toBe('—');
    });
  });

  describe('matchBenchmarkAlias', () => {
    const makeCard = (symbol: string, displayName?: string): IndexCard => ({
      symbol,
      display_name: displayName || symbol,
      ltp: 23000,
      change: 100,
      change_percent: 0.45,
      open: 22900,
      high: 23100,
      low: 22850,
      previous_close: 22900,
      volume: 1000000,
      open_interest: 50000,
      sparkline: [22900, 23000],
      status: 'LIVE',
      timestamp: null,
      provider: 'fyers',
    });

    it('matches NIFTY 50 across brokers without colliding with BANKNIFTY or FINNIFTY', () => {
      expect(matchBenchmarkAlias(makeCard('NIFTY 50'), 'NIFTY 50')).toBe(true);
      expect(matchBenchmarkAlias(makeCard('NSE:NIFTY50-INDEX', 'NIFTY 50'), 'NIFTY 50')).toBe(true);
      expect(matchBenchmarkAlias(makeCard('NIFTY50'), 'NIFTY 50')).toBe(true);
      expect(matchBenchmarkAlias(makeCard('NIFTY'), 'NIFTY 50')).toBe(true);

      // Must not match BANKNIFTY or FINNIFTY
      expect(matchBenchmarkAlias(makeCard('BANKNIFTY'), 'NIFTY 50')).toBe(false);
      expect(matchBenchmarkAlias(makeCard('FINNIFTY'), 'NIFTY 50')).toBe(false);
    });

    it('matches BANKNIFTY aliases', () => {
      expect(matchBenchmarkAlias(makeCard('BANKNIFTY'), 'BANKNIFTY')).toBe(true);
      expect(matchBenchmarkAlias(makeCard('NSE:NIFTYBANK-INDEX', 'NIFTY BANK'), 'BANKNIFTY')).toBe(true);
      expect(matchBenchmarkAlias(makeCard('BANK_NIFTY'), 'BANKNIFTY')).toBe(true);
      expect(matchBenchmarkAlias(makeCard('NIFTY 50'), 'BANKNIFTY')).toBe(false);
    });

    it('matches SENSEX and BSE aliases', () => {
      expect(matchBenchmarkAlias(makeCard('SENSEX'), 'SENSEX')).toBe(true);
      expect(matchBenchmarkAlias(makeCard('BSE:SENSEX-INDEX', 'SENSEX'), 'SENSEX')).toBe(true);
      expect(matchBenchmarkAlias(makeCard('BSE_SENSEX'), 'SENSEX')).toBe(true);
      expect(matchBenchmarkAlias(makeCard('NIFTY 50'), 'SENSEX')).toBe(false);
    });

    it('matches FINNIFTY, INDIA VIX, and MIDCPNIFTY', () => {
      expect(matchBenchmarkAlias(makeCard('NSE:FINNIFTY-INDEX', 'FINNIFTY'), 'FINNIFTY')).toBe(true);
      expect(matchBenchmarkAlias(makeCard('NSE:INDIAVIX-INDEX', 'INDIA VIX'), 'INDIA VIX')).toBe(true);
      expect(matchBenchmarkAlias(makeCard('NSE:MIDCPNIFTY-INDEX', 'NIFTY MIDCAP SELECT'), 'MIDCPNIFTY')).toBe(true);
    });
  });
});
