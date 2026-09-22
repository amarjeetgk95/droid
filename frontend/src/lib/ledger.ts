import type { PortfolioSummary, VirtualPosition } from '@/lib/types';
import { DEFAULT_STALE_AFTER_MS } from '@/lib/feedState';

export type PaperTotals = {
  capital: number | null;
  available: number | null;
  used: number | null;
  utilizationPct: number | null;
  realized: number | null;
  unrealized: number | null;
  total: number | null;
  openCount: number;
  /** Age of the mark backing unrealized MTM, in ms. null = age unknown. */
  markAgeMs?: number | null;
  /** Provenance of that mark — stream MTM vs REST snapshot vs unknown. */
  markSource?: LedgerMarkSource;
  /** True when the mark is missing or older than the staleness window. */
  markStale?: boolean;
  /** True when open rows exist but no mark could produce an unrealized figure. */
  unrealizedUnavailable?: boolean;
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

/* ---------------- mark provenance (never invent a mark) ---------------- */

export type PaperMarkContext = {
  /** Backend instant of the last mark used for MTM (epoch ms). */
  markAtMs?: number | null;
  /** Where the mark came from — live stream MTM vs REST snapshot. */
  liveSource?: 'stream' | 'rest' | null;
  /** Reference clock, injectable for tests. */
  nowMs?: number;
  /** Age past which a mark is considered stale. */
  staleAfterMs?: number;
};

export type PaperMark = {
  markAtMs: number | null;
  markAgeMs: number | null;
  markSource: LedgerMarkSource;
  /** Missing age is treated as stale — an undated mark is not a fresh mark. */
  stale: boolean;
};

/** Describe the MTM mark without fabricating one: unknown time stays unknown. */
export function describePaperMark(context: PaperMarkContext = {}): PaperMark {
  const markAtMs =
    typeof context.markAtMs === 'number' && Number.isFinite(context.markAtMs)
      ? context.markAtMs
      : null;
  const staleAfterMs = context.staleAfterMs ?? DEFAULT_STALE_AFTER_MS;
  const now =
    typeof context.nowMs === 'number' && Number.isFinite(context.nowMs) && context.nowMs > 0
      ? context.nowMs
      : Date.now();
  const markAgeMs = markAtMs === null ? null : Math.max(0, now - markAtMs);
  return {
    markAtMs,
    markAgeMs,
    markSource: ledgerMarkSource(context.liveSource),
    stale: markAgeMs === null || markAgeMs > staleAfterMs,
  };
}

export type PositionMark = PaperMark & {
  /** Derived unrealized P&L, or null when the position has no usable mark. */
  unrealized: number | null;
  /** True only when a finite ltp exists for this position. */
  hasMark: boolean;
  /** True when the mark is present AND fresh — safe to label as live MTM. */
  usable: boolean;
};

/** One position's mark: derived P&L plus its provenance. Missing ltp → null. */
export function positionMark(
  p: VirtualPosition | null | undefined,
  context: PaperMarkContext = {},
): PositionMark {
  const meta = describePaperMark(context);
  const hasMark = fin(p?.ltp) !== null;
  return {
    ...meta,
    unrealized: positionUnrealized(p),
    hasMark,
    usable: hasMark && !meta.stale,
  };
}

export function computePaperTotals(
  portfolio: PortfolioSummary | null | undefined,
  positions: VirtualPosition[] | null | undefined,
  mark: PaperMarkContext = {},
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
  const markMeta = describePaperMark(mark);

  return {
    capital: fin(portfolio?.virtual_capital),
    available: fin(portfolio?.available_margin),
    used: fin(portfolio?.used_margin),
    utilizationPct: fin(portfolio?.margin_utilization_pct),
    realized,
    unrealized,
    total,
    openCount: fin(portfolio?.open_positions_count) ?? rows.length,
    markAgeMs: markMeta.markAgeMs,
    markSource: markMeta.markSource,
    markStale: markMeta.stale,
    unrealizedUnavailable: unrealized === null && rows.length > 0,
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

/* ---------------- mark age / source (never invent P&L) ---------------- */

export type LedgerMarkSource = 'live-mtm' | 'rest-snapshot' | 'unknown';

/** Map a hook live-source to the honest ledger mark source. No invented marks. */
export function ledgerMarkSource(liveSource: 'stream' | 'rest' | null | undefined): LedgerMarkSource {
  if (liveSource === 'stream') return 'live-mtm';
  if (liveSource === 'rest') return 'rest-snapshot';
  return 'unknown';
}

export function ledgerMarkSourceLabel(source: LedgerMarkSource): string {
  if (source === 'live-mtm') return 'LIVE MTM';
  if (source === 'rest-snapshot') return 'REST SNAPSHOT';
  return 'MARK UNKNOWN';
}

/** Age label for a ledger mark. Null mark → 'age unknown', never 'just now'. */
export function ledgerMarkAgeLabel(markAtMs: number | null | undefined, nowMs?: number): string {
  if (markAtMs === null || markAtMs === undefined || !Number.isFinite(markAtMs)) return 'age unknown';
  const now = typeof nowMs === 'number' && Number.isFinite(nowMs) && nowMs > 0 ? nowMs : Date.now();
  const seconds = Math.max(0, Math.round((now - markAtMs) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  return `${Math.floor(minutes / 60)}h ago`;
}

export type LedgerMarkMeta = {
  source: LedgerMarkSource;
  sourceLabel: string;
  markAtMs: number | null;
  ageLabel: string;
};

/** One honest mark description for the P&L strip: source + age, never a fresh stamp. */
export function describeLedgerMark(
  markAtMs: number | null | undefined,
  liveSource: 'stream' | 'rest' | null | undefined,
  nowMs?: number,
): LedgerMarkMeta {
  const source = ledgerMarkSource(liveSource);
  return {
    source,
    sourceLabel: ledgerMarkSourceLabel(source),
    markAtMs: typeof markAtMs === 'number' && Number.isFinite(markAtMs) ? markAtMs : null,
    ageLabel: ledgerMarkAgeLabel(markAtMs, nowMs),
  };
}
