import { describe, it, expect } from 'vitest';
import { parseSignalTime, calcRiskReward, parseAutoExecuted } from './SignalFeedPanel';

describe('War Room Data Logic and Formatting', () => {
  it('correctly classifies bullish and bearish direction tokens', () => {
    const isBull = (raw: string) => {
      const u = raw.toUpperCase();
      return u.includes('BULL') || u.includes('UP') || u.includes('LONG');
    };
    const isBear = (raw: string) => {
      const u = raw.toUpperCase();
      return u.includes('BEAR') || u.includes('DOWN') || u.includes('SHORT');
    };

    expect(isBull('BULLISH')).toBe(true);
    expect(isBull('STRONG_BULL')).toBe(true);
    expect(isBull('UPTREND')).toBe(true);
    expect(isBull('BEARISH')).toBe(false);

    expect(isBear('BEARISH')).toBe(true);
    expect(isBear('DOWNTREND')).toBe(true);
    expect(isBear('SHORT_SETUP')).toBe(true);
    expect(isBear('BULLISH')).toBe(false);
  });

  it('normalizes confidence scores whether given as 0..1 or 0..100', () => {
    const normalizeConf = (c: number) => Math.round(c > 1 ? c : c * 100);

    expect(normalizeConf(0.87)).toBe(87);
    expect(normalizeConf(87)).toBe(87);
    expect(normalizeConf(0.925)).toBe(93);
    expect(normalizeConf(64)).toBe(64);
  });

  it('calculates risk-reward ratio correctly without division by zero', () => {
    const calcRR = (entry: number, stopLoss: number, target: number) => {
      const risk = Math.abs(entry - stopLoss);
      const reward = Math.abs(target - entry);
      if (risk === 0) return 1;
      return Number((reward / risk).toFixed(1));
    };

    // 25000 entry, 24950 SL (50 pts risk), 25100 Target (100 pts reward) -> 1:2.0
    expect(calcRR(25000, 24950, 25100)).toBe(2.0);
    // 50 pts risk, 75 pts reward -> 1:1.5
    expect(calcRR(25000, 24950, 25075)).toBe(1.5);
  });

  it('filters signal feeds cleanly by desk type', () => {
    const signals = [
      { id: '1', deskType: 'SCALP' },
      { id: '2', deskType: 'INTRADAY' },
      { id: '3', deskType: 'SWING' },
      { id: '4', deskType: 'SCALP' },
    ];

    const filterSignals = (list: typeof signals, filter: string) => {
      if (filter === 'ALL') return list;
      return list.filter((s) => s.deskType === filter);
    };

    expect(filterSignals(signals, 'ALL')).toHaveLength(4);
    expect(filterSignals(signals, 'SCALP')).toHaveLength(2);
    expect(filterSignals(signals, 'INTRADAY')).toHaveLength(1);
    expect(filterSignals(signals, 'SWING')).toHaveLength(1);
  });

  it('finds and centers ATM strike window for instant options chain rendering', () => {
    const strikes = Array.from({ length: 30 }, (_, i) => ({
      strike: 24000 + i * 50,
      is_atm: 24000 + i * 50 === 25000,
    }));

    const atmIdx = strikes.findIndex((s) => s.is_atm);
    expect(atmIdx).toBe(20); // 24000 + 20*50 = 25000

    const start = Math.max(0, atmIdx - 8);
    const window = strikes.slice(start, start + 17);

    expect(window).toHaveLength(17);
    expect(window.some((s) => s.is_atm)).toBe(true);
  });
});

describe('SignalFeedPanel helpers (regression)', () => {
  it('parseSignalTime prefers timestamp_ms in ms, converts seconds, falls back safely', () => {
    const ms = 1757920000000;
    expect(parseSignalTime({ timestamp_ms: ms }, 0)).toBe(ms);
    // seconds-epoch -> ms
    expect(parseSignalTime({ timestamp_ms: 1757920000 }, 0)).toBe(1757920000000);
    // timestamp field (seconds) fallback
    expect(parseSignalTime({ timestamp: 1757920000 }, 1)).toBe(1757920000000);
    // created_at ISO string
    expect(parseSignalTime({ created_at: '2024-01-02T03:04:05.000Z' }, 0)).toBe(
      new Date('2024-01-02T03:04:05.000Z').getTime(),
    );
    // empty object -> Date.now() - idx*60000 (allow small clock skew)
    const before = Date.now();
    const t = parseSignalTime({}, 2);
    expect(t).toBeLessThanOrEqual(before);
    expect(t).toBeGreaterThan(before - 2 * 60000 - 5000);
  });

  it('parseSignalTime does not blow up on numeric timestamp_ms=0 edge', () => {
    // 0 is a finite number -> converts to 0ms epoch (explicit), not the idx fallback
    expect(parseSignalTime({ timestamp_ms: 0 }, 3)).toBe(0);
  });

  it('calcRiskReward matches spec and guards zero/non-finite, caps extremes', () => {
    expect(calcRiskReward(25000, 24950, 25100)).toBe(2.0);
    expect(calcRiskReward(25000, 24950, 25075)).toBe(1.5);
    expect(calcRiskReward(100, 100, 110)).toBe(1); // risk === 0
    expect(calcRiskReward(NaN, 100, 110)).toBe(1);
    expect(calcRiskReward(100, 100.000001, 200)).toBeLessThanOrEqual(99); // capped
  });

  it('parseAutoExecuted is false by default, true only with real evidence', () => {
    expect(parseAutoExecuted({})).toBe(false);
    expect(parseAutoExecuted({ is_auto_executed: false })).toBe(false);
    expect(parseAutoExecuted({ is_auto_executed: true })).toBe(true);
    expect(parseAutoExecuted({ paper_order_id: 'PO-123' })).toBe(true);
    expect(parseAutoExecuted({ isAutoExecuted: true })).toBe(true);
  });
});
