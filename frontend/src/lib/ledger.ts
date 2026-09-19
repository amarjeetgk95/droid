import type { PortfolioSummary, VirtualPosition } from '@/lib/types';

export type PaperTotals = {
  capital: number | null;
  available: number | null;
  used: number | null;
  utilizationPct: number | null;
  realized: number | null;
  unrealized: number | null;
  total: number | null;
  openCount: number;
};

function fin(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

function round2(v: number): number {
  return Math.round(v * 100) / 100;
}

export function isOpenPosition(p: VirtualPosition | null | undefined): p is VirtualPosition {
  if (!p || typeof p !== 'object') return false;
  if (typeof p.is_open === 'boolean') return p.is_open;
  return true;
}

export function positionUnrealized(p: VirtualPosition | null | undefined): number | null {
  if (!p) return null;
  const direct = fin(p.unrealized_pnl);
  if (direct !== null) return round2(direct);
  const avg = fin(p.average_price);
  const ltp = fin(p.ltp);
  const qty = fin(p.quantity);
  if (avg === null || ltp === null || qty === null) return null;
  const sign = p.side === 'SELL' ? -1 : 1;
  return round2((ltp - avg) * qty * sign);
}

export function positionNotional(p: VirtualPosition | null | undefined): number | null {
  if (!p) return null;
  const ltp = fin(p.ltp);
  const qty = fin(p.quantity);
  if (ltp === null || qty === null) return null;
  return round2(Math.abs(ltp * qty));
}

export function computePaperTotals(
  portfolio: PortfolioSummary | null | undefined,
  positions: VirtualPosition[] | null | undefined,
): PaperTotals {
  const rows = (positions ?? []).filter(isOpenPosition);
  const hasRows = Array.isArray(positions);

  const portfolioUnrealized = fin(portfolio?.total_unrealized_pnl);
  const portfolioRealized = fin(portfolio?.total_realized_pnl);
  const rowUnrealized = hasRows && rows.length > 0
    ? round2(rows.reduce((acc, p) => acc + (positionUnrealized(p) ?? 0), 0))
    : null;
  const rowRealized = hasRows && positions && positions.length > 0
    ? round2(positions.reduce((acc, p) => acc + (fin(p.realized_pnl) ?? 0), 0))
    : null;

  const unrealized = portfolioUnrealized ?? rowUnrealized;
  const realized = portfolioRealized ?? rowRealized;
  const total =
    fin(portfolio?.total_portfolio_pnl) ??
    (realized !== null || unrealized !== null ? round2((realized ?? 0) + (unrealized ?? 0)) : null);

  return {
    capital: fin(portfolio?.virtual_capital),
    available: fin(portfolio?.available_margin),
    used: fin(portfolio?.used_margin),
    utilizationPct: fin(portfolio?.margin_utilization_pct),
    realized,
    unrealized,
    total,
    openCount: fin(portfolio?.open_positions_count) ?? rows.length,
  };
}

export function pnlClass(v: number | null | undefined): string {
  if (typeof v !== 'number' || !Number.isFinite(v) || v === 0) return '';
  return v > 0 ? 'pos-num' : 'neg-num';
}

const INR = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 2,
});

const INR_SIGNED = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 2,
  signDisplay: 'always',
});

export function fmtInr(v: number | null | undefined, signed = false): string {
  if (typeof v !== 'number' || !Number.isFinite(v)) return '—';
  return signed ? INR_SIGNED.format(v) : INR.format(v);
}
