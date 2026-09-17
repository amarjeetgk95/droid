/* Defensive parsing + formatting shared by the signals desk.
   Backend payloads vary across deploy versions; every field is coerced
   to a safe shape so the UI never crashes on partial data. */

export function asStr(v: unknown): string | null {
  if (v === null || v === undefined) return null;
  const s = String(v).trim();
  return s ? s : null;
}

export function asNum(v: unknown): number | null {
  const n = typeof v === 'string' && v.trim() !== '' ? Number(v) : (v as number);
  return typeof n === 'number' && Number.isFinite(n) ? n : null;
}

export function getObj(v: unknown): Record<string, unknown> | null {
  if (v && typeof v === 'object' && !Array.isArray(v)) return v as Record<string, unknown>;
  return null;
}

export function pickStr(o: Record<string, unknown>, ...keys: string[]): string | null {
  for (const k of keys) {
    const s = asStr(o[k]);
    if (s) return s;
  }
  return null;
}

export function pickNum(o: Record<string, unknown>, ...keys: string[]): number | null {
  for (const k of keys) {
    const n = asNum(o[k]);
    if (n !== null) return n;
  }
  return null;
}

export function pickMs(o: Record<string, unknown>, ...keys: string[]): number | null {
  for (const k of keys) {
    const v = o[k];
    if (v === null || v === undefined || v === '') continue;
    if (typeof v === 'number' && Number.isFinite(v)) {
      // Heuristic: seconds-epoch vs ms-epoch.
      return v < 1e12 ? Math.round(v * 1000) : Math.round(v);
    }
    const d = new Date(String(v));
    const t = d.getTime();
    if (!Number.isNaN(t)) return t;
  }
  return null;
}

/** TTL duration helper: ttl_ms / ttl_seconds are DURATIONS, not epochs.
 *  Returns the duration in ms, or null when absent. Never confuses a
 *  300000ms duration with an epoch timestamp. */
export function pickTtlDurationMs(o: Record<string, unknown>): number | null {
  const ms = asNum(o.ttl_ms);
  if (ms !== null && ms >= 0 && ms < 86400000 * 2) return Math.round(ms);
  const sec =
    asNum(o.ttl_seconds) ?? asNum(o.ttl) ?? asNum(o.ttl_remaining_seconds);
  if (sec !== null && sec >= 0 && sec < 86400 * 2) return Math.round(sec * 1000);
  return null;
}

/** Absolute expiry resolver: prefers epoch timestamps, then derives
 *  baseMs + ttl duration. Returns { expiresMs, source } so callers can
 *  distinguish a real epoch from a computed duration. */
export function resolveExpiresMs(
  o: Record<string, unknown>,
  baseMs: number | null,
): { expiresMs: number | null; source: 'absolute' | 'ttl_duration' | 'none' } {
  const absolute = pickMs(o, 'expires_at_ms', 'expires_at', 'expiry_ms', 'expires_at_utc', 'expiry');
  if (absolute !== null) return { expiresMs: absolute, source: 'absolute' };
  const ttlMs = pickTtlDurationMs(o);
  if (ttlMs !== null && baseMs !== null) {
    return { expiresMs: baseMs + ttlMs, source: 'ttl_duration' };
  }
  return { expiresMs: null, source: 'none' };
}

/* ---------------- formatting ---------------- */

export function fmtTimeMs(ms: number | null): string {
  if (ms === null) return '—';
  const d = new Date(ms);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
}

/** Expiry label from an audit row: explicit field, else FYERS option symbol. */
export function ledgerExpiry(o: Record<string, unknown>): string {
  const direct = pickStr(o, 'expiry');
  if (direct) {
    const f = fmtExpiry(direct);
    if (f !== '—') return f;
  }
  const contract = getObj(o.option_contract);
  if (contract) {
    const f = fmtExpiry(contract.expiry_date ?? contract.expiry);
    if (f !== '—') return f;
  }
  // FYERS weekly {YY}{M}{dd} / monthly {YY}{MMM} after the underlying.
  const sym = pickStr(o, 'option_symbol', 'broker_symbol', 'symbol') ?? '';
  const m = sym.toUpperCase().match(/^(?:NSE|BSE):(?:BANKNIFTY|NIFTY|SENSEX)(\d{2})(.+?)(CE|PE)$/);
  if (m) {
    const tail = m[2];
    const mon3 = tail.slice(0, 3);
    if (/^[A-Z]{3}$/.test(mon3)) return mon3; // monthly: no day component
    const code = tail[0];
    const dd = tail.slice(1, 3);
    const rev: Record<string, string> = { '1': 'JAN', '2': 'FEB', '3': 'MAR', '4': 'APR', '5': 'MAY', '6': 'JUN', '7': 'JUL', '8': 'AUG', '9': 'SEP', O: 'OCT', N: 'NOV', D: 'DEC' };
    if (rev[code] && /^\d{2}$/.test(dd)) return `${dd} ${rev[code]}`;
  }
  return '—';
}
export function fmtExpiry(v: unknown): string {
  if (v === null || v === undefined) return '—';
  const s = String(v).trim();
  if (!s) return '—';
  const d = new Date(s);
  if (!Number.isNaN(d.getTime()) && /\d{4}/.test(s)) {
    return d.toLocaleString('en-IN', { day: '2-digit', month: 'short' }).toUpperCase().replace(',', '');
  }
  const m = s.match(/(\d{1,2})\s*[-/]?\s*([A-Za-z]{3,9})\b/i);
  if (m) return `${m[1].padStart(2, '0')} ${m[2].slice(0, 3).toUpperCase()}`;
  return '—';
}

/** Full desk timestamp: 11 Sep 14:32:05. */
export function fmtDateTimeMs(ms: number | null): string {
  if (ms === null) return '—';
  const d = new Date(ms);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
}

export type TtlTone = 'ok' | 'warn' | 'expired';

/** TTL countdown with a warning band under 2 minutes. */
export function fmtTtl(expiresMs: number | null, now: number): { label: string; tone: TtlTone } {
  if (expiresMs === null) return { label: '—', tone: 'ok' };
  const s = Math.round((expiresMs - now) / 1000);
  if (s <= 0) return { label: 'expired', tone: 'expired' };
  if (s < 60) return { label: `${s}s`, tone: s < 45 ? 'warn' : 'ok' };
  const m = Math.floor(s / 60);
  if (m < 60) return { label: `${m}m ${s % 60}s`, tone: m < 2 ? 'warn' : 'ok' };
  return { label: `${Math.floor(m / 60)}h ${m % 60}m`, tone: 'ok' };
}

/** Distance of the trigger from the current spot. */
export function fmtDist(trigger: number | null, spot: number | null): string {
  if (trigger === null || spot === null || spot === 0) return '—';
  const diff = trigger - spot;
  const pct = (diff / Math.abs(spot)) * 100;
  const sign = diff > 0 ? '+' : '';
  return `${sign}${diff.toFixed(2)} (${sign}${pct.toFixed(2)}%)`;
}

/** Confidence arrives as 0..1 or 0..100 depending on source — normalise to text. */
export function fmtConf(conf: number | null): string {
  if (conf === null) return '—';
  return conf > 1 ? `${conf.toFixed(1)}%` : `${Math.round(conf * 100)}%`;
}

/** 0..100 usable width for confidence meters. */
export function confPct(conf: number | null): number {
  if (conf === null) return 0;
  const pct = conf > 1 ? conf : conf * 100;
  return Math.max(0, Math.min(100, pct));
}

/** 0..1-normalised confidence (confidence domain only, never score). */
export function confidence01ToPct(v: number | null): number {
  return confPct(v);
}

/** 0..100 score domain (score domain only, never confidence). */
export function score0100ToPct(v: number | null): number {
  if (v === null) return 0;
  return Math.max(0, Math.min(100, v));
}

export function shortId(id: string): string {
  return id.length > 10 ? `${id.slice(0, 8)}…` : id;
}

/** SCALP_BREAKOUT -> "scalp breakout" style labels. */
export function prettyKey(s: string): string {
  return s.replace(/_/g, ' ').toLowerCase();
}

export function isHiddenTab(): boolean {
  return typeof document !== 'undefined' && document.hidden;
}

/* ---------------- filter predicates ---------------- */

export type DeskScope = 'SCALP' | 'INTRADAY';

/** Instrument match is exact on the normalized token — never a substring,
 *  so NIFTY can never match BANKNIFTY. Bare option symbols (NIFTY25…) pass. */
export function matchesInstrumentFilter(symbol: string, filter: string): boolean {
  const f = filter.toUpperCase();
  if (!f || f === 'ALL') return true;
  const s = symbol.toUpperCase().replace(/[^A-Z0-9]/g, '');
  if (s === f) return true;
  return s.startsWith(f) && /^[0-9]/.test(s.slice(f.length));
}

/** Desk token from a raw desk string; null when absent or unknown. */
export function deskScope(desk: string | null): DeskScope | null {
  if (!desk) return null;
  const d = desk.toUpperCase();
  if (d === 'SCALP' || d === 'SCALP_DESK') return 'SCALP';
  if (d === 'INTRADAY' || d === 'INTRADAY_DESK') return 'INTRADAY';
  return null;
}

/** Explicit desk filter: the boolean flag wins when present, else the desk
 *  token; a row with neither is excluded from both views — null-desk rows
 *  must never leak into every desk. */
export function matchesDeskFilter(desk: string | null, isScalp: boolean | null, filter: DeskScope): boolean {
  if (isScalp !== null) return filter === 'SCALP' ? isScalp : !isScalp;
  const scope = deskScope(desk);
  return scope !== null && scope === filter;
}

/* ---------------- row normalization ---------------- */

export type ActiveRow = {
  raw: Record<string, unknown>;
  id: string;
  timeMs: number | null;
  symbol: string;
  strategy: string;
  direction: unknown;
  state: string;
  /** Legacy alias = confidence01 only (no score merge). Kept for desk compat. */
  confidence: number | null;
  /** Confidence domain only: confidence / confidence_pct / confidence01. */
  confidence01: number | null;
  /** Score domain only: score / score0100 / overall_confidence. Never merged. */
  score0100: number | null;
  /** Legacy alias = triggerLevel only (no entry merge). Kept for desk compat. */
  trigger: number | null;
  /** Spot-domain trigger level (trigger_price / trigger / trigger_level). */
  triggerLevel: number | null;
  /** Fill-domain entry (actual_fill_price / fill_price / entry_price / entry). */
  entryFill: number | null;
  sl: number | null;
  t1: number | null;
  t2: number | null;
  spot: number | null;
  expiresMs: number | null;
  expiresSource: 'absolute' | 'ttl_duration' | 'none';
  desk: string | null;
  isScalp: boolean | null;
  /** True when trigger or SL is missing — the row is shown, never hidden. */
  incomplete: boolean;
  missingLevels: string[];
  quarantined: boolean;
  quarantineReason: string | null;
};

export function toActiveRow(s: unknown): ActiveRow | null {
  const o = getObj(s);
  if (!o) return null;
  const id = pickStr(o, 'signal_id', 'id');
  if (!id) return null;
  const isScalpRaw = o.is_scalp;
  const timeMs = pickMs(o, 'created_at_ms', 'created_at', 'timestamp_ms', 'timestamp', 'created_at_iso', 'created_at_utc');
  // Split domains: trigger (spot plan) vs entry fill (premium execution).
  // Never fall back across domains: an entry fill must not masquerade as a trigger.
  const triggerLevel = pickNum(o, 'trigger_price', 'trigger', 'trigger_level');
  const entryFill = pickNum(o, 'actual_fill_price', 'fill_price', 'entry_price', 'entry');
  // Split confidence (0..1 or 0..100 from the confidence domain) vs score
  // (0..100 model score). No alias merge: a score must never inflate confidence.
  const confidence01 = pickNum(o, 'confidence', 'confidence_pct', 'confidence01');
  const score0100 = pickNum(o, 'score', 'score0100', 'overall_confidence');
  const sl = pickNum(o, 'stop_loss', 'sl', 'stop');
  const missingLevels: string[] = [];
  if (triggerLevel === null) missingLevels.push('trigger');
  if (sl === null) missingLevels.push('stop_loss');
  const { expiresMs, source: expiresSource } = resolveExpiresMs(o, timeMs);
  return {
    raw: o,
    id,
    timeMs,
    symbol: pickStr(o, 'underlying', 'instrument', 'symbol') ?? '—',
    strategy: pickStr(o, 'strategy') ?? '—',
    direction: o.direction ?? o.bias ?? 'NEUTRAL',
    state: pickStr(o, 'status', 'state', 'fsm_state') ?? '—',
    confidence: confidence01,
    confidence01,
    score0100,
    trigger: triggerLevel,
    triggerLevel,
    entryFill,
    sl,
    t1: pickNum(o, 'target_1', 'target1', 't1'),
    t2: pickNum(o, 'target_2', 'target2', 't2'),
    spot: pickNum(o, 'spot_price', 'current_price', 'ltp', 'spot', 'underlying_price'),
    expiresMs,
    expiresSource,
    desk: pickStr(o, 'desk'),
    isScalp: typeof isScalpRaw === 'boolean' ? isScalpRaw : null,
    incomplete: missingLevels.length > 0,
    missingLevels,
    quarantined: false,
    quarantineReason: null,
  };
}

export type LedgerRow = {
  id: string;
  underlying: string;
  strategy: string;
  direction: unknown;
  status: string;
  outcomeLabel: string | null;
  isWinner: boolean | null;
  side: string | null;
  qty: number | null;
  entry: number | null;
  exit: number | null;
  current: number | null;
  realized: number | null;
  unrealized: number | null;
  total: number | null;
  timeMs: number | null;
  entryTimeMs: number | null;
  exitTimeMs: number | null;
  expiry: string | null;
  /** Same-domain corruption flag — render a quarantined badge, never hide. */
  quarantined: boolean;
  quarantineReason: string | null;
  /** Operator action for corrupt rows (POST audit/sanitize). */
  sanitizeHint: string | null;
};

export const LEDGER_SANITIZE_HINT = 'POST /api/v1/signals/audit/sanitize';

export function toLedgerRow(t: unknown): LedgerRow | null {
  const o = getObj(t);
  if (!o) return null;
  const id = pickStr(o, 'signal_id', 'id');
  if (!id) return null;
  // Entry is a fill concept only. Never fall back to trigger/spot prices:
  // that renders index levels (e.g. 24925) as if they were option premiums.
  const entry = pickNum(o, 'actual_fill_price', 'fill_price', 'entry_price');
  let exit = pickNum(o, 'exit_price');
  let current = pickNum(o, 'current_price', 'ltp');
  // Same-domain rule: a premium entry (<=5000) paired with a spot-scale
  // exit/current (>5000) is legacy corruption. Quarantine the ROW (flag +
  // sanitize hint) instead of returning null — the desk must show a badge,
  // never silently drop evidence.
  let quarantined = false;
  let quarantineReason: string | null = null;
  if (entry !== null && entry <= 5000) {
    if (exit !== null && exit > 5000) {
      quarantined = true;
      quarantineReason = `exit ${exit} off-domain vs entry ${entry}`;
      exit = null;
    }
    if (current !== null && current > 5000) {
      quarantined = true;
      quarantineReason = quarantineReason ?? `current ${current} off-domain vs entry ${entry}`;
      current = null;
    }
  }
  return {
    id,
    underlying: pickStr(o, 'underlying', 'instrument', 'symbol') ?? '—',
    strategy: pickStr(o, 'strategy') ?? '—',
    direction: o.direction ?? 'NEUTRAL',
    status: pickStr(o, 'status', 'state', 'fsm_state') ?? '—',
    outcomeLabel: pickStr(o, 'outcome_label', 'outcome'),
    isWinner: typeof o.is_winner === 'boolean' ? o.is_winner : null,
    side: pickStr(o, 'paper_side', 'side'),
    qty: pickNum(o, 'quantity', 'qty'),
    entry,
    exit,
    current,
    realized: pickNum(o, 'actual_pnl_inr', 'realized_pnl', 'pnl'),
    unrealized: pickNum(o, 'unrealized_pnl_inr'),
    total: pickNum(o, 'total_pnl_inr', 'net_pnl'),
    timeMs: pickMs(o, 'exited_at_utc', 'closed_at_ms', 'closed_at', 'updated_at_utc', 'created_at_utc'),
    entryTimeMs: pickMs(o, 'executed_at_utc', 'executed_at', 'created_at_utc', 'created_at_ms', 'created_at'),
    exitTimeMs: pickMs(o, 'exited_at_utc', 'closed_at_ms', 'closed_at'),
    expiry: ledgerExpiry(o),
    quarantined,
    quarantineReason,
    sanitizeHint: quarantined ? LEDGER_SANITIZE_HINT : null,
  };
}

/** A ledger row with no fill and no exit is an unfilled setup, not a trade. */
export function isUnfilledLedgerRow(r: LedgerRow): boolean {
  return r.entry === null && r.exit === null;
}

/* ---------------- lifecycle predicates (single source of truth) ---------------- */

/** Terminal lifecycle states: no further paper execution is possible. */
const TERMINAL_STATE_RE = /(CLOSED|EXPIRED|INVALIDATED|TARGET_2_HIT|STOP_LOSS_HIT|TIME_STOP)/;

export function isTerminalSignalState(state: string): boolean {
  return TERMINAL_STATE_RE.test(state.toUpperCase());
}

export type ExecutionEligibility = { eligible: boolean; reason: string | null };

/** ONE eligibility predicate shared by the row action button and the `x`
 *  keyboard shortcut. A closed market blocks first (fail-closed); CONFIRMED
 *  rows are already filled/accepted and must not be re-executed; terminal
 *  states are concluded. */
export function executionEligibility(state: string, marketClosed: boolean): ExecutionEligibility {
  if (marketClosed) return { eligible: false, reason: 'Market closed — paper execution is disabled.' };
  const s = state.toUpperCase();
  if (isTerminalSignalState(s)) return { eligible: false, reason: `Signal concluded (${state}) — cannot execute.` };
  if (s.includes('CONFIRMED')) return { eligible: false, reason: 'Already confirmed — cannot re-execute.' };
  return { eligible: true, reason: null };
}

/** Open-state predicate shared by the live strip totals and the ledger rows:
 *  EXPIRED / INVALIDATED are concluded and must not count as open capital. */
const LEDGER_CLOSED_RE = /(WON|LOST|CLOSED|SQUARED|STOP|TARGET_2|RUNNER|EXPIRED|INVALIDATED)/;

export function isOpenLedgerStatus(status: string): boolean {
  return !LEDGER_CLOSED_RE.test(status.toUpperCase());
}

export type LedgerTotals = { realized: number; unrealized: number; total: number };

/** Row-sum of a ledger window using the shared open-state predicate: closed
 *  rows contribute realized P&L, open rows contribute unrealized MTM. */
export function sumLedgerTotals(rows: LedgerRow[]): LedgerTotals | null {
  if (rows.length === 0) return null;
  let realized = 0;
  let unrealized = 0;
  let net = 0;
  let hasNet = false;
  for (const r of rows) {
    if (isOpenLedgerStatus(r.status)) {
      if (r.unrealized !== null) unrealized += r.unrealized;
      else if (r.total !== null) unrealized += r.total;
    } else if (r.realized !== null) {
      realized += r.realized;
    } else if (r.total !== null) {
      realized += r.total;
    }
    if (r.total !== null) {
      net += r.total;
      hasNet = true;
    }
  }
  if (!hasNet) net = realized + unrealized;
  const round2 = (v: number) => Math.round(v * 100) / 100;
  return { realized: round2(realized), unrealized: round2(unrealized), total: round2(net) };
}

export type LedgerSummary = {
  closed: number | null;
  winRate: number | null;
  realized: number | null;
  unrealized: number | null;
  total: number | null;
  /** Global row count of the book, when the backend reports it. */
  totalRows: number | null;
};

/** Backend summary keys vary (`*_inr` vs short names) — accept both.
 *  Win rate is normalized once to a 0..100 percentage: bare `win_rate` is a
 *  0..1 fraction on this backend, `win_rate_pct` is already a percentage. */
export function toLedgerSummary(sum: Record<string, unknown> | null): LedgerSummary | null {
  if (!sum) return null;
  const winRatePct = pickNum(sum, 'win_rate_pct');
  const winRateRaw = pickNum(sum, 'win_rate', 'winRate');
  const winRate =
    winRatePct !== null
      ? winRatePct
      : winRateRaw === null
        ? null
        : Math.round((winRateRaw <= 1 ? winRateRaw * 100 : winRateRaw) * 10) / 10;
  return {
    closed: pickNum(sum, 'closed_trades', 'total_closed', 'closed', 'total_signals_audited'),
    winRate,
    realized: pickNum(sum, 'net_realized_pnl_inr', 'net_realized_pnl', 'realized', 'realized_pnl'),
    unrealized: pickNum(sum, 'net_unrealized_pnl_inr', 'net_unrealized_pnl', 'unrealized', 'unrealized_pnl'),
    total: pickNum(sum, 'total_pnl_inr', 'total_pnl', 'total', 'net_pnl'),
    totalRows: pickNum(sum, 'total_signals_audited'),
  };
}

/* ---------------- semantic state tones ---------------- */

export type Tone = 'bull' | 'bear' | 'info' | 'warn' | 'neut';

/** Map a signal/status state to a badge tone. */
export function stateTone(state: string): Tone {
  const s = state.toUpperCase();
  // Wins first: TARGET_1/2_HIT are profitable outcomes, never neutral gray.
  if (/(TARGET_[12]_HIT|WON|WIN|PROFIT)/.test(s)) return 'bull';
  if (/(STOP_LOSS_HIT|INVALIDATED|LOSS|LOST|KILL|FAIL|REJECT|CANCEL)/.test(s)) return 'bear';
  if (/(CONFIRM|ACTIVE|FILLED|EXECUTED)/.test(s)) return 'bull';
  if (/(ARMED|READY|TRIGGERED)/.test(s)) return 'info';
  if (/(EXPIRED|STALE)/.test(s)) return 'warn';
  return 'neut';
}
