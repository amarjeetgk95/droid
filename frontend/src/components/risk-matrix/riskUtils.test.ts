import { describe, expect, it } from 'vitest';
import {
  buildEquityCurve,
  finiteNumber,
  ledgerEntryPrice,
  ledgerPnl,
  signedINR,
  signedNumber,
  valueTone,
  valueToneClass,
} from './riskUtils';

describe('sign-aware formatting', () => {
  it('prefixes only positive numbers and never emits "+-"', () => {
    expect(signedNumber(0.05, 3)).toBe('+0.050');
    expect(signedNumber(-0.05, 3)).toBe('-0.050');
    expect(signedNumber(0, 3)).toBe('0.000');
    expect(signedNumber(-0, 3)).not.toContain('+');
    expect(signedNumber(Number.NaN)).toBe('—');
    expect(signedNumber(undefined)).toBe('—');
  });

  it('formats rupee values with the sign derived from the value', () => {
    expect(signedINR(2150)).toBe('+₹2,150');
    expect(signedINR(-1420)).toBe('-₹1,420');
    expect(signedINR(0)).toBe('₹0');
    expect(signedINR(null)).toBe('—');
  });

  it('treats zero and non-finite values as neutral, never green or red', () => {
    expect(valueTone(0)).toBe('flat');
    expect(valueTone(null)).toBe('flat');
    expect(valueTone(-0)).toBe('flat');
    expect(valueTone(-2)).toBe('down');
    expect(valueTone(2)).toBe('up');
    expect(valueToneClass(1)).toBe('text-up-strong');
    expect(valueToneClass(-1)).toBe('text-down-strong');
    expect(valueToneClass(0)).toBe('text-ink-2');
  });

  it('coerces Decimal-serialized strings and rejects garbage', () => {
    expect(finiteNumber('125.5')).toBe(125.5);
    expect(finiteNumber('')).toBeNull();
    expect(finiteNumber('abc')).toBeNull();
    // Exact-empty rejection only: whitespace still parses, non-strings do not.
    expect(finiteNumber('   ')).toBe(0);
    expect(finiteNumber(true)).toBeNull();
  });
});

describe('audit ledger field mapping', () => {
  it('prefers total_pnl_inr over actual_pnl_inr and nulls unavailable economics', () => {
    expect(ledgerPnl({ total_pnl_inr: 0, actual_pnl_inr: -2000 })).toBe(0);
    expect(ledgerPnl({ total_pnl_inr: -2000, actual_pnl_inr: -1500 })).toBe(-2000);
    expect(ledgerPnl({ actual_pnl_inr: 900 })).toBe(900);
    expect(ledgerPnl({ total_pnl_inr: 900, economics_unavailable: true })).toBeNull();
  });

  it('only accepts a real executed fill as the entry basis', () => {
    expect(ledgerEntryPrice({ actual_fill_price: 120.5, trigger_price: 24500 })).toBe(120.5);
    expect(ledgerEntryPrice({ trigger_price: 24500 })).toBeNull();
  });
});

describe('realized equity curve', () => {
  const settled = [
    { signal_id: 'A', actual_pnl_inr: 100, exited_at_utc: 3 },
    { signal_id: 'B', actual_pnl_inr: -300, exited_at_utc: 1 },
    { signal_id: 'C', actual_pnl_inr: 50, exited_at_utc: 2 },
  ];

  it('sorts by event time and cumulates settled P&L only', () => {
    const curve = buildEquityCurve(settled);
    expect(curve).not.toBeNull();
    expect(curve!.points.map((p) => p.signalId)).toEqual(['B', 'C', 'A']);
    expect(curve!.points.map((p) => p.cumulative)).toEqual([-300, -250, -150]);
    expect(curve!.current).toBe(-150);
    expect(curve!.peak).toBe(0);
    expect(curve!.maxDrawdown).toBe(300);
    // Peak never went positive, so a percentage drawdown would be meaningless.
    expect(curve!.maxDrawdownPct).toBeNull();
  });

  it('computes drawdown from the running high-water mark', () => {
    const curve = buildEquityCurve([
      { actual_pnl_inr: 100, exited_at_utc: 1 },
      { actual_pnl_inr: 100, exited_at_utc: 2 },
      { actual_pnl_inr: -50, exited_at_utc: 3 },
      { actual_pnl_inr: -100, exited_at_utc: 4 },
    ]);
    expect(curve!.peak).toBe(200);
    expect(curve!.maxDrawdown).toBe(150);
    expect(curve!.maxDrawdownPct).toBe(75);
  });

  it('returns null instead of padding a curve from one or zero events', () => {
    expect(buildEquityCurve([])).toBeNull();
    expect(buildEquityCurve([{ actual_pnl_inr: 100, exited_at_utc: 1 }])).toBeNull();
    expect(buildEquityCurve(settled.slice(0, 1))).toBeNull();
  });

  it('excludes economics-unavailable and unrealized-only records', () => {
    const curve = buildEquityCurve([
      { actual_pnl_inr: 100, exited_at_utc: 1 },
      { total_pnl_inr: 500, created_at_utc: 2 }, // open MTM only
      { actual_pnl_inr: 100, exited_at_utc: 3, economics_unavailable: true },
      { actual_pnl_inr: 200, exited_at_utc: 4 },
    ]);
    expect(curve!.points.map((p) => p.cumulative)).toEqual([100, 300]);
  });
});
