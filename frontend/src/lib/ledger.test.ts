import { describe, expect, it } from 'vitest';
import type { PortfolioSummary, VirtualPosition } from '@/lib/types';
import {
  computePaperTotals,
  fmtInr,
  isOpenPosition,
  pnlClass,
  positionNotional,
  positionUnrealized,
} from './ledger';

function position(patch: Partial<VirtualPosition>): VirtualPosition {
  return {
    position_id: 'p1',
    symbol: 'NIFTY25OCT25000CE',
    underlying: 'NIFTY',
    instrument_type: 'OPTION',
    side: 'BUY',
    product: 'INTRADAY',
    quantity: 75,
    average_price: 100,
    ltp: 120,
    unrealized_pnl: 1500,
    realized_pnl: 0,
    used_margin: 5000,
    is_open: true,
    ...patch,
  };
}

const portfolio: PortfolioSummary = {
  virtual_capital: 1_000_000,
  available_margin: 900_000,
  used_margin: 100_000,
  margin_utilization_pct: 10,
  total_realized_pnl: -2_000,
  total_unrealized_pnl: 3_000,
  total_portfolio_pnl: 1_000,
  open_positions_count: 2,
};

describe('paper ledger math', () => {
  it('derives unrealized P&L when the backend omits it', () => {
    const p = position({ unrealized_pnl: undefined as unknown as number, ltp: 90 });
    expect(positionUnrealized(p)).toBe(-750);
  });

  it('inverts P&L for short positions', () => {
    const p = position({ side: 'SELL', unrealized_pnl: undefined as unknown as number, ltp: 90 });
    expect(positionUnrealized(p)).toBe(750);
  });

  it('trusts portfolio totals when present', () => {
    const totals = computePaperTotals(portfolio, [position({}), position({ position_id: 'p2', unrealized_pnl: 100 })]);
    expect(totals.realized).toBe(-2_000);
    expect(totals.unrealized).toBe(3_000);
    expect(totals.total).toBe(1_000);
    expect(totals.openCount).toBe(2);
  });

  it('falls back to row sums when the portfolio is unavailable', () => {
    const totals = computePaperTotals(null, [
      position({ unrealized_pnl: 100, realized_pnl: 50 }),
      position({ position_id: 'p2', unrealized_pnl: -40, realized_pnl: 0 }),
    ]);
    expect(totals.unrealized).toBe(60);
    expect(totals.realized).toBe(50);
    expect(totals.total).toBe(110);
    expect(totals.capital).toBeNull();
  });

  it('excludes closed positions from open counts and unrealized fallback', () => {
    const totals = computePaperTotals(null, [
      position({}),
      position({ position_id: 'p2', is_open: false, unrealized_pnl: 999 }),
    ]);
    expect(totals.openCount).toBe(1);
    expect(totals.unrealized).toBe(1500);
    expect(isOpenPosition(position({ is_open: false }))).toBe(false);
  });

  it('returns null totals for an empty book without a portfolio', () => {
    const totals = computePaperTotals(null, []);
    expect(totals.unrealized).toBeNull();
    expect(totals.total).toBeNull();
    expect(totals.openCount).toBe(0);
  });

  it('computes notional magnitude', () => {
    expect(positionNotional(position({ side: 'SELL', ltp: 120, quantity: 75 }))).toBe(9_000);
    expect(positionNotional(null)).toBeNull();
  });

  it('classifies and formats P&L', () => {
    expect(pnlClass(10)).toBe('pos-num');
    expect(pnlClass(-10)).toBe('neg-num');
    expect(pnlClass(0)).toBe('');
    expect(pnlClass(null)).toBe('');
    expect(fmtInr(1234.5, true)).toContain('1,234.5');
    expect(fmtInr(null)).toBe('—');
  });
});
