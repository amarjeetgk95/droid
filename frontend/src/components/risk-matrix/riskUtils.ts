/**
 * Pure formatting / derivation helpers for the risk-matrix surfaces.
 *
 * Truth rules enforced here (and covered by tests):
 *  - The sign of a value is derived from the value itself, never from a
 *    `>= 0` boolean — a flat or unavailable number is NEVER painted green.
 *  - `economics_unavailable` records resolve to `null`, never to a fake ₹0.
 *  - The equity curve is built only from settled, realized P&L events.
 *
 * NOTE: `src/components/swing/swingUtils.ts` implements the same sign/tone
 * contract for the swing desk. These helpers should be promoted to a shared
 * module (e.g. `src/lib/format.ts`) — that file is outside this task's edit
 * scope (see report).
 */

import { toNumber } from '@/lib/coerce';

export const UNAVAILABLE = '—';

function toFinite(v: unknown): number | null {
  return toNumber(v, { rejectEmptyString: true });
}

/** Strict finite-number coercion; strings from Decimal-serialized payloads are accepted. */
export function finiteNumber(v: unknown): number | null {
  return toFinite(v);
}

/** `+0.050` / `-0.050` / `0.000`; `—` for non-finite input. */
export function signedNumber(v: unknown, digits = 1): string {
  const n = toFinite(v);
  if (n === null) return UNAVAILABLE;
  return `${n > 0 ? '+' : ''}${n.toFixed(digits)}`;
}

/** `+₹1,250` / `-₹1,250` / `₹0` / `—` for non-finite input. */
export function signedINR(v: unknown, digits = 0): string {
  const n = toFinite(v);
  if (n === null) return UNAVAILABLE;
  if (n === 0) return '₹0';
  const abs = Math.abs(n).toLocaleString('en-IN', { maximumFractionDigits: digits });
  return `${n > 0 ? '+' : '-'}₹${abs}`;
}

export type ValueTone = 'up' | 'down' | 'flat';

/** Zero and non-finite values are neutral — never up/down. */
export function valueTone(v: unknown): ValueTone {
  const n = toFinite(v);
  if (n === null || n === 0) return 'flat';
  return n > 0 ? 'up' : 'down';
}

export function valueToneClass(v: unknown): string {
  switch (valueTone(v)) {
    case 'up':
      return 'text-up-strong';
    case 'down':
      return 'text-down-strong';
    default:
      return 'text-ink-2';
  }
}

/* ── Audit ledger record (subset of backend AuditTradeRecord we render) ── */

export type AuditTradeLike = {
  signal_id?: string | null;
  underlying?: string | null;
  direction?: string | null;
  strategy?: string | null;
  option_symbol?: string | null;
  option_type?: string | null;
  option_strike?: number | null;
  trigger_price?: number | null;
  actual_fill_price?: number | null;
  exit_price?: number | null;
  actual_pnl_inr?: number | null;
  total_pnl_inr?: number | null;
  unrealized_pnl_inr?: number | null;
  economics_unavailable?: boolean | null;
  is_winner?: boolean | null;
  status?: string | null;
  outcome_label?: string | null;
  exit_reason?: string | null;
  created_at_utc?: number | null;
  exited_at_utc?: number | null;
  created_at_str?: string | null;
};

/**
 * Ledger P&L column: live `total_pnl_inr` when present (open MTM or settled),
 * else the settled `actual_pnl_inr`. `economics_unavailable` rows are null —
 * the backend deliberately booked no P&L for them.
 */
export function ledgerPnl(t: AuditTradeLike): number | null {
  if (t.economics_unavailable) return null;
  const total = toFinite(t.total_pnl_inr);
  if (total !== null) return total;
  return toFinite(t.actual_pnl_inr);
}

/** Entry basis: only a real executed fill counts (never the spot trigger). */
export function ledgerEntryPrice(t: AuditTradeLike): number | null {
  return toFinite(t.actual_fill_price);
}

/* ── Realized equity curve ─────────────────────────────────────────────── */

export type EquityPoint = {
  t: number;
  cumulative: number;
  signalId: string | null;
};

export type EquityCurve = {
  points: EquityPoint[];
  current: number;
  peak: number;
  trough: number;
  maxDrawdown: number;
  maxDrawdownPct: number | null;
};

/**
 * Cumulative realized P&L from settled audit records, oldest first.
 * Returns null when fewer than two settled events exist — a single point is
 * not a curve and must never be padded into one.
 */
export function buildEquityCurve(trades: AuditTradeLike[]): EquityCurve | null {
  const events: { pnl: number; t: number; signalId: string | null }[] = [];
  for (const trade of trades) {
    if (trade.economics_unavailable) continue;
    const pnl = toFinite(trade.actual_pnl_inr);
    const t = toFinite(trade.exited_at_utc) ?? toFinite(trade.created_at_utc);
    if (pnl === null || t === null) continue;
    events.push({ pnl, t, signalId: trade.signal_id ?? null });
  }
  if (events.length < 2) return null;
  events.sort((a, b) => a.t - b.t);

  let cumulative = 0;
  let peak = 0;
  let trough = 0;
  let maxDrawdown = 0;
  const points: EquityPoint[] = events.map((e) => {
    cumulative += e.pnl;
    peak = Math.max(peak, cumulative);
    trough = Math.min(trough, cumulative);
    maxDrawdown = Math.max(maxDrawdown, peak - cumulative);
    return { t: e.t, cumulative, signalId: e.signalId };
  });

  const last = points[points.length - 1].cumulative;
  return {
    points,
    current: last,
    peak,
    trough,
    maxDrawdown,
    maxDrawdownPct: peak > 0 ? Number(((maxDrawdown / peak) * 100).toFixed(2)) : null,
  };
}
